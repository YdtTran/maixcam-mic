import unittest

from maix.air6_mic_stream import capture_command, publisher_command


class Air6MicStreamTests(unittest.TestCase):
    def test_captures_headset_sco_and_publishes_continuous_pcm(self):
        capture = capture_command("28:52:E0:16:73:CE")
        publisher = publisher_command("10.127.9.237")
        self.assertIn("bluealsa:DEV=28:52:E0:16:73:CE,PROFILE=sco", capture)
        self.assertIn("pipe:0", publisher)
        self.assertEqual(publisher[publisher.index("-ar") + 1], "8000")
        self.assertEqual(publisher[publisher.index("-c:a") + 1], "pcm_mulaw")
        self.assertEqual(publisher[-1], "rtsp://10.127.9.237:8554/air6mic")


if __name__ == "__main__":
    unittest.main()
