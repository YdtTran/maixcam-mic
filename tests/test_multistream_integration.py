"""Opt-in real FFmpeg/MediaMTX tests; isolated ports, no camera or live stack."""
import array
import json
import math
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import app
from pc.operator_server import RecordingManager
from pc.multistream_recording import mux_command


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(command):
    result = subprocess.run(command, capture_output=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr.decode(errors="replace"))
    return result.stdout


def probe(path, *options):
    return json.loads(run(["ffprobe", "-v", "error", *options, "-of", "json", str(path)]))


def samples(path, track, start, duration=.4):
    data = run(["ffmpeg", "-v", "error", "-ss", str(start), "-i", str(path),
                "-t", str(duration), "-map", f"0:a:{track}", "-ac", "1", "-ar", "48000",
                "-f", "f32le", "pipe:1"])
    result = array.array("f")
    result.frombytes(data)
    return result


def tone_level(values, frequency):
    n = len(values)
    return 2 * abs(sum(value * complex(math.cos(2 * math.pi * frequency * i / 48000),
                                      math.sin(2 * math.pi * frequency * i / 48000))
                       for i, value in enumerate(values))) / max(1, n)


def video_slices(path):
    data = run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-c:v", "copy",
                "-bsf:v", "h264_mp4toannexb", "-f", "h264", "pipe:1"])
    return [nal.rstrip(b"\0") for nal in re.split(b"\x00\x00\x00?\x01", data)
            if nal and nal[0] & 31 in (1, 5)]


@unittest.skipUnless(os.environ.get("MULTISTREAM_INTEGRATION") == "1",
                     "set MULTISTREAM_INTEGRATION=1 for isolated media validation")
class MultistreamIntegrationTests(unittest.TestCase):
    def test_late_audio_gaps_two_sessions_and_video_copy(self):
        self.assertIsNotNone(shutil.which("ffmpeg"))
        children = []
        managers = []
        port = free_port()
        base = f"rtsp://127.0.0.1:{port}"
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = directory / "mediamtx.yml"
            config.write_text(f"rtspAddress: 127.0.0.1:{port}\nrtspTransports: [tcp]\n"
                              "webrtc: false\nrtmp: false\nhls: false\nsrt: false\nmoq: false\n"
                              "paths:\n  maix01:\n  headsetmic:\n  talkback:\n")
            log = (directory / "fixture.log").open("wb")
            def spawn(command):
                child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                children.append(child)
                return child
            def await_condition(condition, timeout=8):
                deadline = time.monotonic() + timeout
                while not condition():
                    if time.monotonic() > deadline:
                        self.fail("Timed out waiting for media condition")
                    time.sleep(.05)
            def publish_audio(path, frequency):
                return spawn(["ffmpeg", "-nostdin", "-v", "error", "-re", "-f", "lavfi", "-i",
                              f"sine=frequency={frequency}:sample_rate=48000", "-ac", "1",
                              "-c:a", "libopus", "-frame_duration", "20", "-f", "rtsp",
                              "-rtsp_transport", "tcp", base + "/" + path])
            try:
                spawn([str(app.media_executable()), str(config)])
                time.sleep(.7)
                # Check an absent audio path really terminates an FFmpeg input;
                # optional -map cannot turn a missing input into dynamic silence.
                missing = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-rtsp_transport", "tcp",
                                          "-timeout", "1000000", "-i", base + "/talkback",
                                          "-map", "0:a?", "-t", ".1", "-f", "null", "-"],
                                         capture_output=True, timeout=5)
                self.assertNotEqual(missing.returncode, 0)
                fixture = directory / "source.mp4"
                run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=15",
                     "-t", "2", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                     "-profile:v", "baseline", "-g", "15", str(fixture)])
                video = spawn(["ffmpeg", "-nostdin", "-v", "error", "-re", "-stream_loop", "-1", "-i",
                               str(fixture), "-c:v", "copy", "-an", "-f", "rtsp", "-rtsp_transport", "tcp",
                               base + "/maix01"])
                time.sleep(.7)
                # Legacy fallback remains genuinely playable and video-only.
                legacy = RecordingManager(directory, base + "/maix01", transport="tcp", mode="video")
                managers.append(legacy)
                legacy.start()
                time.sleep(2)
                legacy.stop()
                legacy_file = legacy.recording_path(legacy.list_recordings()[0]["id"])
                self.assertEqual([s["codec_type"] for s in probe(legacy_file, "-show_streams")["streams"]],
                                 ["video"])

                manager = RecordingManager(directory, base + "/maix01", transport="tcp", mode="video",
                                           recording_mode="multistream")
                managers.append(manager)
                active = manager.start()
                capture = manager._process
                recording = manager.recording_path(active["id"])
                time.sleep(1.5)
                self.assertTrue(manager.status()["recording"])
                worker = publish_audio("headsetmic", 440)
                operator = publish_audio("talkback", 880)
                await_condition(lambda: all(a.stats["audio_frames"] > 30 for a in capture.audio))
                both_time = time.monotonic() - capture.started
                time.sleep(.6)
                app.stop_process(operator)
                app.stop_process(worker)
                time.sleep(2)
                gap_time = time.monotonic() - capture.started
                time.sleep(.6)
                self.assertIsNone(video.poll())
                self.assertIsNone(capture.video.poll())
                worker = publish_audio("headsetmic", 440)
                operator = publish_audio("talkback", 880)
                await_condition(lambda: all(a.stats["connections"] >= 2 and a.stats["audio_frames"] > 90
                                            for a in capture.audio))
                second_time = time.monotonic() - capture.started
                time.sleep(.6)
                app.stop_process(operator)
                time.sleep(.5)
                manager.stop()
                manager.wait()
                self.assertIsNone(capture.error, (capture.error, recording.with_suffix(".ffmpeg.log").read_text()))
                streams = probe(recording, "-show_streams")["streams"]
                self.assertEqual([s["codec_name"] for s in streams], ["h264", "aac", "aac", "aac"])
                self.assertEqual([s["sample_rate"] for s in streams[1:]], ["48000"] * 3)
                self.assertEqual([s["tags"]["handler_name"] for s in streams[1:]],
                                 ["Mixed conversation", "Worker microphone", "Operator microphone"])
                self.assertEqual([s["disposition"]["default"] for s in streams[1:]], [1, 0, 0])
                for stream in streams[1:]:
                    self.assertAlmostEqual(float(stream["start_time"]), 0, delta=.025)
                    self.assertAlmostEqual(float(stream["duration"]), capture.frames * .02, delta=.05)
                for track in (0, 1, 2):
                    self.assertLess(max(abs(v) for v in samples(recording, track, .2)), .0001)
                    self.assertLess(max(abs(v) for v in samples(recording, track, gap_time)), .0001)
                for start in (both_time, second_time):
                    mix = samples(recording, 0, start)
                    self.assertGreater(tone_level(mix, 440), .015)
                    self.assertGreater(tone_level(mix, 880), .015)
                    w = samples(recording, 1, start)
                    o = samples(recording, 2, start)
                    self.assertGreater(tone_level(w, 440), .03)
                    self.assertLess(tone_level(w, 880), .003)
                    self.assertGreater(tone_level(o, 880), .03)
                    self.assertLess(tone_level(o, 440), .003)
                # RTSP adds SPS/PPS to keyframes, so compare encoded slice NALs
                # rather than whole AVCC packet hashes across the containers.
                original_slices = set(video_slices(fixture))
                recorded_slices = video_slices(recording)
                self.assertGreater(len(recorded_slices), 30)
                self.assertTrue(all(nal in original_slices for nal in recorded_slices))
                packets = probe(recording, "-select_streams", "v", "-show_packets", "-show_data_hash",
                                "sha256")["packets"]
                self.assertGreater(len(packets), 30)
                pts = [float(p["pts_time"]) for p in packets]
                self.assertTrue(all(b >= a for a, b in zip(pts, pts[1:])))
                self.assertGreaterEqual(pts[0], 0)
                self.assertLess(pts[0], 2)
                run(["ffmpeg", "-v", "error", "-i", str(recording), "-map", "0", "-f", "null", "-"])
                # A failed video input ends capture and finalizes automatically;
                # diagnostics and staging survive rather than an active zombie.
                app.stop_process(worker)
                failed = RecordingManager(directory, base + "/maix01", transport="tcp", mode="video",
                                          recording_mode="multistream")
                managers.append(failed)
                failed_status = failed.start()
                failed_capture = failed._process
                time.sleep(2)
                app.stop_process(video)
                await_condition(lambda: failed_capture.poll() is not None, timeout=15)
                failed.wait()
                self.assertIn("Video capture exited", failed.status()["error"])
                failed_path = failed.recording_path(failed_status["id"])
                self.assertEqual(len(probe(failed_path, "-show_streams")["streams"]), 4)
                self.assertTrue(failed_capture.video_path.exists())
                print("Multistream: late inputs, gaps, two sessions, four tracks, copied H.264 and decode OK")
            finally:
                for manager in managers:
                    if manager.status()["recording"]:
                        manager.stop()
                    manager.wait()
                for child in reversed(children):
                    app.stop_process(child)
                log.close()

    def test_correlated_full_scale_voices_do_not_clip_mix(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            video = directory / "video.mp4"
            pcm = directory / "voice.pcm"
            output = directory / "out.mp4"
            run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=15",
                 "-t", "1", "-c:v", "libx264", "-preset", "ultrafast", str(video)])
            values = array.array("h", (int(32767 * math.sin(2 * math.pi * 440 * i / 48000))
                                       for i in range(48000)))
            pcm.write_bytes(values.tobytes())
            run(mux_command(video, pcm, pcm, output, 1))
            mixed = samples(output, 0, .2)
            self.assertGreater(tone_level(mixed, 440), .9)
            self.assertLess(max(abs(v) for v in mixed), 1)


if __name__ == "__main__":
    unittest.main()
