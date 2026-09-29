"""Loopback operator UI and an FFmpeg recorder for the existing /maix01 relay."""

import argparse
import json
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


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
DEFAULT_RECORDINGS = Path("recordings")
RECORDING_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")


class RecordingManager:
    def __init__(self, directory=DEFAULT_RECORDINGS, source="rtsp://127.0.0.1:8554/maix01", spawn=subprocess.Popen):
        directory = Path(directory)
        self.directory = directory if directory.is_absolute() else PROJECT_ROOT / directory
        self.source = source
        self.spawn = spawn
        self._lock = threading.RLock()
        self._process = None
        self._recording_id = None
        self._started = None
        self._log = None

    def _refresh(self):
        if self._process is not None and self._process.poll() is not None:
            self._close_process()

    def _close_process(self):
        if self._process and self._process.stdin:
            self._process.stdin.close()
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
            return {
                "recording": self._process is not None,
                "id": self._recording_id,
                "duration_seconds": round(time.monotonic() - self._started) if self._started else 0,
                "size_bytes": path.stat().st_size if path and path.exists() else 0,
                "path": display_path,
            }

    def start(self):
        with self._lock:
            self._refresh()
            if self._process is not None:
                raise RuntimeError("recording is already active")
            self.directory.mkdir(parents=True, exist_ok=True)
            recording_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
            output = self.recording_path(recording_id)
            log = output.with_suffix(".ffmpeg.log").open("wb")
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostats",
                "-rtsp_transport", "tcp", "-analyzeduration", "10000000",
                "-probesize", "20000000", "-i", self.source,
                "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
                "-bsf:v", "filter_units=remove_types=0",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                "-f", "mp4", str(output),
            ]
            try:
                process = self.spawn(
                    command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                log.close()
                raise
            self._process = process
            self._recording_id = recording_id
            self._started = time.monotonic()
            self._log = log
            return self.status()

    def stop(self):
        with self._lock:
            self._refresh()
            if self._process is None:
                raise RuntimeError("recording is not active")
            process = self._process
            output = self.recording_path(self._recording_id)
            duration = round(time.monotonic() - self._started)
            try:
                process.stdin.write(b"q\n")
                process.stdin.flush()
                process.wait(timeout=10)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=3)
            finally:
                self._close_process()
            if output.is_file() and output.stat().st_size:
                output.with_suffix(".json").write_text(json.dumps({"duration_seconds": duration}))
            return self.status()

    def recording_path(self, recording_id):
        if not recording_id or not RECORDING_ID.fullmatch(recording_id):
            raise ValueError("invalid recording id")
        return self.directory / (recording_id + ".mp4")

    def list_recordings(self):
        with self._lock:
            self._refresh()
            if not self.directory.exists():
                return []
            recordings = []
            for path in sorted(self.directory.glob("*.mp4"), reverse=True):
                if not RECORDING_ID.fullmatch(path.stem) or path.stat().st_size == 0:
                    continue
                duration = 0
                metadata = path.with_suffix(".json")
                if metadata.is_file():
                    try:
                        duration = max(0, int(json.loads(metadata.read_text()).get("duration_seconds", 0)))
                    except (ValueError, TypeError, OSError):
                        pass
                recordings.append({
                    "id": path.stem,
                    "size_bytes": path.stat().st_size,
                    "created_at": datetime.strptime(path.stem[:16], "%Y%m%dT%H%M%SZ").isoformat() + "Z",
                    "active": path.stem == self._recording_id,
                    "duration_seconds": round(time.monotonic() - self._started) if path.stem == self._recording_id else duration,
                    "url": "/api/recordings/" + path.stem + "/file",
                })
            return recordings


def make_handler(manager, html_path=APP_DIR / "operator_test.html", talkback=None, bluetooth=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format_string, *args):
            if self.path.startswith("/api/talkback/audio"):
                return
            super().log_message(format_string, *args)

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
            if route in ("/", "/operator_test.html"):
                return self._file(Path(html_path), "text/html; charset=utf-8")
            if route == "/api/recordings/status":
                return self._json(200, manager.status())
            if route == "/api/recordings":
                return self._json(200, manager.list_recordings())
            if route == "/api/talkback/status":
                return self._json(200, {"available": talkback is not None})
            if route == "/api/bluetooth/status":
                if bluetooth is None:
                    return self._json(503, {"error": "Bluetooth control is not configured"})
                code, payload = bluetooth.request("status")
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
            if route == "/api/talkback/audio":
                if talkback is None:
                    return self._json(503, {"error": "talkback is not configured"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    return self._json(400, {"error": "invalid content length"})
                if size <= 0 or size > MAX_POST_BYTES:
                    return self._json(400, {"error": "invalid audio size"})
                try:
                    talkback.send_pcm(self.rfile.read(size))
                except ValueError as error:
                    return self._json(400, {"error": str(error)})
                return self._json(200, {"sent": True})
            if route == "/api/talkback/stop":
                if talkback is None:
                    return self._json(503, {"error": "talkback is not configured"})
                talkback.stop()
                return self._json(200, {"stopped": True})
            if route in ("/api/bluetooth/scan", "/api/bluetooth/select"):
                if bluetooth is None:
                    return self._json(503, {"error": "Bluetooth control is not configured"})
                mac = None
                if route.endswith("/select"):
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                        if size < 1 or size > 256:
                            raise ValueError("invalid selection body")
                        mac = json.loads(self.rfile.read(size)).get("mac")
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
    parser.add_argument("--recordings", type=Path, default=DEFAULT_RECORDINGS)
    parser.add_argument("--talkback-host", required=True, help="MaixCAM IP address for UDP talkback")
    parser.add_argument("--bind-host", default="127.0.0.1", help="Laptop IP address for the operator page")
    parser.add_argument("--talkback-token", type=Path, default=PROJECT_ROOT / ".talkback_token")
    args = parser.parse_args()
    manager = RecordingManager(args.recordings, args.source)
    talkback = None
    if args.talkback_token.is_file():
        token = bytes.fromhex(args.talkback_token.read_text().strip())
        talkback = TalkbackRelay(token, (args.talkback_host, 9002))
    from .bluetooth_client import CameraBluetoothClient
    bluetooth = CameraBluetoothClient(args.talkback_host, token.hex()) if talkback else None
    server = ThreadingHTTPServer((args.bind_host, args.port), make_handler(manager, talkback=talkback, bluetooth=bluetooth))
    print(f"Operator UI: http://{args.bind_host}:{args.port}/operator_test.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if manager.status()["recording"]:
            manager.stop()
        server.server_close()


if __name__ == "__main__":
    main()
