import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app
from pc.headset_return import HeadsetReturn, receiver_command
from maix.bluetooth_audio import BluetoothAudioConnector
from maix.talkback_receiver import TalkbackReceiver


class HeadsetReturnTests(unittest.TestCase):
    def test_copy_pcmu_and_keep_video_publisher_independent(self):
        command = receiver_command("mic.sdp")
        self.assertEqual(command[command.index("-c:a") + 1], "copy")
        self.assertEqual(command[-1], "rtsp://127.0.0.1:8554/headsetmic")
        video = app.publisher_command("192.168.1.7", transport="tcp", mode="video")
        self.assertNotIn("mic.sdp", video)
        self.assertNotIn("rtsp://127.0.0.1:8554/headsetmic", video)
        self.assertIn("PCMU/8000/1", app.headset_sdp(8004))
        self.assertIn("m=audio 8004 RTP/AVP 0", app.headset_sdp(8004))

    def test_stalled_receiver_is_closed_and_retried_with_capped_backoff(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [0]
            processes = []

            def spawn(*args, **kwargs):
                process = Mock()
                process.poll.return_value = None
                processes.append(process)
                return process

            service = HeadsetReturn("mic.sdp", directory, spawn=spawn, clock=lambda: now[0])
            service.tick()
            for expected in (2, 4, 8, 16, 30, 30):
                now[0] += 16
                service.tick()
                self.assertIsNone(service.process)
                self.assertEqual(service.next_retry - now[0], expected)
                now[0] += expected - 0.1
                service.tick()
                self.assertIsNone(service.process)
                now[0] += 0.1
                service.tick()
                self.assertIsNotNone(service.process)
            service.close()
            self.assertTrue(all(process.terminate.call_count == 1 for process in processes))

    def test_start_failure_does_not_escape_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            service = HeadsetReturn("mic.sdp", directory, spawn=Mock(side_effect=OSError("port busy")), clock=lambda: 0)
            service.tick()
            self.assertIsNone(service.process)
            self.assertIsNone(service.log)
            self.assertEqual(service.next_retry, 2)

    def test_healthy_publication_resets_backoff(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = Mock(side_effect=[0, 6])
            process = Mock()
            process.poll.return_value = None
            service = HeadsetReturn("mic.sdp", directory, spawn=Mock(return_value=process),
                                    available=lambda path: True, clock=clock)
            service.delay = 30
            service.tick()
            service.tick()
            self.assertEqual(service.delay, 2)
            service.close()

    def test_return_port_rejects_combined_mode_and_invalid_port(self):
        for arguments in (["--return-audio-port", "8004"],
                          ["--stream-mode", "video", "--return-audio-port", "8005"]):
            with patch("sys.stderr"), self.assertRaises(SystemExit):
                app.parse_args(arguments)
        self.assertEqual(app.parse_args(["--stream-mode", "video", "--return-audio-port", "8004"]).return_audio_port, 8004)

    def test_duplex_is_explicit_and_uses_sco_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "alsa"
            connector = BluetoothAudioConnector("AA:BB:CC:DD:EE:FF", config_path=config, playback_profile="sco")
            connector._route_playback()
            self.assertNotIn('profile "a2dp"', config.read_text())
            pause, ack = Path(directory) / "pause", Path(directory) / "ack"
            receiver = TalkbackReceiver(b"a" * 16, pause_path=pause, ack_path=ack, duplex=True)
            receiver._pause_mic()
            self.assertFalse(pause.exists())
            self.assertFalse(ack.exists())
