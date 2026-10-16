import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pc.multistream_recording import AudioSource, FRAME_BYTES, SILENCE, MultistreamRecording
from pc.operator_server import RecordingManager


class MultistreamTests(unittest.TestCase):
    def test_gap_stale_frames_and_overflow_cannot_delay_new_speech(self):
        source = AudioSource("unused", Path("unused"))
        self.assertEqual(source.take(0), SILENCE)
        source.push(b"a" * FRAME_BYTES, 1)
        self.assertEqual(source.take(1.13), SILENCE)
        for i in range(10):
            source.push(bytes([i]) * FRAME_BYTES, 2)
        self.assertEqual(len(source.queue), 5)
        self.assertEqual(source.take(2.02), bytes([5]) * FRAME_BYTES)
        self.assertEqual(source.stats["dropped"], 6)

    def test_scheduler_stall_fills_exact_sample_timeline_and_drift_stays_bounded(self):
        recording = MultistreamRecording.__new__(MultistreamRecording)
        recording.frames = recording.skipped_ticks = 0
        recording.audio = [AudioSource("unused", Path("unused")) for _ in range(2)]
        files = [io.BytesIO(), io.BytesIO()]
        # Five seconds of delayed producer output cannot shift the recording
        # clock. Catch-up is silence; only the current tick may consume audio.
        for audio in recording.audio:
            for i in range(250):
                audio.push(b"x" * FRAME_BYTES, 5)
        recording._write_frames(250, 5, *files)
        self.assertEqual(recording.frames, 250)
        self.assertEqual(recording.skipped_ticks, 249)
        self.assertEqual(files[0].getvalue()[:249 * FRAME_BYTES], SILENCE * 249)
        for frame in range(251, 1001):
            for audio in recording.audio:
                # A producer running 2% fast periodically overfills the bounded
                # queue; sample count still follows the coordinator exclusively.
                audio.push(b"x" * FRAME_BYTES, frame * .02)
                if frame % 50 == 0:
                    audio.push(b"x" * FRAME_BYTES, frame * .02)
            recording._write_frames(frame, frame * .02, *files)
        self.assertEqual(len(files[0].getvalue()), 20 * 48000 * 2)
        self.assertTrue(all(len(a.queue) <= 5 for a in recording.audio))
        self.assertGreater(recording.audio[0].stats["dropped"], 0)

    def test_decoder_reopens_and_handles_partial_pcm_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            attempts = []
            source = AudioSource("rtsp://unused/talkback", Path(directory) / "audio.log")
            def spawn(*args, **kwargs):
                attempts.append(args[0])
                process = Mock()
                process.poll.return_value = 0
                if len(attempts) == 1:
                    process.stdout = io.BytesIO(b"")
                else:
                    process.stdout = Mock()
                    chunks = iter((b"a" * 17, b"a" * (FRAME_BYTES - 17), b""))
                    def read(size):
                        data = next(chunks)
                        if not data:
                            source.cancel.set()
                        return data
                    process.stdout.read.side_effect = read
                return process
            source.spawn = spawn
            source.start()
            source.thread.join(3)
            self.assertFalse(source.thread.is_alive())
            self.assertEqual(source.stats["connections"], 1)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(len(source.queue), 0)
            self.assertIn("48000", attempts[0])

    def test_finalize_failure_retains_staging_and_does_not_publish_mp4(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "recording.mp4"
            video = Mock()
            video.poll.return_value = None
            mux = Mock()
            mux.wait.return_value = 1
            with patch.object(AudioSource, "start"), patch.object(AudioSource, "close"), self.assertLogs("pc.multistream_recording", "ERROR"):
                recording = MultistreamRecording(output, "rtsp://localhost/maix01",
                                                 spawn=Mock(side_effect=[video, mux]))
                time.sleep(.06)
                recording.stop()
                recording.wait(5)
            self.assertEqual(recording.poll(), 1)
            self.assertIn("Finalization failed", recording.error)
            self.assertTrue(recording.worker_path.exists())
            self.assertFalse(output.exists())

    def test_wallclock_jump_stops_capture_without_rebasing_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            wall = Mock(side_effect=[1000, 1001])
            video = Mock()
            video.poll.return_value = None
            with patch.object(AudioSource, "start"), patch.object(AudioSource, "close"), \
                    patch.object(MultistreamRecording, "_finalize"):
                recording = MultistreamRecording(Path(directory) / "out.mp4", "rtsp://localhost/maix01",
                                                 spawn=Mock(return_value=video), wallclock=wall)
                recording.wait(5)
            self.assertEqual(recording.frames, 1)
            self.assertIn("wall clock changed", recording.error)
            self.assertEqual(video.stdin.write.call_args.args[0], b"q\n")

    def test_manager_protects_finalization_and_retains_error(self):
        with tempfile.TemporaryDirectory() as directory:
            # Spec makes isinstance recognize the patched coordinator handle.
            process = Mock(spec=MultistreamRecording)
            process.poll.return_value = None
            process.started = time.monotonic()
            process.stdin = None
            process.status.return_value = {"finalizing": True, "error": "diagnostic"}
            with patch("pc.operator_server.MultistreamRecording", return_value=process):
                manager = RecordingManager(directory, mode="video", recording_mode="multistream")
                with patch.object(manager, "status", return_value={}):
                    manager.start()
            self.assertTrue(manager.status()["recording"])
            manager.stop()
            self.assertTrue(manager.camera_view()["locked"])
            with self.assertRaisesRegex(RuntimeError, "Stop recording"):
                manager.set_camera_view(0)
            with self.assertRaisesRegex(RuntimeError, "already active"):
                manager.start()
            process.poll.return_value = 1
            self.assertFalse(manager.status()["recording"])
            self.assertEqual(manager.status()["error"], "diagnostic")


if __name__ == "__main__":
    unittest.main()
