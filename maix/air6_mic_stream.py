"""Publish selected headset microphone audio, or silence during PC talkback."""

import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

try:
    from .bluetooth_control import SELECTION_PATH, MAC
except ImportError:  # Run directly on MaixCAM.
    from bluetooth_control import SELECTION_PATH, MAC


PAUSE_PATH = Path("/run/air6-mic-paused")
ACK_PATH = Path("/run/air6-mic-paused.ack")
FRAME_BYTES = 320  # 20 ms of signed 16-bit mono PCM at 8 kHz.
SILENCE = bytes(FRAME_BYTES)


def selected_mac(path=SELECTION_PATH):
    try:
        mac = Path(path).read_text().strip().upper()
    except FileNotFoundError:
        return None
    return mac if MAC.fullmatch(mac) else None


def publisher_command(target):
    return [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning",
        "-f", "s16le", "-ar", "8000", "-ac", "1", "-i", "pipe:0",
        "-c:a", "pcm_mulaw", "-f", "rtsp", "-rtsp_transport", "tcp",
        f"rtsp://{target}:8554/air6mic",
    ]


def capture_command(mac):
    return [
        "arecord", "-q", "-D", f"bluealsa:DEV={mac},PROFILE=sco",
        "-t", "raw", "-f", "S16_LE", "-r", "8000", "-c", "1",
    ]


def stop_process(process):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    for stream in (process.stdin, process.stdout):
        if stream is not None:
            stream.close()


def publish_audio(target, selection_path=SELECTION_PATH, pause_path=PAUSE_PATH, ack_path=ACK_PATH):
    publisher = subprocess.Popen(publisher_command(target), stdin=subprocess.PIPE, bufsize=0)
    os.set_blocking(publisher.stdin.fileno(), False)
    capture = None
    pending = bytearray()
    retry_capture_at = 0.0
    next_frame_at = time.monotonic()
    active_mac = None
    next_selection_check = 0.0
    try:
        while publisher.poll() is None:
            now = time.monotonic()
            if now >= next_selection_check:
                next_selection_check = now + 0.5
                current_mac = selected_mac(selection_path)
                if current_mac != active_mac:
                    stop_process(capture)
                    capture = None
                    pending.clear()
                    active_mac = current_mac
            paused = pause_path.exists()
            if paused:
                if capture is not None:
                    stop_process(capture)
                    capture = None
                    pending.clear()
                if not ack_path.exists():
                    ack_path.touch()
            else:
                ack_path.unlink(missing_ok=True)
                if active_mac and capture is None and now >= retry_capture_at:
                    capture = subprocess.Popen(capture_command(active_mac), stdout=subprocess.PIPE,
                                               stderr=subprocess.DEVNULL, bufsize=0,
                                               env={**os.environ, "HOME": "/root"})
                    os.set_blocking(capture.stdout.fileno(), False)
                    retry_capture_at = now + 3

            frame = SILENCE
            if capture is not None:
                if capture.poll() is not None:
                    stop_process(capture)
                    capture = None
                    pending.clear()
                else:
                    try:
                        chunk = os.read(capture.stdout.fileno(), FRAME_BYTES - len(pending))
                        pending.extend(chunk)
                    except BlockingIOError:
                        pass
                    if len(pending) == FRAME_BYTES:
                        frame = bytes(pending)
                        pending.clear()

            try:
                if os.write(publisher.stdin.fileno(), frame) != FRAME_BYTES:
                    raise RuntimeError("audio publisher is not keeping up")
            except (BrokenPipeError, BlockingIOError):
                break
            next_frame_at += 0.02
            if next_frame_at < time.monotonic():
                next_frame_at = time.monotonic()
            time.sleep(max(0, next_frame_at - time.monotonic()))
    finally:
        ack_path.unlink(missing_ok=True)
        stop_process(capture)
        stop_process(publisher)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Windows laptop IP address")
    parser.add_argument("--selection", type=Path, default=SELECTION_PATH)
    args = parser.parse_args()

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    while True:
        try:
            publish_audio(args.target, args.selection)
            print("Headset mic publisher exited; retrying", flush=True)
            time.sleep(3)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
