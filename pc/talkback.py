"""WHIP signaling and bounded WebRTC-to-TB3 UDP talkback relay."""
import collections
import secrets
import socket
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from .talkback_protocol import FRAME_BYTES, encode

MAX_POST_BYTES = 65536
CHUNK_BYTES = FRAME_BYTES


def make_packet(pcm, stop=False, session=0, sequence=0, timestamp=None):
    return encode(pcm, session, sequence, timestamp, stop)


class TalkbackRelay:
    def __init__(self, target, udp_socket=None, spawn=subprocess.Popen,
                 relay_http="http://127.0.0.1:8889", relay_rtsp="rtsp://127.0.0.1:8554", transport="udp",
                 clock_sync=None):
        if transport not in ("tcp", "udp"):
            raise ValueError("RTSP transport must be tcp or udp")
        self.transport = transport
        self.relay_http = relay_http
        self.relay_rtsp = relay_rtsp
        self.target = target
        self.udp = udp_socket or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.control_lock = threading.Lock()
        self.lock = threading.RLock()
        self.spawn = spawn
        self.session = secrets.randbits(64)
        self.sequence = 0
        self.location = None
        self.decoder = None
        self.cancel = threading.Event()
        self.workers = []
        self.queue = collections.deque(maxlen=3)
        self.error = None
        self.clock_sync = clock_sync
        self.timestamp_ms = lambda: int(time.time() * 1000)

    def send_pcm(self, pcm):
        if not pcm or len(pcm) % 2 or len(pcm) > MAX_POST_BYTES:
            raise ValueError("expected 16-bit PCM, at most 65536 bytes")
        with self.lock:
            for offset in range(0, len(pcm), FRAME_BYTES):
                self.udp.sendto(make_packet(pcm[offset:offset + FRAME_BYTES],
                                           session=self.session, sequence=self.sequence,
                                           timestamp=self.timestamp_ms()), self.target)
                self.sequence = (self.sequence + 1) & 0xffffffff

    def offer(self, sdp):
        with self.control_lock, self.lock:
            if self.location:
                raise RuntimeError("talkback is already active")
            if self.clock_sync is not None:
                self.timestamp_ms = self.clock_sync()
            endpoint = self.relay_http + "/talkback/whip"
            request = Request(endpoint, data=sdp.encode(), headers={"Content-Type": "application/sdp"})
            with urlopen(request, timeout=10) as response:
                resource = response.headers.get("Location")
                if not resource:
                    raise RuntimeError("WHIP relay omitted session location")
                location = urljoin(endpoint, resource)
                if urlsplit(location).netloc != urlsplit(self.relay_http).netloc or not urlsplit(location).path.startswith("/talkback/"):
                    raise RuntimeError("invalid WHIP session location")
                answer = response.read(MAX_POST_BYTES).decode()
            self.location = location
            self.session = secrets.randbits(64)
            self.sequence = 0
            self.error = None
            self.cancel = threading.Event()
            self.queue.clear()
            worker = threading.Thread(target=self._decode, args=(self.cancel, self.session), daemon=True)
            sender = threading.Thread(target=self._forward, args=(self.cancel, self.session), daemon=True)
            self.workers = [worker, sender]
            for thread in self.workers:
                thread.start()
            return {"sdp": answer, "session": str(self.session)}

    def _decode(self, cancel, session):
        # WHIP negotiation finishes before ICE media arrives. Retry the RTSP reader.
        deadline = time.monotonic() + 10
        error = None
        try:
            while not cancel.is_set():
                process = self.spawn([
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-rtsp_transport", self.transport, "-timeout", "2000000", "-max_delay", "40000",
                    "-analyzeduration", "100000", "-probesize", "32768",
                    "-i", self.relay_rtsp + "/talkback", "-vn",
                    "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le",
                    "-f", "s16le", "-flush_packets", "1", "-blocksize", "320", "pipe:1",
                ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
                with self.lock:
                    stale = cancel.is_set() or session != self.session
                    if not stale:
                        self.decoder = process
                if stale:
                    self._terminate(process)
                    return
                pending = bytearray()
                while not cancel.is_set():
                    chunk = process.stdout.read(FRAME_BYTES - len(pending))
                    if not chunk:
                        break
                    pending.extend(chunk)
                    if len(pending) == FRAME_BYTES:
                        with self.lock:
                            if not cancel.is_set() and session == self.session:
                                self.queue.append((time.monotonic(), bytes(pending)))
                        pending.clear()
                with self.lock:
                    reap = self.decoder is process
                    if reap:
                        self.decoder = None
                if reap:
                    self._terminate(process)
                if time.monotonic() >= deadline:
                    raise RuntimeError("WebRTC talkback audio interrupted")
                cancel.wait(0.1)
        except Exception as failure:
            if not cancel.is_set():
                error = f"WebRTC talkback audio interrupted; retry Talk ({failure})"
        finally:
            self._retire(session, cancel, error)

    def _forward(self, cancel, session):
        next_send = time.monotonic() + 0.02
        while not cancel.wait(max(0, next_send - time.monotonic())):
            now = time.monotonic()
            next_send += 0.02
            if next_send < now:
                next_send = now + 0.02
            # Absolute deadlines compensate for Windows rounding a 20ms wait
            # to ~31ms. Relative waits underfeed 20ms PCM frames by ~35%.
            with self.lock:
                if session != self.session or cancel.is_set():
                    return
                while self.queue and time.monotonic() - self.queue[0][0] > 0.12:
                    self.queue.popleft()
                if self.queue:
                    _, pcm = self.queue.popleft()
                    self.send_pcm(pcm)

    @staticmethod
    def _terminate(process):
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        if process.stdout:
            process.stdout.close()

    def _send_stop(self, session=None, sequence=None, timestamp_ms=None):
        with self.lock:
            if session is None:
                session, sequence, timestamp_ms = self.session, self.sequence, self.timestamp_ms
                self.sequence = (self.sequence + 1) & 0xffffffff
        packet = make_packet(b"", stop=True, session=session, sequence=sequence,
                             timestamp=timestamp_ms())
        for _ in range(3):
            self.udp.sendto(packet, self.target)

    def stop(self, session=None):
        with self.control_lock:
            self._stop(session)

    def _stop(self, session):
        with self.lock:
            if session is not None and session != str(self.session):
                return
            session, cancel = self.session, self.cancel
        self._retire(session, cancel, acknowledge=True)

    def _retire(self, session, cancel, error=None, acknowledge=False):
        with self.lock:
            if session != self.session or cancel is not self.cancel:
                return
            if acknowledge:
                self.error = None
            if cancel.is_set():
                return
            cancel.set()
            process, location, workers = self.decoder, self.location, self.workers
            sequence, timestamp_ms = self.sequence, self.timestamp_ms
            self.decoder = None
            self.location = None
            self.workers = []
            self.queue.clear()
            self.error = error
        # Ownership is detached before blocking cleanup; retries may now proceed.
        try:
            self._send_stop(session, sequence, timestamp_ms)
        except OSError:
            pass
        try:
            if process:
                self._terminate(process)
        except (OSError, subprocess.TimeoutExpired) as failure:
            with self.lock:
                if session == self.session and not self.error:
                    self.error = f"Talkback decoder cleanup failed: {failure}"
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=3)
        if location:
            try:
                with urlopen(Request(location, method="DELETE"), timeout=3):
                    pass
            except (OSError, HTTPError):
                pass

    def close(self):
        self.stop()
        self.udp.close()
