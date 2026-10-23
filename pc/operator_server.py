"""Loopback operator UI and an FFmpeg recorder for the existing /maix01 relay."""

import argparse
import json
import math
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from .talkback import MAX_POST_BYTES, TalkbackRelay
from .camera_diagnostics import CameraDiagnostics, DEFAULT_USB_IP, ipv4
from .multistream_recording import MultistreamRecording
from .video_orientation import rotation_options, validate_rotation


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
DEFAULT_RECORDINGS = Path("recordings")
RECORDING_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")


class RecordingManager:
    def __init__(self, directory=DEFAULT_RECORDINGS, source="rtsp://127.0.0.1:8554/maix01", spawn=subprocess.Popen,
                 transport="udp", mode="combined", recording_mode="multistream", base_rotation=0):
        if transport not in ("tcp", "udp") or mode not in ("video", "audio", "combined"):
            raise ValueError("Invalid transport or stream mode")
        self.transport = transport
        self.mode = mode
        if recording_mode not in ("legacy", "multistream"):
            raise ValueError("Invalid recording mode")
        if recording_mode == "multistream" and mode == "audio":
            raise ValueError("Multistream recording requires video")
        self.recording_mode = recording_mode
        self._last_recording_status = {}
        directory = Path(directory)
        self.directory = directory if directory.is_absolute() else PROJECT_ROOT / directory
        self.source = source
        self.spawn = spawn
        self._lock = threading.RLock()
        self._process = None
        self._recording_id = None
        self._started = None
        self._log = None
        self._base_rotation = validate_rotation(base_rotation)
        self._rotation = 0
        self._view_path = self.directory / ".camera-view.json"
        self._maintenance_path = self.directory / ".maintenance.json"
        self._metadata_warnings = {}
        if self._view_path.is_file():
            try:
                view = json.loads(self._view_path.read_text())
                if not isinstance(view, dict):
                    raise ValueError("expected an object")
                self._rotation = validate_rotation(view.get("rotation"))
            except (ValueError, OSError) as error:
                self._metadata_warnings[self._view_path.name] = (
                    f"{self._view_path.name}: {error}. Using rotation 0; back up this file, "
                    "then save a camera rotation to replace it.")

    @property
    def effective_rotation(self):
        return (self._base_rotation + self._rotation) % 360

    def maintenance(self):
        with self._lock:
            try:
                marker = json.loads(self._maintenance_path.read_text())
                self._validate_owner(marker.get("owner") if isinstance(marker, dict) else None)
                return marker
            except FileNotFoundError:
                return None
            except (ValueError, OSError) as error:
                return {"owner": None, "error": f"Invalid maintenance marker: {error}; inspect {self._maintenance_path.name} before recovery"}

    @staticmethod
    def _validate_owner(owner):
        if not isinstance(owner, str) or not re.fullmatch(r"[a-f0-9]{32}", owner):
            raise ValueError("maintenance owner must be a 32-character lowercase hexadecimal operation ID")

    def begin_maintenance(self, owner):
        self._validate_owner(owner)
        with self._lock:
            self._refresh()
            if self._process is not None:
                raise RuntimeError("Stop recording and wait for finalization before maintenance")
            marker = self.maintenance()
            if marker is not None:
                if marker.get("owner") != owner:
                    raise RuntimeError("Maintenance belongs to another owner; use owner-specific recovery")
                return self.status()
            self.directory.mkdir(parents=True, exist_ok=True)
            with self._maintenance_path.open("x") as output:
                json.dump({"owner": owner}, output)
            return self.status()

    def end_maintenance(self, owner):
        self._validate_owner(owner)
        with self._lock:
            self._refresh()
            if self._process is not None:
                raise RuntimeError("Stop recording and wait for finalization before maintenance recovery")
            marker = self.maintenance()
            if marker is not None:
                if marker.get("owner") != owner:
                    raise RuntimeError("Maintenance belongs to another owner; use owner-specific recovery")
                self._maintenance_path.unlink()
            return self.status()

    def camera_view(self):
        with self._lock:
            self._refresh()
            return {"rotation": self._rotation, "effective_rotation": self.effective_rotation,
                    "metadata_warnings": list(self._metadata_warnings.values()),
                    "locked": self._process is not None}

    def set_camera_view(self, rotation):
        validate_rotation(rotation)
        with self._lock:
            self._refresh()
            if self._process is not None:
                raise RuntimeError("Stop recording and wait for finalization before rotating the camera")
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self._view_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"rotation": rotation}))
            temporary.replace(self._view_path)
            self._rotation = rotation
            self._metadata_warnings.pop(self._view_path.name, None)
            return self.camera_view()

    def _refresh(self):
        returncode = self._process.poll() if self._process is not None else None
        if returncode is not None:
            if isinstance(self._process, MultistreamRecording):
                self._last_recording_status = self._process.status()
            else:
                self._finish_legacy(returncode)
            self._close_process()

    def _finish_legacy(self, returncode):
        output = self.recording_path(self._recording_id)
        error = self._last_recording_status.get("error")
        if not error and returncode != 0:
            error = f"Legacy recording failed (FFmpeg exit {returncode})."
        if not error and (not output.is_file() or not output.stat().st_size):
            error = "Legacy recording failed: FFmpeg produced no media."
        if error:
            failed = output.with_suffix(".failed.mp4")
            if output.exists():
                output.rename(failed)
            self._last_recording_status = {
                "error": f"{error} Keep {failed.name} (if present) and {output.with_suffix('.ffmpeg.log').name} for recovery; see docs/multistream-recording.md."
            }
        else:
            output.with_suffix(".json").write_text(json.dumps({
                "duration_seconds": round(time.monotonic() - self._started),
                "rotation": self.effective_rotation,
            }))

    def _close_process(self):
        if self._process and self._process.stdin:
            try:
                self._process.stdin.close()
            except OSError:
                pass  # The recorder may have exited before closing its input.
        if self._log:
            self._log.close()
        self._process = None
        self._recording_id = None
        self._started = None
        self._log = None

    def status(self):
        with self._lock:
            self._refresh()
            path = self.recording_path(self._recording_id) if self._recording_id else None
            if path is None:
                display_path = None
            elif path.is_relative_to(PROJECT_ROOT):
                display_path = path.relative_to(PROJECT_ROOT).as_posix()
            else:
                display_path = str(path)
            details = (self._process.status() if isinstance(self._process, MultistreamRecording)
                       else self._last_recording_status)
            return {
                **details,
                "recording": self._process is not None,
                "rotation": self._rotation,
                "effective_rotation": self.effective_rotation,
                "metadata_warnings": list(self._metadata_warnings.values()),
                "maintenance": self.maintenance(),
                "id": self._recording_id,
                "duration_seconds": details.get("duration_seconds", round(time.monotonic() - self._started)
                                                if self._started else 0),
                "size_bytes": path.stat().st_size if path and path.exists() else 0,
                "path": display_path,
            }

    def start(self):
        with self._lock:
            self._refresh()
            if self.maintenance() is not None:
                raise RuntimeError("Maintenance is active. Wait for the owning operation or use owner-specific recovery in scripts/README.md")
            if self._process is not None:
                raise RuntimeError("recording is already active")
            self.directory.mkdir(parents=True, exist_ok=True)
            recording_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
            output = self.recording_path(recording_id)
            if self.recording_mode == "multistream":
                self._process = MultistreamRecording(output, self.source, self.transport, self.spawn,
                                                    rotation=self.effective_rotation)
                self._last_recording_status = {}
                self._recording_id = recording_id
                self._started = self._process.started
                return self.status()
            log = output.with_suffix(".ffmpeg.log").open("wb")
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostats",
                "-rtsp_transport", self.transport, "-analyzeduration", "10000000",
                "-probesize", "20000000",
            ]
            input_rotation, output_rotation = rotation_options(self.effective_rotation) if self.mode != "audio" else ([], [])
            command += [*input_rotation, "-i", self.source]
            if self.mode != "audio":
                command += ["-map", "0:v:0", "-c:v", "copy", "-bsf:v",
                            "filter_units=remove_types=0,h264_metadata=sample_aspect_ratio=1/1",
                            *output_rotation]
            if self.mode != "video":
                command += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k"]
            command += ["-movflags", "+faststart", "-f", "mp4", str(output)]
            try:
                process = self.spawn(
                    command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                log.close()
                raise
            self._process = process
            self._last_recording_status = {}
            self._recording_id = recording_id
            self._started = time.monotonic()
            self._log = log
            return self.status()

    def stop(self):
        with self._lock:
            self._refresh()
            if self._process is None:
                if self._last_recording_status.get("error"):
                    return self.status()
                raise RuntimeError("recording is not active")
            process = self._process
            if isinstance(process, MultistreamRecording):
                process.stop()
                return self.status()
            try:
                process.stdin.write(b"q\n")
                process.stdin.flush()
                returncode = process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired) as error:
                self._last_recording_status = {"error": f"Legacy recording interrupted during stop ({error}); forced termination required."}
                process.kill()
                try:
                    returncode = process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    return self.status()
            self._finish_legacy(returncode)
            self._close_process()
            return self.status()

    def wait(self):
        """Allow app shutdown to finish an asynchronous multistream mux."""
        with self._lock:
            process = self._process
        if isinstance(process, MultistreamRecording):
            process.wait()
        with self._lock:
            self._refresh()

    def recording_path(self, recording_id):
        if not recording_id or not RECORDING_ID.fullmatch(recording_id):
            raise ValueError("invalid recording id")
        return self.directory / (recording_id + ".mp4")

    def list_recordings(self):
        with self._lock:
            self._refresh()
            self._metadata_warnings = {name: warning for name, warning in self._metadata_warnings.items()
                                       if name == self._view_path.name}
            if not self.directory.exists():
                return []
            recordings = []
            for path in sorted(self.directory.glob("*.mp4"), reverse=True):
                if not RECORDING_ID.fullmatch(path.stem) or path.stat().st_size == 0:
                    continue
                if path.stem == self._recording_id and self._last_recording_status.get("error"):
                    continue
                duration = None
                metadata = path.with_suffix(".json")
                if metadata.is_file():
                    try:
                        document = json.loads(metadata.read_text())
                        if not isinstance(document, dict):
                            raise ValueError("expected an object")
                        value = document.get("duration_seconds")
                        if type(value) not in (int, float) or value < 0 or not math.isfinite(value):
                            raise ValueError("duration_seconds must be a finite nonnegative number")
                        duration = int(value)
                    except (ValueError, OSError, OverflowError) as error:
                        self._metadata_warnings[metadata.name] = (
                            f"{metadata.name}: {error}. Duration is unknown; keep the MP4 and "
                            "back up and repair its JSON sidecar, then refresh Recordings.")
                recordings.append({
                    "id": path.stem,
                    "size_bytes": path.stat().st_size,
                    "created_at": datetime.strptime(path.stem[:16], "%Y%m%dT%H%M%SZ").isoformat() + "Z",
                    "active": path.stem == self._recording_id,
                    "duration_seconds": round(time.monotonic() - self._started) if path.stem == self._recording_id else duration,
                    "url": "/api/recordings/" + path.stem + "/file",
                })
            return recordings


def make_handler(manager, html_path=APP_DIR / "operator_test.html", talkback=None, bluetooth=None, diagnostics=None):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code, payload):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _file(self, path, mime):
            if not path.is_file():
                self.send_error(404)
                return
            size = path.stat().st_size
            start, end = 0, size - 1
            requested = self.headers.get("Range")
            if requested:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                if not match:
                    self.send_error(416)
                    return
                start = int(match.group(1)) if match.group(1) else max(0, size - int(match.group(2)))
                end = int(match.group(2)) if match.group(1) and match.group(2) else size - 1
                if start >= size or end < start:
                    self.send_error(416)
                    return
                end = min(end, size - 1)
            self.send_response(206 if requested else 200)
            self.send_header("Content-Type", mime)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if requested:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as source:
                source.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = source.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def do_GET(self):
            route = urlsplit(self.path).path
            if route == "/api/camera/diagnostics":
                if diagnostics is None:
                    return self._json(503, {"error": "Camera diagnostics are not configured"})
                return self._json(200, diagnostics.check())
            if route in ("/", "/operator_test.html"):
                return self._file(Path(html_path), "text/html; charset=utf-8")
            if route == "/api/recordings/status":
                return self._json(200, manager.status())
            if route == "/api/camera/view":
                return self._json(200, manager.camera_view())
            if route == "/api/recordings":
                return self._json(200, manager.list_recordings())
            if route == "/api/talkback/status":
                return self._json(200, {"available": talkback is not None, "transport": "webrtc",
                                        "protocol": "TB3",
                                        "error": talkback.error if talkback else None})
            if route in ("/api/bluetooth/status", "/api/bluetooth/volume"):
                if bluetooth is None:
                    return self._json(503, {"error": "Bluetooth control is not configured"})
                code, payload = bluetooth.request(route.rsplit("/", 1)[1])
                return self._json(code, payload)
            match = re.fullmatch(r"/api/recordings/([^/]+)/file", route)
            if match:
                try:
                    path = manager.recording_path(match.group(1))
                except ValueError:
                    return self.send_error(404)
                if path.stem == manager.status()["id"]:
                    return self.send_error(409, "Stop recording before playback")
                return self._file(path, "video/mp4")
            self.send_error(404)

        def do_POST(self):
            route = urlsplit(self.path).path
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                return self._json(403, {"error": "cross-origin control is blocked"})
            if route in ("/api/maintenance/begin", "/api/maintenance/end"):
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size < 1 or size > 128:
                        raise ValueError("invalid maintenance request size")
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict) or set(payload) != {"owner"}:
                        raise ValueError("request must contain only owner")
                    operation = manager.begin_maintenance if route.endswith("/begin") else manager.end_maintenance
                    return self._json(200, operation(payload["owner"]))
                except (ValueError, UnicodeError) as error:
                    return self._json(400, {"error": str(error)})
                except RuntimeError as error:
                    return self._json(409, {"error": str(error)})
                except OSError as error:
                    return self._json(503, {"error": str(error)})
            if route == "/api/camera/view":
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size <= 0 or size > 128:
                        raise ValueError("invalid camera view request size")
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict) or set(payload) != {"rotation"}:
                        raise ValueError("request must contain only rotation")
                    return self._json(200, manager.set_camera_view(payload["rotation"]))
                except (ValueError, UnicodeError) as error:
                    return self._json(400, {"error": str(error)})
                except RuntimeError as error:
                    return self._json(409, {"error": str(error)})
                except OSError as error:
                    return self._json(503, {"error": str(error)})
            if route == "/api/talkback/offer":
                if talkback is None:
                    return self._json(503, {"error": "talkback is not configured"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size <= 0 or size > MAX_POST_BYTES:
                        raise ValueError("invalid SDP size")
                    sdp = self.rfile.read(size).decode("utf-8")
                    return self._json(200, talkback.offer(sdp))
                except (ValueError, UnicodeError) as error:
                    return self._json(400, {"error": str(error)})
                except RuntimeError as error:
                    return self._json(409, {"error": str(error)})
                except OSError:
                    return self._json(503, {"error": "WebRTC relay is unavailable"})
            if route == "/api/talkback/stop":
                if talkback is None:
                    return self._json(503, {"error": "talkback is not configured"})
                session = self.headers.get("X-Talkback-Session")
                if not session:
                    return self._json(400, {"error": "talkback session is required"})
                talkback.stop(session)
                return self._json(200, {"stopped": True})
            if route in ("/api/bluetooth/scan", "/api/bluetooth/select", "/api/bluetooth/volume"):
                if bluetooth is None:
                    return self._json(503, {"error": "Bluetooth control is not configured"})
                mac = None
                if route.endswith("/select") or route.endswith("/volume"):
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                        if size < 1 or size > 256:
                            raise ValueError("invalid selection body")
                        body = json.loads(self.rfile.read(size))
                        if route.endswith("/volume"):
                            if not isinstance(body, dict) or set(body) != {"volume"} or type(body["volume"]) is not int or not 0 <= body["volume"] <= 100:
                                raise ValueError("invalid volume")
                            code, payload = bluetooth.request("volume", volume=body["volume"])
                            return self._json(code, payload)
                        mac = body.get("mac")
                    except (ValueError, AttributeError):
                        return self._json(400, {"error": "invalid selection body"})
                elif self.headers.get("Content-Length", "0") != "0":
                    return self._json(400, {"error": "request body is not supported"})
                code, payload = bluetooth.request("select" if route.endswith("/select") else "scan", mac)
                return self._json(code, payload)
            if self.headers.get("Content-Length", "0") != "0":
                return self._json(400, {"error": "request body is not supported"})
            try:
                if route == "/api/recordings/start":
                    return self._json(200, manager.start())
                if route == "/api/recordings/stop":
                    return self._json(200, manager.stop())
            except RuntimeError as error:
                return self._json(409, {"error": str(error)})
            except OSError as error:
                return self._json(503, {"error": str(error)})
            self.send_error(404)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--source", default="rtsp://127.0.0.1:8554/maix01")
    parser.add_argument("--camera-base-rotation", type=int, choices=(0, 90, 180, 270),
                        default=os.environ.get("CAMERA_BASE_ROTATION", "0"),
                        help="Fixed camera mounting offset in counter-clockwise degrees")
    parser.add_argument("--recordings", type=Path, default=DEFAULT_RECORDINGS)
    parser.add_argument("--recording-mode", choices=("legacy", "multistream"), default="multistream")
    parser.add_argument("--rtsp-transport", choices=("tcp", "udp"), default=os.environ.get("RTSP_TRANSPORT", "udp"))
    parser.add_argument("--talkback-host", required=True, help="MaixCAM IP address for UDP talkback")
    parser.add_argument("--maix-usb-ip", type=ipv4, default=os.environ.get("MAIX_USB_IP") or DEFAULT_USB_IP)
    parser.add_argument("--bind-host", default="127.0.0.1", help="Laptop IP address for the operator page")
    args = parser.parse_args()
    if args.camera_base_rotation not in (0, 90, 180, 270):
        parser.error("CAMERA_BASE_ROTATION must be 0, 90, 180 or 270")
    manager = RecordingManager(args.recordings, args.source, transport=args.rtsp_transport,
                               recording_mode=args.recording_mode, base_rotation=args.camera_base_rotation)
    from .bluetooth_client import CameraBluetoothClient
    bluetooth = CameraBluetoothClient(args.talkback_host)
    talkback = TalkbackRelay((args.talkback_host, 9002), transport=args.rtsp_transport,
                             clock_sync=bluetooth.talkback_clock)
    server = ThreadingHTTPServer((args.bind_host, args.port), make_handler(
        manager, talkback=talkback, bluetooth=bluetooth,
        diagnostics=CameraDiagnostics(args.talkback_host, args.maix_usb_ip)))
    print(f"Operator UI: http://{args.bind_host}:{args.port}/operator_test.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if manager.status()["recording"]:
            manager.stop()
        manager.wait()
        server.server_close()
        if talkback is not None:
            talkback.close()


if __name__ == "__main__":
    main()
