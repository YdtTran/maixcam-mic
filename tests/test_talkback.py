import unittest
import tempfile
import threading
import math
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

from pc.talkback import TalkbackRelay, make_packet
from pc.talkback_protocol import decode
from maix.talkback_receiver import TalkbackReceiver, valid_packet


class TalkbackTests(unittest.TestCase):
    def relay_response(self):
        response = Mock()
        response.headers = {"Location": "/talkback/session"}
        response.read.return_value = b"answer"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_decoder_failure_releases_resource_and_allows_retry_without_stop(self):
        for failure in (OSError("decoder missing"), RuntimeError("pipe failed")):
            with self.subTest(failure=failure):
                relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock(),
                                      spawn=Mock(side_effect=failure))
                with patch("pc.talkback.urlopen", return_value=self.relay_response()) as http, \
                        patch("pc.talkback.threading.Thread"):
                    first = relay.offer("offer")
                    cancel = relay.cancel
                    relay._decode(cancel, int(first["session"]))
                    self.assertTrue(cancel.is_set())
                    self.assertIsNone(relay.location)
                    self.assertIsNone(relay.decoder)
                    self.assertIn(str(failure), relay.error)
                    self.assertEqual(http.call_args.args[0].method, "DELETE")
                    second = relay.offer("retry")
                    self.assertNotEqual(first["session"], second["session"])
                    self.assertIsNone(relay.error)

    def test_media_eof_reaps_decoder_and_releases_abandoned_session(self):
        process = Mock()
        process.stdout.read.return_value = b""
        process.poll.return_value = None
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock(),
                              spawn=Mock(return_value=process))
        with patch("pc.talkback.urlopen", return_value=self.relay_response()) as http, \
                patch("pc.talkback.threading.Thread"):
            relay.offer("offer")
            with patch("pc.talkback.time.monotonic", side_effect=[0, 11]):
                relay._decode(relay.cancel, relay.session)
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=2)
            process.stdout.close.assert_called_once()
            self.assertIsNone(relay.location)
            self.assertIsNone(relay.decoder)
            self.assertIn("interrupted", relay.error)
            self.assertEqual(http.call_args.args[0].method, "DELETE")
            relay.offer("retry")

    def test_real_failed_worker_exits_without_browser_stop(self):
        deleted = threading.Event()
        def http(request, timeout):
            if request.get_method() == "DELETE":
                deleted.set()
            return self.relay_response()
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock(),
                              spawn=Mock(side_effect=OSError("decoder missing")))
        with patch("pc.talkback.urlopen", side_effect=http):
            relay.offer("offer")
            with relay.lock:
                workers = list(relay.workers)
            self.assertTrue(deleted.wait(2))
            for worker in workers:
                worker.join(2)
                self.assertFalse(worker.is_alive())
            self.assertIsNone(relay.location)
            self.assertIn("decoder missing", relay.error)

    def test_spawn_finishing_after_stop_reaps_only_its_own_process(self):
        process = Mock()
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock())
        with patch("pc.talkback.urlopen", return_value=self.relay_response()), \
                patch("pc.talkback.threading.Thread"):
            relay.offer("offer")
            old_session, old_cancel = relay.session, relay.cancel
            def spawn(*args, **kwargs):
                relay.stop(str(old_session))
                relay.offer("retry")
                return process
            relay.spawn = spawn
            relay._decode(old_cancel, old_session)
            process.wait.assert_called_once_with(timeout=2)
            process.stdout.close.assert_called_once()
            self.assertNotEqual(relay.session, old_session)
            self.assertIsNotNone(relay.location)
            self.assertIsNone(relay.decoder)
            self.assertFalse(relay.cancel.is_set())

    def test_delayed_cleanup_and_stale_stop_cannot_touch_retry(self):
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock())
        entered, resume = threading.Event(), threading.Event()
        original_stop = relay._send_stop
        def delayed_stop(*args):
            entered.set()
            self.assertTrue(resume.wait(2))
            original_stop(*args)
        with patch("pc.talkback.urlopen", return_value=self.relay_response()), \
                patch("pc.talkback.threading.Thread"):
            first = relay.offer("offer")
            old_cancel, old_session = relay.cancel, relay.session
        with patch.object(relay, "_send_stop", side_effect=delayed_stop), \
                patch("pc.talkback.urlopen", return_value=self.relay_response()):
            cleanup = threading.Thread(target=relay._retire,
                                       args=(old_session, old_cancel, "lost audio"))
            cleanup.start()
            try:
                self.assertTrue(entered.wait(2))
                with patch("pc.talkback.urlopen", return_value=self.relay_response()), \
                        patch("pc.talkback.threading.Thread"):
                    relay.offer("retry")
                new_location, new_cancel, new_workers = relay.location, relay.cancel, relay.workers
                relay.error = "new diagnostic"
                relay.stop(first["session"])
                relay._retire(old_session, old_cancel, "late failure")
            finally:
                resume.set()
                cleanup.join(2)
        self.assertFalse(cleanup.is_alive())
        self.assertEqual(relay.location, new_location)
        self.assertIs(relay.cancel, new_cancel)
        self.assertFalse(new_cancel.is_set())
        self.assertIs(relay.workers, new_workers)
        self.assertEqual(relay.error, "new diagnostic")
        packets = [decode(call.args[0]) for call in relay.udp.sendto.call_args_list]
        self.assertEqual(len(packets), 3)
        self.assertTrue(all(packet[0] == "stop" and packet[2] == old_session for packet in packets))

    def test_cleanup_reaps_outside_lock_skips_self_and_bounds_waits(self):
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock())
        process, worker = Mock(), Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("ffmpeg", 2), 0]
        relay.decoder = process
        relay.workers = [threading.current_thread(), worker]
        def assert_unlocked(*args, **kwargs):
            acquired = []
            def check():
                with relay.lock:
                    acquired.append(True)
            thread = threading.Thread(target=check)
            thread.start()
            thread.join(1)
            self.assertEqual(acquired, [True])
        process.terminate.side_effect = assert_unlocked
        worker.join.side_effect = assert_unlocked
        relay._retire(relay.session, relay.cancel, "original failure")
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)
        self.assertTrue(all(call.kwargs == {"timeout": 2} for call in process.wait.call_args_list))
        worker.join.assert_called_once_with(timeout=3)
        self.assertEqual(relay.error, "original failure")
        relay._retire(relay.session, relay.cancel, "duplicate")
        self.assertEqual(relay.udp.sendto.call_count, 3)

    def test_sco_packet_gaps_feed_silence_at_audio_rate_without_restarting_player(self):
        receiver = TalkbackReceiver(duplex=True)
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
            receiver = TalkbackReceiver(spawn=spawn, duplex=True,
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
            TalkbackReceiver(duplex=True, playback_profile="a2dp")

    def test_pause_allows_capture_termination_timeout_before_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            pause = Path(directory) / "pause"
            ack = Path(directory) / "ack"
            receiver = TalkbackReceiver(pause_path=pause, ack_path=ack)
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
            receiver = TalkbackReceiver(pause_path=pause,
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
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock())
        now = [0.0]
        cancel = Mock()
        cancel.is_set.return_value = False
        def coarse_wait(delay):
            now[0] += math.ceil(max(delay, .000001) / .015625) * .015625
            relay.queue.append((now[0], b"\0\0" * 160))
            return now[0] >= 2
        cancel.wait.side_effect = coarse_wait
        with patch("pc.talkback.time.monotonic", side_effect=lambda: now[0]):
            relay._forward(cancel, relay.session)
        self.assertGreaterEqual(relay.udp.sendto.call_count, 95)
        self.assertLessEqual(relay.udp.sendto.call_count, 101)

    def test_release_clears_interruption_error_only_for_current_session(self):
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock())
        relay.error = "WebRTC talkback audio interrupted; release and retry"
        relay.stop("old-session")
        self.assertIsNotNone(relay.error)
        relay.stop(str(relay.session))
        self.assertIsNone(relay.error)

    def test_temporary_playback_backpressure_drops_frame_without_restarting_audio(self):
        receiver = TalkbackReceiver()
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
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=udp)
        relay.timestamp_ms = lambda: 10000
        with patch("pc.talkback.time.time", return_value=7.8):
            # An uncalibrated packet is rejected for the observed 2.2s skew.
            packet = make_packet(b"\0\0", session=1)
            self.assertIsNone(decode(packet, now_ms=10000))
            relay.send_pcm(b"\0\0" * 160)
            relay._send_stop()
        packets = [call.args[0] for call in udp.sendto.call_args_list]
        self.assertEqual(decode(packets[0], now_ms=10000)[0], "pcm")
        self.assertEqual(decode(packets[-1], now_ms=10000)[0], "stop")
        self.assertIsNone(decode(packets[0], now_ms=12001))

    def test_offer_calibrates_clock_before_starting_audio_workers(self):
        response = Mock()
        response.headers = {"Location": "/talkback/session"}
        response.read.return_value = b"answer"
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        calibrated = lambda: 10000
        sync = Mock(return_value=calibrated)
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock(), clock_sync=sync)
        with patch("pc.talkback.urlopen", return_value=context), patch("pc.talkback.threading.Thread"):
            relay.offer("offer")
        sync.assert_called_once()
        self.assertIs(relay.timestamp_ms, calibrated)

    def test_receiver_player_uses_root_alsa_configuration(self):
        process = Mock()
        spawn = Mock(return_value=process)
        receiver = TalkbackReceiver(spawn=spawn)

        with patch("maix.talkback_receiver.os.set_blocking", create=True):
            receiver._player()

        self.assertEqual(spawn.call_args.kwargs["env"]["HOME"], "/root")
        self.assertEqual(spawn.call_args.args[0][-3:], ["8000", "-c", "1"])

    def test_pcm_is_split_into_tb3_udp_packets(self):
        udp = Mock()
        relay = TalkbackRelay(("192.168.1.15", 9002), udp_socket=udp)
        relay.send_pcm(b"\x00\x01" * 1500)
        self.assertEqual(udp.sendto.call_count, 10)
        for call in udp.sendto.call_args_list:
            packet, target = call.args
            self.assertEqual(target, ("192.168.1.15", 9002))
            self.assertLessEqual(len(packet), 344)
            self.assertIsNotNone(valid_packet(packet))

    def test_odd_or_oversized_audio_is_rejected(self):
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock())
        with self.assertRaises(ValueError):
            relay.send_pcm(b"a")
        with self.assertRaises(ValueError):
            relay.send_pcm(b"a" * 65538)

    def test_stop_packet_has_no_pcm(self):
        packet = make_packet(b"", stop=True)
        self.assertEqual(valid_packet(packet), ("stop", b""))

    def test_talkback_waits_for_mic_pause_and_restores_capture_on_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            pause_path = Path(directory) / "pause"
            ack_path = Path(directory) / "ack"
            receiver = TalkbackReceiver(pause_path=pause_path, ack_path=ack_path)
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
