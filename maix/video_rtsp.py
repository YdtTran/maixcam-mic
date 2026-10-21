"""Bounded H.264 RTSP/TCP output for frames encoded by the MaixCAM.

The vendor bound-camera server cannot accept rotated frames (write is not
implemented). This server keeps the same /live and TCP-interleaved RTP contract.
"""
import base64
import queue
import re
import secrets
import select
import socket
import socketserver
import struct
import threading
import time


def rotate_nv21(data, width, height, destination=None):
    """Rotate NV21 90 CCW, optionally reusing a caller-owned bytearray."""
    import numpy as np
    import cv2
    pixels = np.frombuffer(data, dtype=np.uint8)
    y = pixels[:width * height].reshape(height, width)
    vu = pixels[width * height:].reshape(height // 2, width // 2, 2)
    if destination is None:
        destination = bytearray(width * height * 3 // 2)
    output = np.frombuffer(destination, dtype=np.uint8)
    cv2.rotate(y, cv2.ROTATE_90_COUNTERCLOCKWISE,
               dst=output[:width * height].reshape(width, height))
    cv2.rotate(vu, cv2.ROTATE_90_COUNTERCLOCKWISE,
               dst=output[width * height:].reshape(width // 2, height // 2, 2))
    return bytes(destination)


def split_nals(data):
    view = memoryview(data)
    nals = []
    start = 0
    offset = data.find(b'\x00\x00\x01')
    while offset >= 0:
        boundary = offset - 1 if offset > start and data[offset - 1] == 0 else offset
        if boundary > start:
            nals.append(view[start:boundary])
        start = offset + 3
        offset = data.find(b'\x00\x00\x01', start)
    if start < len(data):
        nals.append(view[start:])
    return nals


def rtp_payloads(nal, limit=1200):
    if len(nal) <= limit:
        yield nal
        return
    indicator = (nal[0] & 0xe0) | 28
    kind = nal[0] & 31
    for offset in range(1, len(nal), limit - 2):
        end = min(offset + limit - 2, len(nal))
        header = kind | (0x80 if offset == 1 else 0) | (0x40 if end == len(nal) else 0)
        yield bytes((indicator, header)) + nal[offset:end]


class VideoServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address=("0.0.0.0", 8554)):
        self.clients = set()
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.sps = self.pps = None
        self.origin = time.monotonic()
        super().__init__(address, VideoClient)

    def publish(self, data):
        nals = split_nals(data)
        for nal in nals:
            if nal[0] & 31 == 7:
                self.sps = bytes(nal)
            elif nal[0] & 31 == 8:
                self.pps = bytes(nal)
        if self.sps and self.pps:
            self.ready.set()
        frame = (int((time.monotonic() - self.origin) * 90000) & 0xffffffff, nals)
        with self.lock:
            for client in tuple(self.clients):
                frames = getattr(client, "frames", client)
                try:
                    frames.put_nowait(frame)
                except queue.Full:
                    try:
                        frames.get_nowait()
                    except queue.Empty:
                        pass
                    if hasattr(client, "waiting_keyframe"):
                        client.waiting_keyframe = True
                    try:
                        frames.put_nowait(frame)
                    except queue.Full:
                        pass


class VideoClient(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (OSError, AttributeError):
            pass
        try:
            self.request.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        except (OSError, AttributeError):
            pass
        self.request.settimeout(2)
        self.frames = queue.Queue(maxsize=2)
        self.session = secrets.token_hex(8)
        self.playing = False
        self.waiting_keyframe = True
        self.channel = 0
        self.seq = secrets.randbits(16)
        self.ssrc = secrets.randbits(32)
        self.packets = self.octets = 0
        self.report_at = 0
        buffer = b""
        try:
            while True:
                if select.select([self.request], [], [], 0 if self.playing else .2)[0]:
                    data = self.request.recv(65536)
                    if not data:
                        break
                    buffer += data
                    if len(buffer) > 65536:
                        break
                    while buffer:
                        if buffer[0] == 36:  # Consume interleaved RTCP feedback.
                            if len(buffer) < 4:
                                break
                            size = struct.unpack("!H", buffer[2:4])[0] + 4
                            if len(buffer) < size:
                                break
                            buffer = buffer[size:]
                            continue
                        boundary = buffer.find(b"\r\n\r\n")
                        if boundary < 0:
                            break
                        header = buffer[:boundary].decode("ascii")
                        lines = header.split("\r\n")
                        method, url, _ = lines[0].split(" ", 2)
                        headers = dict(line.split(":", 1) for line in lines[1:])
                        headers = {k.lower(): v.strip() for k, v in headers.items()}
                        size = int(headers.get("content-length", "0"))
                        if size < 0 or size > 65536:
                            return
                        total = boundary + 4 + size
                        if len(buffer) < total:
                            break
                        buffer = buffer[total:]
                        if not self.control(method, url, headers):
                            return
                if self.playing:
                    try:
                        stamp, nals = self.frames.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    # Start each reader on a complete keyframe, never midway
                    # through a GOP. Repeat SPS/PPS for robust reconnects.
                    if self.waiting_keyframe:
                        if not any(n[0] & 31 == 5 for n in nals):
                            continue
                        self.waiting_keyframe = False
                        header = [n for n in (self.server.sps, self.server.pps) if n]
                        nals = header + list(nals)
                    self.send_frame(stamp, nals)
        except (OSError, ValueError, UnicodeError):
            pass
        finally:
            with self.server.lock:
                self.server.clients.discard(self)
                self.server.clients.discard(self.frames)

    def reply(self, headers, status="200 OK", body=b"", extra=""):
        response = (f"RTSP/1.0 {status}\r\nCSeq: {headers.get('cseq', '0')}\r\n"
                    f"Session: {self.session}\r\n{extra}Content-Length: {len(body)}\r\n\r\n")
        self.request.sendall(response.encode("ascii") + body)

    def control(self, method, url, headers):
        if method == "OPTIONS":
            self.reply(headers, extra="Public: OPTIONS, DESCRIBE, SETUP, PLAY, GET_PARAMETER, TEARDOWN\r\n")
        elif method == "DESCRIBE":
            if not self.server.ready.wait(3):
                self.reply(headers, "503 Service Unavailable")
                return False
            sps, pps = self.server.sps, self.server.pps
            body = ("v=0\r\no=- 0 0 IN IP4 0.0.0.0\r\ns=MaixCAM\r\nc=IN IP4 0.0.0.0\r\n"
                    "t=0 0\r\na=control:*\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\n"
                    f"a=fmtp:96 packetization-mode=1;profile-level-id={sps[1:4].hex()};"
                    f"sprop-parameter-sets={base64.b64encode(sps).decode()},{base64.b64encode(pps).decode()}\r\n"
                    "a=control:trackID=0\r\n").encode("ascii")
            self.reply(headers, body=body, extra=f"Content-Type: application/sdp\r\nContent-Base: {url.rstrip('/')}/\r\n")
        elif method == "SETUP":
            transport = headers.get("transport", "")
            match = re.search(r"interleaved=(\d+)-(\d+)", transport)
            if "RTP/AVP/TCP" not in transport or not match or not 0 <= int(match[1]) < 255:
                self.reply(headers, "461 Unsupported Transport")
                return False
            self.channel = int(match[1])
            self.reply(headers, extra=f"Transport: RTP/AVP/TCP;unicast;interleaved={self.channel}-{self.channel + 1}\r\n")
        elif method == "PLAY":
            self.reply(headers)
            try:
                self.request.settimeout(10.0)
            except (OSError, AttributeError):
                pass
            self.waiting_keyframe = True
            self.playing = True
            with self.server.lock:
                self.server.clients.add(self)
                if hasattr(self, "frames"):
                    self.server.clients.add(self.frames)
        elif method == "GET_PARAMETER":
            self.reply(headers)
        elif method == "TEARDOWN":
            self.reply(headers)
            return False
        else:
            self.reply(headers, "405 Method Not Allowed")
        return True

    def interleaved(self, channel, data):
        self.request.sendall(struct.pack("!BBH", 36, channel, len(data)) + data)

    def send_frame(self, stamp, nals):
        packets = bytearray()
        for index, nal in enumerate(nals):
            payloads = list(rtp_payloads(nal))
            for part, payload in enumerate(payloads):
                marker = index == len(nals) - 1 and part == len(payloads) - 1
                header = struct.pack("!BBHII", 0x80, 96 | (0x80 if marker else 0), self.seq, stamp, self.ssrc)
                payload_data = header + payload
                packets += struct.pack("!BBH", 36, self.channel, len(payload_data))
                packets += payload_data
                self.seq = (self.seq + 1) & 65535
                self.packets += 1
                self.octets += len(payload)
        if time.monotonic() >= self.report_at:
            ntp = time.time() + 2208988800
            report = struct.pack("!BBHIIIIII", 0x80, 200, 6, self.ssrc, int(ntp),
                                 int((ntp % 1) * 2**32), stamp,
                                 self.packets & 0xffffffff, self.octets & 0xffffffff)
            packets += struct.pack("!BBH", 36, self.channel + 1, len(report))
            packets += report
            self.report_at = time.monotonic() + 1
        if packets:
            self.request.sendall(packets)
