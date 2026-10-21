"""Real media checks: preserve 768x432 slices and match live rotation on decode."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pc.multistream_recording import mux_command
from pc.operator_server import RecordingManager
from pc.video_orientation import rotation_options


class BaselineRotationTests(unittest.TestCase):
    def test_all_offsets_preserve_manager_selection_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            for base in (0, 90, 180, 270):
                manager = RecordingManager(directory, base_rotation=base)
                for selected in (0, 90, 180, 270):
                    expected = (base + selected) % 360
                    self.assertEqual(manager.set_camera_view(selected), {
                        "rotation": selected, "effective_rotation": expected,
                        "metadata_warnings": [], "locked": False})
                    self.assertEqual(manager.status()["effective_rotation"], expected)
                    restored = RecordingManager(directory, base_rotation=base)
                    self.assertEqual(restored.camera_view(), manager.camera_view())
                    self.assertEqual(json.loads((Path(directory) / ".camera-view.json").read_text()),
                                     {"rotation": selected})
            for invalid in (True, "90", 45, -90, None, 90.0):
                with self.assertRaises(ValueError):
                    RecordingManager(directory, base_rotation=invalid)

    def test_both_recorders_receive_effective_rotation_and_lock_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("legacy", "multistream"):
                manager = RecordingManager(directory, base_rotation=270, recording_mode=mode)
                manager.set_camera_view(180)
                if mode == "multistream":
                    with patch("pc.operator_server.MultistreamRecording") as capture:
                        capture.return_value.poll.return_value = None
                        with patch.object(manager, "status", return_value={}):
                            manager.start()
                        self.assertEqual(capture.call_args.kwargs["rotation"], 90)
                        with self.assertRaises(RuntimeError):
                            manager.set_camera_view(0)
                else:
                    process = Mock()
                    process.poll.return_value = None
                    process.wait.return_value = 0
                    manager.spawn = Mock(return_value=process)
                    with patch("pc.video_orientation.supports_display_rotation", return_value=False):
                        manager.start()
                    command = manager.spawn.call_args.args[0]
                    self.assertIn("rotate=90", command)
                    self.assertEqual(command[command.index("-c:v") + 1], "copy")
                    with self.assertRaises(RuntimeError):
                        manager.set_camera_view(0)
                    output = manager.recording_path(manager.status()["id"])
                    output.write_bytes(b"test")
                    manager.stop()
                    self.assertEqual(json.loads(output.with_suffix(".json").read_text())["rotation"], 90)


class RotationOptionsTests(unittest.TestCase):
    def test_old_and_new_ffmpeg_use_same_counterclockwise_angle(self):
        with patch("pc.video_orientation.supports_display_rotation", return_value=False):
            self.assertEqual(rotation_options(90), ([], ["-metadata:s:v:0", "rotate=90"]))
        with patch("pc.video_orientation.supports_display_rotation", return_value=True):
            self.assertEqual(rotation_options(90), (["-noautorotate", "-display_rotation:v:0", "90"], []))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools required")
class RotationMediaTests(unittest.TestCase):
    def run_media(self, command):
        result = subprocess.run(command, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result.stdout

    def test_all_rotations_keep_source_resolution_slices_and_display_full_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "video.mkv"
            pcm = directory / "silent.pcm"
            pcm.write_bytes(bytes(48000 * 2))
            self.run_media(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=768x432:rate=5", "-t", "1", "-c:v", "libx264",
                            "-preset", "ultrafast", str(source)])
            def slices(path):
                data = self.run_media(["ffmpeg", "-v", "error", "-i", str(path), "-c:v", "copy",
                                       "-an", "-bsf:v", "h264_mp4toannexb", "-f", "h264", "-"])
                import re
                return [n.rstrip(b"\0") for n in re.split(b"\x00\x00\x00?\x01", data)
                        if n and n[0] & 31 in (1, 5)]
            original = slices(source)
            for rotation, filter_ in ((0, "null"), (90, "transpose=cclock"),
                                      (180, "hflip,vflip"), (270, "transpose=clock")):
                with self.subTest(rotation=rotation):
                    output = directory / f"out-{rotation}.mp4"
                    self.run_media(mux_command(source, pcm, pcm, output, 1, rotation))
                    streams = json.loads(self.run_media(["ffprobe", "-v", "error", "-show_streams",
                                                          "-of", "json", str(output)]))["streams"]
                    video = streams[0]
                    self.assertEqual((video["width"], video["height"]), (768, 432))
                    self.assertEqual(video["sample_aspect_ratio"], "1:1")
                    self.assertEqual(video["display_aspect_ratio"], "16:9")
                    self.assertEqual(len(streams), 4)
                    self.assertEqual(slices(output), original)
                    expected = self.run_media(["ffmpeg", "-v", "error", "-i", str(source), "-vf", filter_,
                                               "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
                    actual = self.run_media(["ffmpeg", "-v", "error", "-i", str(output),
                                             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
                    self.assertEqual(actual, expected, "MP4 must display exactly the selected rotation")
