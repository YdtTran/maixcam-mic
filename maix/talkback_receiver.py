"""Run on MaixCAM: play authenticated PC microphone PCM through BlueALSA."""

import argparse
import hmac
import os
import socket
import subprocess
import time
from pathlib import Path


def valid_packet(packet, token):
    if len(packet) < 19 or not hmac.compare_digest(packet[3:19], token):
        return None
    if packet[:3] == b"TB0" and len(packet) == 19:
        return "stop", b""
    if packet[:3] == b"TB1" and 0 < len(packet[19:]) <= 1024 and len(packet[19:]) % 2 == 0:
        return "pcm", packet[19:]
    return None


def mono_to_stereo(pcm):
    return b"".join(pcm[index:index + 2] * 2 for index in range(0, len(pcm), 2))


class TalkbackReceiver:
    def __init__(self, token, bind=("0.0.0.0", 9002), spawn=subprocess.Popen):
        self.token = token
        self.bind = bind
        self.spawn = spawn
        self.player = None
        self.last_packet = 0.0

    def _player(self):
        if self.player is None or self.player.poll() is not None:
            self.player = self.spawn(
                ["aplay", "-q", "-D", "bt_output", "-f", "S16_LE", "-r", "48000", "-c", "2"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, bufsize=0,
                env={**os.environ, "HOME": "/root"},
            )
        return self.player

    def stop(self):
        if self.player is None:
            return
        try:
            self.player.stdin.close()
            self.player.wait(timeout=5)
        except Exception:
            self.player.kill()
            self.player.wait(timeout=2)
        self.player = None

    def serve(self):
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
                        self._player().stdin.write(mono_to_stereo(pcm))
                    except (BrokenPipeError, OSError):
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
