"""Real media checks: preserve 768x432 slices and match live rotation on decode."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pc.multistream_recording import mux_command
from pc.video_orientation import rotation_options


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
