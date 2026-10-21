"""TB3: token-free PCM16/8kHz/mono frames, at most 20ms per datagram.

Deploy this same module beside talkback_receiver.py on MaixCAM.
"""
import struct
import time

PROTOCOL_VERSION = "TB3"
FRAME_BYTES = 320
HEADER = struct.Struct("!3sBQIQ")  # magic, stop, session, sequence, UTC milliseconds
MAX_AGE_MS = 2000  # Camera and PC clocks must be synchronized.


def encode(pcm, session, sequence, timestamp=None, stop=False):
    if (stop and pcm) or (not stop and (not pcm or len(pcm) > FRAME_BYTES or len(pcm) % 2)):
        raise ValueError("expected at most 20 ms of PCM16")
    header = HEADER.pack(b"TB3", int(stop), session, sequence,
                         int(time.time() * 1000) if timestamp is None else timestamp)
    return header + pcm


def decode(packet, now_ms=None):
    if len(packet) < HEADER.size or len(packet) > HEADER.size + FRAME_BYTES:
        return None
    magic, stop, session, sequence, timestamp = HEADER.unpack(packet[:HEADER.size])
    pcm = packet[HEADER.size:]
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if magic != b"TB3" or stop not in (0, 1) or abs(now_ms - timestamp) > MAX_AGE_MS:
        return None
    if (stop and pcm) or (not stop and (not pcm or len(pcm) % 2)):
        return None
    return ("stop" if stop else "pcm", pcm, session, sequence, timestamp)


class JitterBuffer:
    """40ms reorder window; cap at six frames and drop audio over 120ms late."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.session = None
        self.played = -1
        self.frames = {}
        self.origin = None

    def push(self, payload, now):
        kind, pcm, session, sequence, timestamp = payload
        if self.session is None:
            self.session = session
            self.origin = now - timestamp / 1000
        if session != self.session or sequence <= self.played or sequence in self.frames:
            return False
        due = self.origin + timestamp / 1000 + 0.04
        if now - due > 0.12 or due - now > 0.16:
            return False
        self.frames[sequence] = (due, pcm)
        while len(self.frames) > 6:
            del self.frames[min(self.frames)]
        return True

    def pop(self, now):
        while self.frames:
            sequence = min(self.frames)
            due, pcm = self.frames[sequence]
            if due > now:
                return None
            del self.frames[sequence]
            self.played = sequence
            if now - due <= 0.12:
                return pcm
        return None
