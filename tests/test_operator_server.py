import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from pc.operator_server import PROJECT_ROOT, RecordingManager


class RecordingManagerTests(unittest.TestCase):
    def test_default_recordings_directory_is_project_relative(self):
        manager = RecordingManager()
        self.assertEqual(manager.directory, PROJECT_ROOT / "recordings")
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

            manager = RecordingManager(Path(directory), spawn=spawn)
            active = manager.start()
            try:
                self.assertTrue(active["recording"])
                self.assertIn("-c:v", commands[0])
                self.assertIn("copy", commands[0])
                self.assertIn("filter_units=remove_types=0", commands[0])
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
            manager = RecordingManager(Path(directory), spawn=lambda *a, **kw: process)
            manager.start()
            with self.assertRaisesRegex(RuntimeError, "already active"):
                manager.start()
            manager.stop()

    def test_only_known_recording_ids_can_be_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RecordingManager(Path(directory))
            with self.assertRaises(ValueError):
                manager.recording_path("../auto.key")


if __name__ == "__main__":
    unittest.main()
