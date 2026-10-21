import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from pc.operator_server import PROJECT_ROOT, RecordingManager


class RecordingManagerTests(unittest.TestCase):
    def test_legacy_exit_outcomes_preserve_failed_media_and_success_metadata(self):
        for spontaneous in (False, True):
            for returncode in (0, 1, -9):
                with self.subTest(spontaneous=spontaneous, returncode=returncode), tempfile.TemporaryDirectory() as directory:
                    process = Mock()
                    process.poll.return_value = None
                    process.wait.return_value = returncode
                    manager = RecordingManager(directory, spawn=lambda *a, **kw: process, recording_mode="legacy")
                    manager.set_camera_view(90)
                    active = manager.start()
                    output = manager.recording_path(active["id"])
                    output.write_bytes(b"recorded")
                    if spontaneous:
                        process.poll.return_value = returncode
                        status = manager.status()
                    else:
                        status = manager.stop()
                    self.assertFalse(status["recording"])
                    self.assertTrue(process.stdin.close.called)
                    self.assertTrue(output.with_suffix(".ffmpeg.log").is_file())
                    if returncode == 0:
                        self.assertNotIn("error", status)
                        self.assertEqual(manager.list_recordings()[0]["id"], active["id"])
                        metadata = json.loads(output.with_suffix(".json").read_text())
                        self.assertEqual(metadata["rotation"], 90)
                        self.assertGreaterEqual(metadata["duration_seconds"], 0)
                    else:
                        self.assertIn(f"exit {returncode}", status["error"])
                        self.assertIn("recovery", status["error"])
                        self.assertEqual(output.with_suffix(".failed.mp4").read_bytes(), b"recorded")
                        self.assertFalse(output.exists())
                        self.assertFalse(output.with_suffix(".json").exists())
                        self.assertEqual(manager.list_recordings(), [])
                        self.assertEqual(RecordingManager(directory).list_recordings(), [])
                        self.assertEqual(manager.stop()["error"], status["error"])
                        with patch.object(manager, "spawn", side_effect=OSError("spawn failed")):
                            with self.assertRaisesRegex(OSError, "spawn failed"):
                                manager.start()
                        self.assertEqual(manager.status()["error"], status["error"])
                        process.poll.return_value = None
                        self.assertNotIn("error", manager.start())
                        manager.stop()

    def test_legacy_forced_stop_is_failure_even_if_kill_returns_zero(self):
        for failure in (subprocess.TimeoutExpired("ffmpeg", 10), BrokenPipeError("closed input")):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                process = Mock()
                process.poll.return_value = None
                if isinstance(failure, BrokenPipeError):
                    process.stdin.write.side_effect = failure
                    process.wait.return_value = 0
                else:
                    process.wait.side_effect = [failure, 0]
                manager = RecordingManager(directory, spawn=lambda *a, **kw: process, recording_mode="legacy")
                active = manager.start()
                output = manager.recording_path(active["id"])
                output.write_bytes(b"partial")
                status = manager.stop()
                process.kill.assert_called_once()
                self.assertFalse(status["recording"])
                self.assertIn("forced termination", status["error"])
                self.assertEqual(output.with_suffix(".failed.mp4").read_bytes(), b"partial")
                self.assertFalse(output.with_suffix(".json").exists())
                self.assertEqual(manager.list_recordings(), [])

    def test_legacy_kill_timeout_keeps_capture_locked_until_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            process.wait.side_effect = subprocess.TimeoutExpired("ffmpeg", 10)
            manager = RecordingManager(directory, spawn=lambda *a, **kw: process, recording_mode="legacy")
            output = manager.recording_path(manager.start()["id"])
            output.write_bytes(b"partial")
            self.assertTrue(manager.stop()["recording"])
            self.assertTrue(manager.camera_view()["locked"])
            self.assertEqual(manager.list_recordings(), [])
            with self.assertRaisesRegex(RuntimeError, "already active"):
                manager.start()
            process.poll.return_value = -9
            self.assertFalse(manager.status()["recording"])
            self.assertIn("forced termination", manager.status()["error"])
            self.assertEqual(manager.list_recordings(), [])

    def test_legacy_zero_exit_without_media_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            process.wait.return_value = 0
            manager = RecordingManager(directory, spawn=lambda *a, **kw: process, recording_mode="legacy")
            manager.start()
            self.assertIn("no media", manager.stop()["error"])
            self.assertEqual(manager.list_recordings(), [])

    def test_invalid_camera_view_preserves_file_and_warns_until_saved(self):
        for contents in ('{', '[]', 'null', '{}', '{"rotation": true}',
                         '{"rotation": "90"}', '{"rotation": 90.0}', '{"rotation": 45}',
                         '{"rotation": null}', '{"rotation": NaN}'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / ".camera-view.json"
                path.write_text(contents)
                manager = RecordingManager(directory)
                self.assertEqual(manager.camera_view()["rotation"], 0)
                self.assertEqual(path.read_text(), contents)
                status = manager.status()
                self.assertIn(".camera-view.json", status["metadata_warnings"][0])
                self.assertNotIn("error", status)
                with patch.object(Path, "replace", side_effect=OSError("write denied")):
                    with self.assertRaisesRegex(OSError, "write denied"):
                        manager.set_camera_view(90)
                self.assertEqual(manager.status()["metadata_warnings"], status["metadata_warnings"])
                self.assertEqual(path.read_text(), contents)
                manager.set_camera_view(270)
                self.assertEqual(manager.status()["metadata_warnings"], [])
                self.assertEqual(RecordingManager(directory).camera_view()["rotation"], 270)

    def test_bad_sidecars_do_not_hide_media_or_modify_files(self):
        invalid = ('{', '[]', 'null', '{}', '{"duration_seconds": null}',
                   '{"duration_seconds": "12"}', '{"duration_seconds": true}',
                   '{"duration_seconds": -1}', '{"duration_seconds": NaN}',
                   '{"duration_seconds": Infinity}', '{"duration_seconds": -Infinity}',
                   '{"duration_seconds": ' + '9' * 400 + '}')
        with tempfile.TemporaryDirectory() as directory:
            manager = RecordingManager(directory)
            for index, contents in enumerate((*invalid, '{"duration_seconds": 12.8}')):
                path = manager.recording_path(f"20261021T000000Z_{index:08x}")
                path.write_bytes(b"media")
                path.with_suffix(".json").write_text(contents)
            missing = manager.recording_path("20261021T000000Z_ffffffff")
            missing.write_bytes(b"no sidecar")
            originals = {path: path.read_bytes() for path in Path(directory).iterdir()}
            items = {item["id"]: item for item in manager.list_recordings()}
            self.assertEqual(len(items), len(invalid) + 2)
            for index in range(len(invalid)):
                self.assertIsNone(items[f"20261021T000000Z_{index:08x}"]["duration_seconds"])
            self.assertEqual(items[f"20261021T000000Z_{len(invalid):08x}"]["duration_seconds"], 12)
            self.assertIsNone(items[missing.stem]["duration_seconds"])
            self.assertEqual(len(manager.status()["metadata_warnings"]), len(invalid))
            manager.set_camera_view(90)
            self.assertEqual(len(manager.camera_view()["metadata_warnings"]), len(invalid))
            self.assertNotIn("error", manager.status())
            for path, contents in originals.items():
                self.assertEqual(path.read_bytes(), contents)
            for path in Path(directory).glob("*.json"):
                path.write_text('{"duration_seconds": 0}')
            manager.list_recordings()
            self.assertEqual(manager.status()["metadata_warnings"], [])

    def test_unreadable_optional_metadata_is_a_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".camera-view.json"
            path.write_bytes(b'\xff')
            manager = RecordingManager(directory)
            self.assertEqual(manager.camera_view()["rotation"], 0)
            media = manager.recording_path("20261021T000000Z_12345678")
            media.write_bytes(b"media")
            media.with_suffix(".json").write_bytes(b'\xff')
            self.assertIsNone(manager.list_recordings()[0]["duration_seconds"])
            self.assertEqual(len(manager.status()["metadata_warnings"]), 2)
            with patch.object(Path, "read_text", side_effect=OSError("read denied")):
                manager = RecordingManager(directory)
                self.assertIsNone(manager.list_recordings()[0]["duration_seconds"])
            self.assertEqual(len(manager.status()["metadata_warnings"]), 2)
            self.assertEqual(path.read_bytes(), b'\xff')

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
            process.wait.return_value = 0
            manager = RecordingManager(Path(directory), spawn=lambda *a, **kw: process, recording_mode="legacy")
            manager.start()
            with self.assertRaisesRegex(RuntimeError, "already active"):
                manager.start()
            manager.stop()

    def test_camera_view_persists_and_cannot_change_during_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RecordingManager(directory)
            self.assertEqual(manager.camera_view(), {"rotation": 0, "effective_rotation": 0,
                                                    "metadata_warnings": [], "locked": False})
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
