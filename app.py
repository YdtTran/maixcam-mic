"""Start the MediaMTX relay, MaixCAM publisher, and operator page."""

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from pc.operator_server import RecordingManager, make_handler
from pc.bluetooth_client import CameraBluetoothClient
from pc.talkback import TalkbackRelay
from pc.camera_diagnostics import CameraDiagnostics, DEFAULT_USB_IP, ipv4
from pc.check_camera_udp import check_camera


ROOT = Path(__file__).resolve().parent


def media_executable(platform_name=None):
    platform_name = platform_name or os.name
    return ROOT / ("mediamtx.exe" if platform_name == "nt" else "mediamtx")


def list_host_processes():
    """Read Windows process paths and command lines, with a path-only fallback."""
    scripts = [
        ("Get-CimInstance Win32_Process -Filter \"Name = 'mediamtx.exe' OR Name = 'ffmpeg.exe' OR Name = 'python.exe' OR Name = 'pythonw.exe'\" "
         "| Select-Object @{Name='id';Expression={$_.ProcessId}},"
         "@{Name='path';Expression={$_.ExecutablePath}},"
         "@{Name='command_line';Expression={$_.CommandLine}} | ConvertTo-Json -Compress"),
        ("Get-Process -Name mediamtx -ErrorAction SilentlyContinue "
         "| Select-Object @{Name='id';Expression={$_.Id}},"
         "@{Name='path';Expression={$_.Path}} | ConvertTo-Json -Compress"),
    ]
    for script in scripts:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            return json.loads(result.stdout) if result.stdout.strip() else []
    raise RuntimeError("Could not inspect existing MediaMTX processes")


def operator_listener_pids(port=8000):
    result = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("Could not inspect operator port owners")
    pids = set()
    for line in result.stdout.splitlines():
        columns = line.split()
        if (len(columns) == 5 and columns[1].endswith(f":{port}")
                and columns[3].upper() == "LISTENING"):
            pids.add(int(columns[4]))
    return pids


def stop_previous_host(processes, terminate_pid, current_pid=None, operator_pids=()):
    """Stop only this project's relay and its matching FFmpeg publisher."""
    own_media = os.path.normcase(str(ROOT / "mediamtx.exe"))
    stopped = []
    if isinstance(processes, dict):
        processes = [processes]
    for process in processes:
        pid = process["id"]
        if pid == current_pid:
            continue
        path = process.get("path") or ""
        command = process.get("command_line") or ""
        is_own_media = os.path.normcase(path) == own_media
        is_own_publisher = (Path(path).name.lower() == "ffmpeg.exe"
                            and ":8554/live" in command
                            and ("libopus" in command or "filter_units=remove_types=0" in command)
                            and re.search(r"rtsp://[^\s\"']+:8554/maix01", command))
        is_own_operator = (pid in operator_pids
                           and Path(path).name.lower() in ("python.exe", "pythonw.exe")
                           and (re.search(r"(?i)(?:^|[\\/\s])app\.py(?=[\"'\s]|$)", command)
                                or ("pc.operator_server" in command and "/maix01" in command)))
        if is_own_media or is_own_publisher or is_own_operator:
            terminate_pid(pid)
            stopped.append(pid)
    return stopped


def stop_old_processes():
    stopped = stop_previous_host(
        list_host_processes(), lambda pid: os.kill(pid, signal.SIGTERM), os.getpid(),
        operator_listener_pids())
    if stopped:
        print(f"Stopped previous host processes: {', '.join(map(str, stopped))}", flush=True)
        time.sleep(0.2)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maix-ip", default=os.environ.get("MAIX_IP", "192.168.1.7"), help="MaixCAM IP address")
    parser.add_argument("--maix-usb-ip", type=ipv4, default=os.environ.get("MAIX_USB_IP") or DEFAULT_USB_IP,
                        help="Optional MaixCAM USB IPv4 address for diagnostics")
    parser.add_argument("--bind-host", default="127.0.0.1", help="Operator page bind address")
    parser.add_argument("--port", type=int, default=8000, help="Operator page port")
    parser.add_argument("--recordings", type=Path, default=Path("recordings"))
    parser.add_argument("--talkback-token", type=Path, default=ROOT / ".talkback_token")
    parser.add_argument("--rtsp-transport", choices=("tcp", "udp"),
                        default=os.environ.get("RTSP_TRANSPORT", "udp"))
    parser.add_argument("--stream-mode", choices=("video", "audio", "combined"),
                        default=os.environ.get("STREAM_MODE", "combined"))
    parser.add_argument("--headset-rtp-port", type=int, default=os.environ.get("HEADSET_RTP_PORT") or None,
                        help="Receive direct G.711 RTP/UDP instead of /headsetmic")
    args = parser.parse_args(argv)
    if args.rtsp_transport not in ("tcp", "udp") or args.stream_mode not in ("video", "audio", "combined"):
        parser.error("Invalid RTSP_TRANSPORT or STREAM_MODE")
    if args.rtsp_transport == "tcp" and args.headset_rtp_port and args.stream_mode != "video":
        parser.error("TCP audio requires RTSP publication; unset HEADSET_RTP_PORT and omit --headset-rtp-port")
    if args.headset_rtp_port is not None and not (1024 <= args.headset_rtp_port <= 65534 and args.headset_rtp_port % 2 == 0):
        parser.error("--headset-rtp-port must be an even port from 1024 to 65534")
    return args


def headset_sdp(port):
    return ("v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=Headset microphone\r\n"
            f"c=IN IP4 0.0.0.0\r\nt=0 0\r\nm=audio {port} RTP/AVP 0\r\n"
            "a=rtpmap:0 PCMU/8000/1\r\na=recvonly\r\n")


def publisher_command(maix_ip, ffmpeg="ffmpeg", audio_sdp=None, transport="udp", mode="combined"):
    if transport not in ("tcp", "udp") or mode not in ("video", "audio", "combined"):
        raise ValueError("Invalid transport or stream mode")
    if transport == "tcp" and audio_sdp and mode != "video":
        raise ValueError("Direct RTP audio is UDP; TCP mode requires RTSP audio")
    # Larger socket buffers absorb scheduling bursts; the 100 ms RTP deadline
    # still bounds reordering. Keep relay payloads below MediaMTX's UDP limit.
    audio_input = (["-protocol_whitelist", "file,udp,rtp", "-f", "sdp"] if audio_sdp else
                   ["-rtsp_transport", transport, "-timeout", "5000000"])
    audio_input += ["-max_delay", "100000", "-buffer_size", "4194304", "-reorder_queue_size", "128",
                    "-i", str(audio_sdp) if audio_sdp else "rtsp://127.0.0.1:8554/headsetmic"]
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostats",
    ]
    if mode != "audio":
        command += [
            "-rtsp_transport", transport, "-timeout", "5000000", "-max_delay", "100000",
            "-buffer_size", "4194304", "-reorder_queue_size", "512",
            "-fflags", "nobuffer", "-flags", "low_delay",
            "-analyzeduration", "1000000", "-probesize", "1000000",
            "-i", f"rtsp://{maix_ip}:8554/live",
        ]
    if mode != "video":
        command += audio_input
    if mode != "audio":
        command += ["-map", "0:v:0"]
    if mode != "video":
        command += ["-map", "1:a:0" if mode == "combined" else "0:a:0"]
    if mode != "audio":
        command += ["-c:v", "copy",
                    "-bsf:v", "filter_units=remove_types=0,dump_extra=freq=keyframe",
        ]
    if mode != "video":
        command += [
            "-c:a", "libopus", "-application", "lowdelay", "-frame_duration", "20",
            "-ar", "48000", "-ac", "1", "-b:a", "64k",
        ]
    return command + [
        "-f", "rtsp", "-rtsp_transport", transport,
        "-buffer_size", "4194304", "-pkt_size", "1200",
        "rtsp://127.0.0.1:8554/maix01",
    ]


def wait_for_relay(process):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("MediaMTX exited before its RTSP port was ready")
        try:
            with socket.create_connection(("127.0.0.1", 8554), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("MediaMTX did not open RTSP port 8554 within 10 seconds")


def rtsp_path_available(path):
    request = (f"DESCRIBE rtsp://127.0.0.1:8554/{path} RTSP/1.0\r\n"
               "CSeq: 1\r\nAccept: application/sdp\r\n\r\n").encode()
    try:
        with socket.create_connection(("127.0.0.1", 8554), timeout=1) as rtsp:
            rtsp.sendall(request)
            return rtsp.recv(64).startswith(b"RTSP/1.0 200")
    except OSError:
        return False


def wait_for_audio(process):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("MediaMTX exited while waiting for headset microphone")
        if rtsp_path_available("headsetmic"):
            return
        time.sleep(0.5)
    raise RuntimeError("headset microphone did not publish /headsetmic within 30 seconds")


def stop_process(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run(args, spawn=subprocess.Popen, server_factory=ThreadingHTTPServer,
        wait_for_relay=wait_for_relay, wait_for_audio=wait_for_audio,
        stop_existing=None, path_available=rtsp_path_available, camera_probe=check_camera):
    media_exe = media_executable()
    media_config = ROOT / "mediamtx.yml"
    if not media_exe.is_file() or not media_config.is_file():
        raise RuntimeError("MediaMTX files are missing from the project directory")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not on PATH")
    if args.rtsp_transport == "tcp" and args.stream_mode != "audio":
        capability = camera_probe(args.maix_ip, transport="tcp")
        if not capability["verified"]:
            raise RuntimeError("Camera TCP media unverified; UDP configuration retained. "
                               + capability.get("error", "No video packets received"))
        print("Camera TCP-interleaved video packets verified", flush=True)
    if stop_existing is not None:
        stop_existing()
    elif os.name == "nt":
        stop_old_processes()

    token_path = args.talkback_token
    talkback = None
    bluetooth = None
    if token_path.is_file():
        token = bytes.fromhex(token_path.read_text().strip())
        talkback = TalkbackRelay(token, (args.maix_ip, 9002), transport=args.rtsp_transport)
        bluetooth = CameraBluetoothClient(args.maix_ip, token.hex())

    relay = publisher = server = None
    manager = RecordingManager(args.recordings, transport=args.rtsp_transport, mode=args.stream_mode)
    audio_sdp = None
    if args.headset_rtp_port:
        runtime = ROOT / ".runtime"
        runtime.mkdir(exist_ok=True)
        audio_sdp = runtime / "headset.sdp"
        audio_sdp.write_text(headset_sdp(args.headset_rtp_port), encoding="ascii", newline="")
    try:
        relay = spawn([str(media_exe), str(media_config)], cwd=ROOT,
                      env={**os.environ, "MTX_RTSPTRANSPORTS": "udp,tcp"})
        wait_for_relay(relay)
        command = publisher_command(args.maix_ip, audio_sdp=audio_sdp,
                                    transport=args.rtsp_transport, mode=args.stream_mode)
        publisher = spawn(command, cwd=ROOT)
        publisher_started = time.monotonic()
        next_retry_at = publisher_started
        last_health_check = publisher_started
        diagnostics = CameraDiagnostics(args.maix_ip, args.maix_usb_ip)
        server = server_factory((args.bind_host, args.port), make_handler(
            manager, talkback=talkback, bluetooth=bluetooth, diagnostics=diagnostics))
        server.timeout = 0.5
        print(f"Operator UI: http://{args.bind_host}:{args.port}/operator_test.html", flush=True)
        try:
            while True:
                if relay.poll() is not None:
                    raise RuntimeError("MediaMTX exited")
                now = time.monotonic()
                publisher_exited = publisher.poll() is not None
                check_stream = now - publisher_started >= 10 and now - last_health_check >= 2
                if check_stream:
                    last_health_check = now
                if now >= next_retry_at and (publisher_exited or (check_stream and not path_available("maix01"))):
                    print("FFmpeg publisher lost its stream; reconnecting...", flush=True)
                    stop_process(publisher)
                    publisher = spawn(command, cwd=ROOT)
                    publisher_started = time.monotonic()
                    next_retry_at = publisher_started + 2
                    last_health_check = publisher_started
                server.handle_request()
        except KeyboardInterrupt:
            pass
    finally:
        try:
            if manager.status()["recording"]:
                manager.stop()
        finally:
            if server is not None:
                server.server_close()
            stop_process(publisher)
            stop_process(relay)
            if talkback is not None:
                talkback.close()


def main():
    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        run(parse_args())
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(f"Startup failed: {error}") from error


if __name__ == "__main__":
    main()
