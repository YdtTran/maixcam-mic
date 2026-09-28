"""Authenticated, small PCM datagrams for operator-to-MaixCAM talkback."""

import socket
import threading


MAX_POST_BYTES = 65536
CHUNK_BYTES = 1024


def make_packet(token, pcm, stop=False):
    if len(token) != 16:
        raise ValueError("talkback token must be 16 bytes")
    return (b"TB0" if stop else b"TB1") + token + pcm


class TalkbackRelay:
    def __init__(self, token, target, udp_socket=None):
        self.token = token
        self.target = target
        self.udp = udp_socket or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.lock = threading.Lock()

    def send_pcm(self, pcm):
        if not pcm or len(pcm) % 2 or len(pcm) > MAX_POST_BYTES:
            raise ValueError("expected 16-bit PCM, at most 65536 bytes")
        with self.lock:
            for offset in range(0, len(pcm), CHUNK_BYTES):
                self.udp.sendto(make_packet(self.token, pcm[offset:offset + CHUNK_BYTES]), self.target)

    def stop(self):
        with self.lock:
            self.udp.sendto(make_packet(self.token, b"", stop=True), self.target)
