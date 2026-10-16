import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from pc.operator_server import PROJECT_ROOT, RecordingManager


class RecordingManagerTests(unittest.TestCase):
    def test_default_recordings_directory_is_project_relative(self):
        manager = RecordingManager()
        self.assertEqual(manager.directory, PROJECT_ROOT / "recordings")
        self.assertEqual(manager.recording_mode, "multistream")
        manager._recording_id = "20260917T000000Z_12345678"
        manager._process = Mock()
        manager._process.poll.return_value = None
        self.assertEqual(manager.status()["path"], "recordings/20260917T000000Z_12345678.mp4")

    def test_start_stop_creates_playable_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            process.wait.return_value = 0
            process.stdin = Mock()
            commands = []

            def spawn(command, **kwargs):
                commands.append(command)
                Path(command[-1]).write_bytes(b"recorded")
                return process

            manager = RecordingManager(Path(directory), spawn=spawn, recording_mode="legacy")
            active = manager.start()
            try:
                self.assertTrue(active["recording"])
                self.assertIn("-c:v", commands[0])
                self.assertIn("copy", commands[0])
                self.assertIn("filter_units=remove_types=0,h264_metadata=sample_aspect_ratio=1/1", commands[0])
                self.assertEqual(commands[0][-1][-4:], ".mp4")
                self.assertIn("aac", commands[0])
            finally:
                manager.stop()
            self.assertFalse(manager.status()["recording"])
            recordings = manager.list_recordings()
            self.assertEqual(len(recordings), 1)
            self.assertIn("duration_seconds", recordings[0])
            process.stdin.write.assert_called_once_with(b"q\n")

    def test_second_start_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            manager = RecordingManager(Path(directory), spawn=lambda *a, **kw: process, recording_mode="legacy")
            manager.start()
            with self.assertRaisesRegex(RuntimeError, "already active"):
                manager.start()
            manager.stop()

    def test_camera_view_persists_and_cannot_change_during_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RecordingManager(directory)
            self.assertEqual(manager.camera_view(), {"rotation": 0, "locked": False})
            for invalid in (True, "90", 45, -90, None, 90.0):
                with self.assertRaises(ValueError):
                    manager.set_camera_view(invalid)
            manager.set_camera_view(90)
            restored = RecordingManager(directory)
            self.assertEqual(restored.camera_view()["rotation"], 90)
            with patch("pc.operator_server.MultistreamRecording") as capture:
                capture.return_value.poll.return_value = None
                # Keep the status isinstance check using the actual class.
                with patch.object(manager, "status", return_value={"recording": True}):
                    manager.start()
                self.assertEqual(capture.call_args.kwargs["rotation"], 90)
                with self.assertRaisesRegex(RuntimeError, "Stop recording"):
                    manager.set_camera_view(0)
            self.assertEqual(RecordingManager(directory).camera_view()["rotation"], 90)

    def test_only_known_recording_ids_can_be_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RecordingManager(Path(directory))
            with self.assertRaises(ValueError):
                manager.recording_path("../README.md")


if __name__ == "__main__":
    unittest.main()
