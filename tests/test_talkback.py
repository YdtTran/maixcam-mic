import unittest
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock

from pc.talkback import TalkbackRelay, make_packet
from maix.talkback_receiver import TalkbackReceiver, valid_packet


class TalkbackTests(unittest.TestCase):
    def test_receiver_player_uses_root_alsa_configuration(self):
        process = Mock()
        spawn = Mock(return_value=process)
        receiver = TalkbackReceiver(b"a" * 16, spawn=spawn)

        receiver._player()

        self.assertEqual(spawn.call_args.kwargs["env"]["HOME"], "/root")
        self.assertEqual(spawn.call_args.args[0][-3:], ["8000", "-c", "1"])

    def test_pcm_is_split_into_authenticated_udp_packets(self):
        udp = Mock()
        relay = TalkbackRelay(b"a" * 16, ("192.168.1.15", 9002), udp_socket=udp)
        relay.send_pcm(b"\x00\x01" * 1500)
        self.assertEqual(udp.sendto.call_count, 3)
        for call in udp.sendto.call_args_list:
            packet, target = call.args
            self.assertEqual(target, ("192.168.1.15", 9002))
            self.assertLessEqual(len(packet), 1059)
            self.assertIsNotNone(valid_packet(packet, b"a" * 16))
            self.assertIsNone(valid_packet(packet, b"b" * 16))

    def test_odd_or_oversized_audio_is_rejected(self):
        relay = TalkbackRelay(b"a" * 16, ("127.0.0.1", 9002), udp_socket=Mock())
        with self.assertRaises(ValueError):
            relay.send_pcm(b"a")
        with self.assertRaises(ValueError):
            relay.send_pcm(b"a" * 65538)

    def test_stop_packet_is_authenticated(self):
        packet = make_packet(b"a" * 16, b"", stop=True)
        self.assertEqual(valid_packet(packet, b"a" * 16), ("stop", b""))
        self.assertIsNone(valid_packet(packet, b"b" * 16))

    def test_talkback_waits_for_mic_pause_and_restores_capture_on_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            pause_path = Path(directory) / "pause"
            ack_path = Path(directory) / "ack"
            receiver = TalkbackReceiver(b"a" * 16, pause_path=pause_path, ack_path=ack_path)
            timer = threading.Timer(0.05, ack_path.touch)
            timer.start()
            try:
                receiver._pause_mic()
                self.assertTrue(pause_path.exists())
                receiver.stop()
                self.assertFalse(pause_path.exists())
            finally:
                timer.join()


if __name__ == "__main__":
    unittest.main()
