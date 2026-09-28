"""Run on MaixCAM: play authenticated PC microphone PCM through BlueALSA."""

import argparse
import hmac
import os
import socket
import subprocess
import time
from pathlib import Path


PAUSE_PATH = Path("/run/air6-mic-paused")
ACK_PATH = Path("/run/air6-mic-paused.ack")


def valid_packet(packet, token):
    if len(packet) < 19 or not hmac.compare_digest(packet[3:19], token):
        return None
    if packet[:3] == b"TB0" and len(packet) == 19:
        return "stop", b""
    if packet[:3] == b"TB1" and 0 < len(packet[19:]) <= 1024 and len(packet[19:]) % 2 == 0:
        return "pcm", packet[19:]
    return None


class TalkbackReceiver:
    def __init__(self, token, bind=("0.0.0.0", 9002), spawn=subprocess.Popen,
                 pause_path=PAUSE_PATH, ack_path=ACK_PATH):
        self.token = token
        self.bind = bind
        self.spawn = spawn
        self.player = None
        self.last_packet = 0.0
        self.pause_path = Path(pause_path)
        self.ack_path = Path(ack_path)

    def _pause_mic(self):
        if self.pause_path.exists():
            return
        self.ack_path.unlink(missing_ok=True)
        self.pause_path.touch()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if self.ack_path.exists():
                return
            time.sleep(0.02)
        self.pause_path.unlink(missing_ok=True)
        raise RuntimeError("Air6 HS microphone did not pause for talkback")

    def _player(self):
        if self.player is None or self.player.poll() is not None:
            self.player = self.spawn(
                ["aplay", "-q", "-D", "bt_output", "-f", "S16_LE", "-r", "8000", "-c", "1"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, bufsize=0,
                env={**os.environ, "HOME": "/root"},
            )
        return self.player

    def stop(self):
        if self.player is not None:
            try:
                self.player.terminate()
                self.player.stdin.close()
                self.player.wait(timeout=0.5)
            except Exception:
                self.player.kill()
                self.player.wait(timeout=2)
            self.player = None
        self.pause_path.unlink(missing_ok=True)
        self.ack_path.unlink(missing_ok=True)

    def serve(self):
        self.stop()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.bind(self.bind)
            udp.settimeout(1)
            print("Talkback listening on UDP", self.bind, flush=True)
            try:
                while True:
                    try:
                        packet, _ = udp.recvfrom(2048)
                    except socket.timeout:
                        if self.player and time.monotonic() - self.last_packet > 2:
                            self.stop()
                        continue
                    payload = valid_packet(packet, self.token)
                    if payload is None:
                        continue
                    kind, pcm = payload
                    if kind == "stop":
                        self.stop()
                        continue
                    self.last_packet = time.monotonic()
                    try:
                        self._pause_mic()
                        self._player().stdin.write(pcm)
                    except (BrokenPipeError, OSError, RuntimeError) as error:
                        print("Talkback playback error:", error, flush=True)
                        self.stop()
            finally:
                self.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", type=Path, default=Path("/root/.talkback_token"))
    parser.add_argument("--port", type=int, default=9002)
    args = parser.parse_args()
    token = bytes.fromhex(args.token.read_text().strip())
    if len(token) != 16:
        raise ValueError("talkback token must contain 32 hex digits")
    TalkbackReceiver(token, bind=("0.0.0.0", args.port)).serve()


if __name__ == "__main__":
    main()
