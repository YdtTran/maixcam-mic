import unittest
import shutil
import socket
import struct
import subprocess

from maix.headset_mic_stream import capture_command, publisher_command


class HeadsetMicStreamTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required for RTP packet check")
    def test_direct_rtp_emits_twenty_millisecond_g711_frames(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(2)
            command = publisher_command("127.0.0.1", receiver.getsockname()[1])
            result = subprocess.run(command, input=bytes(320 * 20), capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            first = receiver.recv(2048)
            second = receiver.recv(2048)
            self.assertEqual(first[0] >> 6, 2)
            self.assertEqual(first[1] & 127, 0)  # Static PCMU payload type.
            self.assertEqual(len(first), 172)  # 12-byte RTP header + 160 samples.
            timestamp = lambda packet: struct.unpack("!I", packet[4:8])[0]
            self.assertEqual((timestamp(second) - timestamp(first)) & 0xffffffff, 160)

    def test_captures_headset_sco_and_publishes_continuous_pcm(self):
        capture = capture_command("28:52:E0:16:73:CE")
        publisher = publisher_command("10.127.9.237")
        self.assertIn("bluealsa:DEV=28:52:E0:16:73:CE,PROFILE=sco", capture)
        self.assertIn("pipe:0", publisher)
        self.assertEqual(publisher[publisher.index("-ar") + 1], "8000")
        self.assertEqual(publisher[publisher.index("-c:a") + 1], "pcm_mulaw")
        self.assertEqual(publisher[-1], "rtsp://10.127.9.237:8554/headsetmic")


if __name__ == "__main__":
    unittest.main()
