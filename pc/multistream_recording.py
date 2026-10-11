"""PC arrival-clock recording, with independent video and reconnecting audio.

No RTSP audio input is attached to the video process. Continuous PCM staging
files are muxed only after capture, so absent publishers cannot stall video.
"""
import collections
import json
import logging
import math
import subprocess
import threading
import time
from pathlib import Path

LOG = logging.getLogger(__name__)
RATE = 48000
FRAME_SECONDS = 0.02
FRAME_BYTES = 960 * 2
SILENCE = bytes(FRAME_BYTES)
MAX_QUEUE = 5
MAX_AGE = 0.12
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def decoder_command(source):
    return ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-rtsp_transport", "tcp", "-timeout", "2000000",
            "-analyzeduration", "100000", "-probesize", "32768",
            "-max_delay", "100000", "-i", source, "-map", "0:a:0", "-vn",
            "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le",
            "-f", "s16le", "-flush_packets", "1", "pipe:1"]


def video_command(source, transport, epoch, output):
    return ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostats",
            "-copyts", "-rtsp_transport", transport, "-timeout", "5000000",
            "-use_wallclock_as_timestamps", "1", "-analyzeduration", "100000",
            "-probesize", "1000000", "-i", source, "-map", "0:v:0",
            "-c:v", "copy", "-bsf:v", "filter_units=remove_types=0",
            "-output_ts_offset", f"{-epoch:.6f}", "-avoid_negative_ts", "disabled",
            "-f", "matroska", str(output)]


def mux_command(video, worker, operator, output, duration):
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning", "-y",
               "-copyts", "-i", str(video)]
    for audio in (worker, operator):
        command += ["-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", str(audio)]
    # Fixed half-gain per voice bounds the sum even for correlated full-scale
    # input. Limiter also catches resampling/encoding filter overshoot.
    command += ["-filter_complex",
                "[1:a]asplit=2[w][wm];[2:a]asplit=2[o][om];"
                "[wm][om]amix=inputs=2:weights='1 1':normalize=1:dropout_transition=0,"
                "alimiter=limit=0.95:level=0:latency=1[m]",
                "-map", "0:v:0", "-map", "[m]", "-map", "[w]", "-map", "[o]",
                "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-b:a", "96k",
                "-metadata:s:v:0", "title=MaixCAM video",
                "-metadata:s:a:0", "title=Mixed conversation",
                "-metadata:s:a:0", "handler_name=Mixed conversation",
                "-metadata:s:a:1", "title=Worker microphone",
                "-metadata:s:a:1", "handler_name=Worker microphone",
                "-metadata:s:a:2", "title=Operator microphone",
                "-metadata:s:a:2", "handler_name=Operator microphone",
                "-disposition:a:0", "default", "-disposition:a:1", "0",
                "-disposition:a:2", "0", "-t", f"{duration:.6f}",
                "-avoid_negative_ts", "disabled", "-movflags", "+faststart",
                "-f", "mp4", str(output)]
    return command


class AudioSource:
    """Bounded arrival queue. Old data never shifts later speech indefinitely."""
    def __init__(self, source, log_path, spawn=subprocess.Popen, clock=time.monotonic):
        self.source, self.log_path = source, log_path
        self.spawn, self.clock = spawn, clock
        self.lock = threading.Lock()
        self.queue = collections.deque()
        self.cancel = threading.Event()
        self.process = None
        self.thread = None
        self.stats = dict(attempts=0, connections=0, dropped=0, silence_frames=0,
                          audio_frames=0)

    def push(self, pcm, now):
        with self.lock:
            if len(self.queue) >= MAX_QUEUE:
                self.queue.popleft()
                self.stats["dropped"] += 1
            self.queue.append((now, pcm))

    def take(self, now):
        with self.lock:
            while self.queue and now - self.queue[0][0] > MAX_AGE:
                self.queue.popleft()
                self.stats["dropped"] += 1
            if self.queue:
                self.stats["audio_frames"] += 1
                return self.queue.popleft()[1]
            self.stats["silence_frames"] += 1
            return SILENCE

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        with self.log_path.open("ab", buffering=0) as log:
            while not self.cancel.is_set():
                self.stats["attempts"] += 1
                log.write(f"\nDecoder attempt {self.stats['attempts']} at {self.clock():.6f}\n".encode())
                process = None
                try:
                    process = self.spawn(decoder_command(self.source), stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=log, bufsize=0,
                                         creationflags=FLAGS)
                    with self.lock:
                        self.process = process
                    pending = bytearray()
                    connected = False
                    while not self.cancel.is_set():
                        chunk = process.stdout.read(FRAME_BYTES - len(pending))
                        if not chunk:
                            break
                        pending.extend(chunk)
                        if len(pending) == FRAME_BYTES:
                            if not connected:
                                self.stats["connections"] += 1
                                connected = True
                                log.write(f"PCM connected at {self.clock():.6f}\n".encode())
                            self.push(bytes(pending), self.clock())
                            pending.clear()
                except OSError as error:
                    log.write(f"Decoder error: {error}\n".encode())
                finally:
                    if process:
                        terminate(process)
                        process.stdout.close()
                    with self.lock:
                        self.process = None
                        # Never play tail PCM from an old session in a new one.
                        self.queue.clear()
                self.cancel.wait(0.5)

    def close(self):
        self.cancel.set()
        with self.lock:
            process = self.process
        if process:
            terminate(process)
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise RuntimeError("audio decoder failed to stop")


def terminate(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


class MultistreamRecording:
    """Popen-like capture handle; poll stays active throughout finalization."""
    stdin = None

    def __init__(self, output, source, transport="tcp", spawn=subprocess.Popen,
                 clock=time.monotonic, wallclock=time.time):
        self.output, self.spawn = Path(output), spawn
        self.clock, self.wallclock = clock, wallclock
        self.started = clock()
        self.epoch = wallclock()
        self.cancel = threading.Event()
        self.returncode = None
        self.error = None
        self.state = "capturing"
        self.frames = 0
        self.skipped_ticks = 0
        self.staging = self.output.with_suffix(".capture")
        self.staging.mkdir()
        self.video_path = self.staging / "video.mkv"
        self.worker_path = self.staging / "worker.pcm"
        self.operator_path = self.staging / "operator.pcm"
        base = source.rsplit("/", 1)[0]
        self.audio = [AudioSource(base + "/" + name, self.staging / (name + ".log"), spawn, clock)
                      for name in ("headsetmic", "talkback")]
        self.log = self.output.with_suffix(".ffmpeg.log").open("ab", buffering=0)
        self.command = video_command(source, transport, self.epoch, self.video_path)
        self.log.write(("Capture command: " + json.dumps(self.command) + "\n").encode())
        self.video = None
        self.thread = None
        try:
            (self.staging / "manifest.json").write_text(json.dumps({
                "epoch": self.epoch, "monotonic_origin": self.started,
                "sample_rate": RATE, "channels": 1, "format": "s16le",
                "sources": [audio.source for audio in self.audio],
                "video_command": self.command}, indent=2))
            self.video = spawn(self.command,
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=self.log, creationflags=FLAGS)
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        except Exception:
            self.log.close()
            raise

    def poll(self):
        return self.returncode

    def status(self):
        return {"recording_mode": "multistream", "finalizing": self.state == "finalizing",
                "duration_seconds": round(self.frames * FRAME_SECONDS),
                "error": self.error, "audio": [dict(a.stats) for a in self.audio]}

    def stop(self):
        self.state = "finalizing"
        self.cancel.set()

    def wait(self, timeout=None):
        if self.thread:
            self.thread.join(timeout)
            if self.thread.is_alive():
                raise subprocess.TimeoutExpired("recording finalization", timeout)
        return self.returncode

    def _run(self):
        try:
            next_diagnostic = self.started + 5
            for audio in self.audio:
                audio.start()
            with self.worker_path.open("wb") as worker, self.operator_path.open("wb") as operator:
                while not self.cancel.is_set():
                    now = self.clock()
                    # Epoch is a fixed bridge to FFmpeg's wallclock timestamps.
                    # A wallclock step invalidates that bridge; finalize safely.
                    if abs((self.wallclock() - self.epoch) - (now - self.started)) > 0.25:
                        self.error = "PC wall clock changed; capture stopped to preserve alignment"
                        break
                    if self.video.poll() is not None:
                        self.error = "Video capture exited; see FFmpeg log"
                        break
                    target = int((now - self.started) / FRAME_SECONDS)
                    self._write_frames(target, now, worker, operator)
                    if now >= next_diagnostic:
                        self.log.write((json.dumps({"timeline_seconds": self.frames * FRAME_SECONDS,
                                                    "audio": [dict(a.stats) for a in self.audio],
                                                    "scheduler_silence_frames": self.skipped_ticks}) + "\n").encode())
                        next_diagnostic = now + 5
                    self.cancel.wait(max(0, self.started + (self.frames + 1) * FRAME_SECONDS - self.clock()))
                # Extend to the actual stop time (including a fractional frame).
                target = max(1, math.ceil((self.clock() - self.started) / FRAME_SECONDS))
                self._write_frames(target, self.clock(), worker, operator, tail=True)
            self.state = "finalizing"
        except Exception as error:
            self.error = f"Capture failed: {error}"
        finally:
            self.cancel.set()
            for audio in self.audio:
                try:
                    audio.close()
                except Exception as error:
                    self.error = str(error)
            try:
                if self.video.poll() is None:
                    try:
                        self.video.stdin.write(b"q\n")
                        self.video.stdin.flush()
                        self.video.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired):
                        terminate(self.video)
                        self.error = "Video required forced shutdown; staging retained"
                self.video.stdin.close()
                self.state = "finalizing"
                self._finalize()
            except Exception as error:
                self.error = f"Finalization failed: {error}; recover from {self.staging.name}"
                LOG.exception("Multistream recording failed")
                self.returncode = 1
            finally:
                self.log.close()
                self.state = "finished"
                if self.returncode is None:
                    self.returncode = 0

    def _write_frames(self, target, now, worker, operator, tail=False):
        # Scheduler stalls are silence, never a burst of stale speech. The
        # integer frame counter, not accumulated wait durations, defines time.
        while self.frames < target:
            silent = tail or target - self.frames > 1
            for file, audio in zip((worker, operator), self.audio):
                file.write(SILENCE if silent else audio.take(now))
            self.skipped_ticks += int(silent)
            self.frames += 1

    def _finalize(self):
        duration = self.frames * FRAME_SECONDS
        partial = self.output.with_suffix(".partial.mp4")
        command = mux_command(self.video_path, self.worker_path, self.operator_path, partial, duration)
        self.log.write(("\nFinalize command: " + json.dumps(command) + "\n").encode())
        process = self.spawn(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=self.log, creationflags=FLAGS)
        # Offline AAC encoding may take minutes for a long recording; no arbitrary
        # duration timeout and no lock held by the HTTP request while encoding.
        if process.wait() != 0:
            raise RuntimeError("FFmpeg mux/encode failed")
        partial.replace(self.output)
        metadata = {"duration_seconds": duration, "recording_mode": "multistream",
                    "alignment": "PC arrival clock; physical flash/click validation pending",
                    "epoch": self.epoch, "audio": [dict(a.stats) for a in self.audio],
                    "scheduler_silence_frames": self.skipped_ticks, "error": self.error}
        self.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2))
        # Keep diagnostic logs; only remove large staging media after success.
        if self.error is None:
            for path in (self.video_path, self.worker_path, self.operator_path):
                path.unlink()
