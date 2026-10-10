"""Independent PCMU RTP receiver; microphone loss must never stop video."""

import subprocess
import time
from pathlib import Path


def receiver_command(sdp, ffmpeg="ffmpeg"):
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "info", "-nostats",
            "-protocol_whitelist", "file,udp,rtp", "-f", "sdp",
            "-analyzeduration", "0", "-probesize", "32",
            "-max_delay", "100000", "-reorder_queue_size", "16",
            "-i", str(sdp), "-map", "0:a:0", "-c:a", "copy",
            "-flush_packets", "1", "-f", "rtsp", "-rtsp_transport", "tcp",
            "rtsp://127.0.0.1:8554/headsetmic"]


class HeadsetReturn:
    def __init__(self, sdp, runtime, spawn=subprocess.Popen, available=lambda path: False,
                 clock=time.monotonic):
        self.command = receiver_command(sdp)
        self.runtime = Path(runtime)
        self.spawn = spawn
        self.available = available
        self.clock = clock
        self.process = None
        self.log = None
        self.next_retry = 0
        self.delay = 2
        self.started = 0
        self.next_check = 0

    def tick(self):
        now = self.clock()
        if self.process is not None:
            failed = self.process.poll() is not None
            if not failed and now >= self.next_check:
                self.next_check = now + 5
                healthy = self.available("headsetmic")
                if healthy:
                    self.delay = 2
                failed = not healthy and now - self.started >= 15
            if failed:
                self.close()
                self.next_retry = now + self.delay
                print(f"Headset return lost RTP/publication; retry in {self.delay}s", flush=True)
                self.delay = min(30, self.delay * 2)
        if self.process is None and now >= self.next_retry:
            try:
                self.runtime.mkdir(exist_ok=True)
                # Preserve the previous attempt without allowing logs to accumulate.
                logfile = self.runtime / "headset-return.ffmpeg.log"
                if logfile.exists():
                    logfile.replace(self.runtime / "headset-return.previous.log")
                self.log = logfile.open("wb")
                self.process = self.spawn(self.command, stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=self.log,
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.started = now
                self.next_check = now + 5
                print("Headset return listening for PCMU RTP; publishing /headsetmic", flush=True)
            except OSError as error:
                self.close()
                self.next_retry = now + self.delay
                self.delay = min(30, self.delay * 2)
                print(f"Headset return startup failed: {error}", flush=True)

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None
