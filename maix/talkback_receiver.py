"""Run on MaixCAM: play authenticated PC microphone PCM through BlueALSA."""

import argparse
import collections
import threading
import os
import socket
import subprocess
import time
from pathlib import Path


PAUSE_PATH = Path("/run/headset-mic-paused")
ACK_PATH = Path("/run/headset-mic-paused.ack")


try:
    from pc.talkback_protocol import decode, JitterBuffer
except ImportError:  # Standalone deployment on MaixCAM.
    from talkback_protocol import decode, JitterBuffer


def valid_packet(packet, token):
    payload = decode(packet, token)
    return payload[:2] if payload else None


class TalkbackReceiver:
    def __init__(self, token, bind=("0.0.0.0", 9002), spawn=subprocess.Popen,
                 pause_path=PAUSE_PATH, ack_path=ACK_PATH):
        self.jitter = JitterBuffer()
        self.lock = threading.Lock()
        self.retired = collections.deque(maxlen=64)
        self.generation = 0
        self.latest_timestamp = 0
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
        raise RuntimeError("headset microphone did not pause for talkback")

    def _player(self):
        if self.player is None or self.player.poll() is not None:
            self.player = self.spawn(
                ["aplay", "-q", "-D", "bt_output", "-f", "S16_LE", "-r", "8000", "-c", "1"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, bufsize=0,
                env={**os.environ, "HOME": "/root"},
            )
            os.set_blocking(self.player.stdin.fileno(), False)
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

    def accept(self, packet, now=None):
        payload = decode(packet, self.token)
        if payload is None:
            return False
        now = time.monotonic() if now is None else now
        kind, pcm, session, sequence, timestamp = payload
        with self.lock:
            if session in self.retired:
                return False
            if self.jitter.session is None and timestamp < self.latest_timestamp:
                return False
            if kind == "stop":
                if sequence <= self.jitter.played or (self.jitter.frames and sequence <= max(self.jitter.frames)):
                    return False
                if self.jitter.session not in (None, session):
                    return False
                self.retired.append(session)
                self.latest_timestamp = max(self.latest_timestamp, timestamp)
                self.jitter.reset()
                self.generation += 1
                self.last_packet = 0
                return True
            if not self.jitter.push(payload, now):
                return False
            self.latest_timestamp = max(self.latest_timestamp, timestamp)
            self.last_packet = now
            return True

    def _playback(self, closing):
        generation = self.generation
        while not closing.wait(0.01):
            with self.lock:
                changed = generation != self.generation
                generation = self.generation
                idle = self.last_packet and time.monotonic() - self.last_packet > 0.5
                if idle:
                    self.retired.append(self.jitter.session)
                    self.jitter.reset()
                    self.last_packet = 0
                pcm = self.jitter.pop(time.monotonic())
            if changed or idle:
                self.stop()
            if pcm is None:
                continue
            try:
                selected_at = time.monotonic()
                self._pause_mic()
                # Profile switching may take seconds: discard that frame and
                # all queued stale audio instead of playing it after the switch.
                with self.lock:
                    if generation != self.generation:
                        self.stop()
                        continue
                    if time.monotonic() - selected_at > 0.12:
                        pcm = self.jitter.pop(time.monotonic())
                if pcm is not None:
                    os.write(self._player().stdin.fileno(), pcm)
            except (BrokenPipeError, BlockingIOError, OSError, RuntimeError) as error:
                print("Talkback playback error:", error, flush=True)
                self.stop()

    def serve(self):
        self.stop()
        closing = threading.Event()
        worker = threading.Thread(target=self._playback, args=(closing,), daemon=True)
        worker.start()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.bind(self.bind)
            udp.settimeout(0.1)
            print("Talkback listening on UDP", self.bind, flush=True)
            try:
                while True:
                    try:
                        packet, _ = udp.recvfrom(2048)
                        self.accept(packet)
                    except socket.timeout:
                        pass
            finally:
                closing.set()
                worker.join(timeout=3)
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
