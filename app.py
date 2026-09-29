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
                            and "libopus" in command
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
    parser.add_argument("--maix-ip", default="10.127.15.230", help="MaixCAM IP address")
    parser.add_argument("--bind-host", default="127.0.0.1", help="Operator page bind address")
    parser.add_argument("--port", type=int, default=8000, help="Operator page port")
    parser.add_argument("--recordings", type=Path, default=Path("recordings"))
    parser.add_argument("--talkback-token", type=Path, default=ROOT / ".talkback_token")
    return parser.parse_args(argv)


def publisher_command(maix_ip, ffmpeg="ffmpeg"):
    return [
        ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostats",
        "-rtsp_transport", "tcp",
        "-fflags", "nobuffer", "-flags", "low_delay",
        "-analyzeduration", "1000000", "-probesize", "1000000",
        "-i", f"rtsp://{maix_ip}:8554/live",
        "-rtsp_transport", "tcp",
        "-i", "rtsp://127.0.0.1:8554/air6mic",
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
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
            raise RuntimeError("MediaMTX exited while waiting for Air6 HS microphone")
        if rtsp_path_available("air6mic"):
            return
        time.sleep(0.5)
    raise RuntimeError("Air6 HS microphone did not publish /air6mic within 30 seconds")


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
        stop_existing=None, path_available=rtsp_path_available):
    media_exe = media_executable()
    media_config = ROOT / "mediamtx.yml"
    if not media_exe.is_file() or not media_config.is_file():
        raise RuntimeError("MediaMTX files are missing from the project directory")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not on PATH")
    if stop_existing is not None:
        stop_existing()
    elif os.name == "nt":
        stop_old_processes()

    token_path = args.talkback_token
    talkback = None
    bluetooth = None
    if token_path.is_file():
        token = bytes.fromhex(token_path.read_text().strip())
        talkback = TalkbackRelay(token, (args.maix_ip, 9002))
        bluetooth = CameraBluetoothClient(args.maix_ip, token.hex())

    relay = publisher = server = None
    manager = RecordingManager(args.recordings)
    try:
        relay = spawn([str(media_exe), str(media_config)], cwd=ROOT)
        wait_for_relay(relay)
        print("Waiting for Air6 HS microphone stream...", flush=True)
        wait_for_audio(relay)
        publisher = spawn(publisher_command(args.maix_ip), cwd=ROOT)
        publisher_started = time.monotonic()
        last_health_check = publisher_started
        server = server_factory((args.bind_host, args.port), make_handler(manager, talkback=talkback, bluetooth=bluetooth))
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
                if publisher_exited or (check_stream and not path_available("maix01")):
                    print("FFmpeg publisher lost its stream; reconnecting...", flush=True)
                    stop_process(publisher)
                    wait_for_audio(relay)
                    publisher = spawn(publisher_command(args.maix_ip), cwd=ROOT)
                    publisher_started = time.monotonic()
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
                talkback.udp.close()


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
