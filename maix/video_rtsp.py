"""Bounded H.264 RTSP/TCP output for frames encoded by the MaixCAM.

The vendor bound-camera server cannot accept rotated frames (write is not
implemented). This server keeps the same /live and TCP-interleaved RTP contract.
"""
import base64
import queue
import re
import secrets
import select
import socketserver
import struct
import threading
import time


def rotate_nv21(data, width, height):
    """Rotate all Y pixels and VU pairs 90 degrees CCW, without resampling."""
    import numpy as np
    import cv2
    pixels = np.frombuffer(data, dtype=np.uint8)
    y = pixels[:width * height].reshape(height, width)
    vu = pixels[width * height:].reshape(height // 2, width // 2, 2)
    # Materialize using OpenCV's native transpose, avoiding NumPy's slow
    # strided tobytes loop on the camera's RISC-V CPU.
    return (cv2.rotate(y, cv2.ROTATE_90_COUNTERCLOCKWISE).tobytes() +
            cv2.rotate(vu, cv2.ROTATE_90_COUNTERCLOCKWISE).tobytes())


def split_nals(data):
    return [nal for nal in re.split(b"\x00\x00\x00?\x01", data) if nal]


def pad_nv21(data, width=480, height=640, stride=512):
    """Pad hardware input rows; the padding is excluded by the SPS window."""
    import numpy as np
    source = np.frombuffer(data, dtype=np.uint8).reshape(height * 3 // 2, width)
    output = np.empty((height * 3 // 2, stride), dtype=np.uint8)
    output[:height, width:] = 16
    output[height:, width:] = 128
    output[:, :width] = source
    return output.tobytes()


def crop_encoder_padding(nal):
    """Set Main/Baseline SPS display window to exclude 32 padded columns.

    Only the non-picture encoder padding is removed. All 480x640 rotated
    camera pixels remain. Slice NALs are untouched.
    """
    rbsp = nal[1:].replace(b'\x00\x00\x03', b'\x00\x00')
    bits = ''.join(f'{value:08b}' for value in rbsp)
    position = 0
    def read(size):
        nonlocal position
        value = int(bits[position:position + size], 2)
        position += size
        return value
    def ue():
        zeros = 0
        while read(1) == 0:
            zeros += 1
        return (1 << zeros) - 1 + (read(zeros) if zeros else 0)
    def code(value):
        encoded = bin(value + 1)[2:]
        return '0' * (len(encoded) - 1) + encoded
    if read(8) not in (66, 77, 88):
        raise ValueError('Unsupported camera SPS profile')
    read(16)  # constraint flags and level
    ue()  # sequence id
    ue()  # log2_max_frame_num_minus4
    poc = ue()
    if poc == 0:
        ue()
    elif poc == 1:
        read(1)
        ue()
        ue()
        for _ in range(ue()):
            ue()
    ue()  # reference frames
    read(1)
    width = (ue() + 1) * 16
    height_units = ue() + 1
    frame_only = read(1)
    if not frame_only:
        read(1)
    read(1)
    if (width, height_units * 16 * (2 - frame_only)) != (512, 640):
        raise ValueError('Unexpected encoder dimensions')
    start = position
    offsets = [ue() for _ in range(4)] if read(1) else [0, 0, 0, 0]
    offsets[1] = 16  # 4:2:0 crop unit is two luma columns.
    updated = (bits[:start] + '1' + ''.join(code(value) for value in offsets) + bits[position:]).rstrip('0')
    updated += '0' * (-len(updated) % 8)
    raw = bytes(int(updated[i:i + 8], 2) for i in range(0, len(updated), 8))
    escaped = bytearray(nal[:1])
    zeros = 0
    for value in raw:
        if zeros >= 2 and value <= 3:
            escaped.append(3)
            zeros = 0
        escaped.append(value)
        zeros = zeros + 1 if value == 0 else 0
    return bytes(escaped)


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

    def __init__(self, address=("0.0.0.0", 8554), trim_padding=False):
        self.trim_padding = trim_padding
        self.clients = set()
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.sps = self.pps = None
        self.origin = time.monotonic()
        super().__init__(address, VideoClient)

    def publish(self, data):
        nals = split_nals(data)
        if self.trim_padding:
            nals = [crop_encoder_padding(nal) if nal[0] & 31 == 7 else nal for nal in nals]
        for nal in nals:
            if nal[0] & 31 == 7:
                self.sps = nal
            elif nal[0] & 31 == 8:
                self.pps = nal
        if self.sps and self.pps:
            self.ready.set()
        frame = (int((time.monotonic() - self.origin) * 90000) & 0xffffffff, nals)
        with self.lock:
            for client in tuple(self.clients):
                try:
                    client.put_nowait(frame)
                except queue.Full:
                    try:
                        client.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        client.put_nowait(frame)
                    except queue.Full:
                        pass


class VideoClient(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(2)
        self.frames = queue.Queue(maxsize=2)
        self.session = secrets.token_hex(8)
        self.playing = False
        self.channel = 0
        self.seq = secrets.randbits(16)
        self.ssrc = secrets.randbits(32)
        self.packets = self.octets = 0
        self.report_at = 0
        buffer = b""
        try:
            while True:
                if select.select([self.request], [], [], .01)[0]:
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
                        stamp, nals = self.frames.get_nowait()
                    except queue.Empty:
                        continue
                    # Start each reader on a complete keyframe, never midway
                    # through a GOP. Repeat SPS/PPS for robust reconnects.
                    if self.waiting_keyframe:
                        if not any(n[0] & 31 == 5 for n in nals):
                            continue
                        self.waiting_keyframe = False
                        nals = [self.server.sps, self.server.pps, *nals]
                    self.send_frame(stamp, nals)
        except (OSError, ValueError, UnicodeError):
            pass
        finally:
            with self.server.lock:
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
            self.waiting_keyframe = True
            self.playing = True
            with self.server.lock:
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
        for index, nal in enumerate(nals):
            payloads = list(rtp_payloads(nal))
            for part, payload in enumerate(payloads):
                marker = index == len(nals) - 1 and part == len(payloads) - 1
                header = struct.pack("!BBHII", 0x80, 96 | (0x80 if marker else 0), self.seq, stamp, self.ssrc)
                self.interleaved(self.channel, header + payload)
                self.seq = (self.seq + 1) & 65535
                self.packets += 1
                self.octets += len(payload)
        if time.monotonic() >= self.report_at:
            ntp = time.time() + 2208988800
            report = struct.pack("!BBHIIIIII", 0x80, 200, 6, self.ssrc, int(ntp),
                                 int((ntp % 1) * 2**32), stamp,
                                 self.packets & 0xffffffff, self.octets & 0xffffffff)
            self.interleaved(self.channel + 1, report)
            self.report_at = time.monotonic() + 1
