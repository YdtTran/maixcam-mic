import unittest
import tempfile
import threading
import math
from pathlib import Path
from unittest.mock import Mock, patch

from pc.talkback import TalkbackRelay, make_packet
from pc.talkback_protocol import decode
from maix.talkback_receiver import TalkbackReceiver, valid_packet


class TalkbackTests(unittest.TestCase):
    def test_sco_packet_gaps_feed_silence_at_audio_rate_without_restarting_player(self):
        receiver = TalkbackReceiver(b"a" * 16, duplex=True)
        receiver.last_packet = .001
        receiver.player = Mock()
        receiver._player = Mock(return_value=receiver.player)
        receiver._pause_mic = Mock()
        receiver.stop = Mock()
        receiver.jitter.pop = Mock(return_value=None)
        now = [0.0]
        closing = Mock()
        def wait(seconds):
            now[0] += seconds
            return now[0] >= .11
        closing.wait.side_effect = wait
        with patch("maix.talkback_receiver.time.monotonic", side_effect=lambda: now[0]), \
                patch("maix.talkback_receiver.os.write", return_value=320) as write:
            receiver._playback(closing)
        self.assertGreaterEqual(write.call_count, 4)
        self.assertLessEqual(write.call_count, 6)
        self.assertTrue(all(call.args[1] == bytes(320) for call in write.call_args_list))
        receiver.stop.assert_not_called()

    def test_sco_duplex_uses_frame_sized_playback_period_without_pausing_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            pause = Path(directory) / "pause"
            spawn = Mock(return_value=Mock())
            receiver = TalkbackReceiver(b"a" * 16, spawn=spawn, duplex=True,
                                       pause_path=pause, ack_path=Path(directory) / "ack")
            receiver._pause_mic()
            self.assertFalse(pause.exists())
            with patch("maix.talkback_receiver.os.set_blocking", create=True):
                receiver._player()
            command = spawn.call_args.args[0]
            self.assertEqual(command[command.index("--period-time") + 1], "20000")
            self.assertEqual(command[command.index("--buffer-time") + 1], "80000")

    def test_duplex_rejects_a2dp_playback(self):
        with self.assertRaisesRegex(ValueError, "requires SCO"):
            TalkbackReceiver(b"a" * 16, duplex=True, playback_profile="a2dp")

    def test_pause_allows_capture_termination_timeout_before_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            pause = Path(directory) / "pause"
            ack = Path(directory) / "ack"
            receiver = TalkbackReceiver(b"a" * 16, pause_path=pause, ack_path=ack)
            now = [0.0]

            def wait(seconds):
                now[0] += seconds
                # stop_process waits two seconds before killing a stuck arecord.
                if now[0] >= 2.1:
                    ack.touch()

            with patch("maix.talkback_receiver.time.monotonic", side_effect=lambda: now[0]), \
                    patch("maix.talkback_receiver.time.sleep", side_effect=wait):
                receiver._pause_mic()
            self.assertTrue(pause.exists())
            self.assertTrue(ack.exists())
            receiver.stop()

    def test_unresponsive_capture_pause_is_bounded_and_released(self):
        with tempfile.TemporaryDirectory() as directory:
            pause = Path(directory) / "pause"
            receiver = TalkbackReceiver(b"a" * 16, pause_path=pause,
                                       ack_path=Path(directory) / "ack")
            now = [0.0]

            def wait(seconds):
                now[0] += seconds

            with patch("maix.talkback_receiver.time.monotonic", side_effect=lambda: now[0]), \
                    patch("maix.talkback_receiver.time.sleep", side_effect=wait), \
                    self.assertRaisesRegex(RuntimeError, "did not pause"):
                receiver._pause_mic()
            self.assertFalse(pause.exists())
            self.assertLess(now[0], 4)

    def test_sender_keeps_audio_rate_with_coarse_windows_waits(self):
        relay = TalkbackRelay(b"a" * 16, ("127.0.0.1", 9002), udp_socket=Mock())
        now = [0.0]
        cancel = Mock()
        def coarse_wait(delay):
            now[0] += math.ceil(max(delay, .000001) / .015625) * .015625
            relay.queue.append((now[0], b"\0\0" * 160))
            return now[0] >= 2
        cancel.wait.side_effect = coarse_wait
        with patch("pc.talkback.time.monotonic", side_effect=lambda: now[0]):
            relay._forward(cancel)
        self.assertGreaterEqual(relay.udp.sendto.call_count, 95)
        self.assertLessEqual(relay.udp.sendto.call_count, 101)

    def test_release_clears_interruption_error_only_for_current_session(self):
        relay = TalkbackRelay(b"a" * 16, ("127.0.0.1", 9002), udp_socket=Mock())
        relay.error = "WebRTC talkback audio interrupted; release and retry"
        relay.stop("old-session")
        self.assertIsNotNone(relay.error)
        relay.stop(str(relay.session))
        self.assertIsNone(relay.error)

    def test_temporary_playback_backpressure_drops_frame_without_restarting_audio(self):
        receiver = TalkbackReceiver(b"a" * 16)
        receiver._pause_mic = Mock()
        receiver._player = Mock()
        receiver.jitter.pop = Mock(return_value=b"\0\0" * 160)
        receiver.stop = Mock()
        closing = Mock()
        closing.wait.side_effect = [False, False, True]
        with patch("maix.talkback_receiver.time.monotonic", return_value=0), \
                patch("maix.talkback_receiver.os.write", side_effect=[BlockingIOError(), 320]) as write:
            receiver._playback(closing)
        self.assertEqual(write.call_count, 2)
        receiver.stop.assert_not_called()

    def test_camera_clock_allows_pcm_and_stop_without_relaxing_packet_age(self):
        udp = Mock()
        relay = TalkbackRelay(b"a" * 16, ("127.0.0.1", 9002), udp_socket=udp)
        relay.timestamp_ms = lambda: 10000
        with patch("pc.talkback.time.time", return_value=7.8):
            # An uncalibrated packet is rejected for the observed 2.2s skew.
            packet = make_packet(b"a" * 16, b"\0\0", session=1)
            self.assertIsNone(decode(packet, b"a" * 16, now_ms=10000))
            relay.send_pcm(b"\0\0" * 160)
            relay._send_stop()
        packets = [call.args[0] for call in udp.sendto.call_args_list]
        self.assertEqual(decode(packets[0], b"a" * 16, now_ms=10000)[0], "pcm")
        self.assertEqual(decode(packets[-1], b"a" * 16, now_ms=10000)[0], "stop")
        self.assertIsNone(decode(packets[0], b"a" * 16, now_ms=12001))

    def test_offer_calibrates_clock_before_starting_audio_workers(self):
        response = Mock()
        response.headers = {"Location": "/talkback/session"}
        response.read.return_value = b"answer"
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        calibrated = lambda: 10000
        sync = Mock(return_value=calibrated)
        relay = TalkbackRelay(b"a" * 16, ("127.0.0.1", 9002), udp_socket=Mock(), clock_sync=sync)
        with patch("pc.talkback.urlopen", return_value=context), patch("pc.talkback.threading.Thread"):
            relay.offer("offer")
        sync.assert_called_once()
        self.assertIs(relay.timestamp_ms, calibrated)

    def test_receiver_player_uses_root_alsa_configuration(self):
        process = Mock()
        spawn = Mock(return_value=process)
        receiver = TalkbackReceiver(b"a" * 16, spawn=spawn)

        with patch("maix.talkback_receiver.os.set_blocking", create=True):
            receiver._player()

        self.assertEqual(spawn.call_args.kwargs["env"]["HOME"], "/root")
        self.assertEqual(spawn.call_args.args[0][-3:], ["8000", "-c", "1"])

    def test_pcm_is_split_into_authenticated_udp_packets(self):
        udp = Mock()
        relay = TalkbackRelay(b"a" * 16, ("192.168.1.15", 9002), udp_socket=udp)
        relay.send_pcm(b"\x00\x01" * 1500)
        self.assertEqual(udp.sendto.call_count, 10)
        for call in udp.sendto.call_args_list:
            packet, target = call.args
            self.assertEqual(target, ("192.168.1.15", 9002))
            self.assertLessEqual(len(packet), 360)
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
