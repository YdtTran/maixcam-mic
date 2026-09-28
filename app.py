"""Start the Windows MediaMTX relay, MaixCAM publisher, and operator page."""

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
from pc.talkback import TalkbackRelay


ROOT = Path(__file__).resolve().parent


def list_host_processes():
    """Read Windows process paths and command lines, with a path-only fallback."""
    scripts = [
        ("Get-CimInstance Win32_Process -Filter \"Name = 'mediamtx.exe' OR Name = 'ffmpeg.exe'\" "
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


def stop_previous_host(processes, terminate_pid, current_pid=None):
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
                            and "libopus" in command
                            and re.search(r"rtsp://[^\s\"']+:8554/maix01", command))
        if is_own_media or is_own_publisher:
            terminate_pid(pid)
            stopped.append(pid)
    return stopped


def stop_old_processes():
    stopped = stop_previous_host(
        list_host_processes(), lambda pid: os.kill(pid, signal.SIGTERM), os.getpid())
    if stopped:
        print(f"Stopped previous host processes: {', '.join(map(str, stopped))}", flush=True)
        time.sleep(0.2)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maix-ip", default="10.127.15.230", help="MaixCAM IP address")
    parser.add_argument("--bind-host", default="127.0.0.1", help="Operator page bind address")
    parser.add_argument("--port", type=int, default=8000, help="Operator page port")
    parser.add_argument("--recordings", type=Path, default=Path("recordings"))
    parser.add_argument("--talkback-token", type=Path, default=ROOT / ".talkback_token")
    return parser.parse_args(argv)


def publisher_command(maix_ip, ffmpeg="ffmpeg"):
    return [
        ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostats",
        "-rtsp_transport", "tcp", "-analyzeduration", "10000000",
        "-probesize", "20000000", "-i", f"rtsp://{maix_ip}:8554/live",
        "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
        "-bsf:v", "filter_units=remove_types=0,dump_extra=freq=keyframe",
        "-c:a", "libopus", "-ar", "48000", "-ac", "1", "-b:a", "64k",
        "-f", "rtsp", "-rtsp_transport", "tcp",
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


def stop_process(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run(args, spawn=subprocess.Popen, server_factory=ThreadingHTTPServer,
        wait_for_relay=wait_for_relay, stop_existing=stop_old_processes):
    media_exe = ROOT / "mediamtx.exe"
    media_config = ROOT / "mediamtx.yml"
    if not media_exe.is_file() or not media_config.is_file():
        raise RuntimeError("MediaMTX files are missing from the project directory")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not on PATH")
    stop_existing()

    token_path = args.talkback_token
    talkback = None
    if token_path.is_file():
        token = bytes.fromhex(token_path.read_text().strip())
        talkback = TalkbackRelay(token, (args.maix_ip, 9002))

    relay = publisher = server = None
    manager = RecordingManager(args.recordings)
    try:
        relay = spawn([str(media_exe), str(media_config)], cwd=ROOT)
        wait_for_relay(relay)
        publisher = spawn(publisher_command(args.maix_ip), cwd=ROOT)
        server = server_factory((args.bind_host, args.port), make_handler(manager, talkback=talkback))
        server.timeout = 0.5
        print(f"Operator UI: http://{args.bind_host}:{args.port}/operator_test.html", flush=True)
        try:
            while True:
                if relay.poll() is not None:
                    raise RuntimeError("MediaMTX exited")
                if publisher.poll() is not None:
                    raise RuntimeError("FFmpeg publisher exited; check the camera RTSP stream")
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
                talkback.udp.close()


def main():
    try:
        run(parse_args())
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(f"Startup failed: {error}") from error


if __name__ == "__main__":
    main()
