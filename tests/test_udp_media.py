import time
import unittest
from unittest.mock import Mock, patch

import app
from maix.headset_mic_stream import publisher_command
from maix.talkback_receiver import TalkbackReceiver
from pc.talkback import TalkbackRelay, make_packet
from pc.talkback_protocol import decode, JitterBuffer
from pc.check_camera_udp import check_camera


class UdpMediaTests(unittest.TestCase):

    def test_every_publisher_transport_is_udp_and_video_is_copied(self):
        for command in (app.publisher_command("192.0.2.1"), publisher_command("192.0.2.2")):
            transports = [command[i + 1] for i, value in enumerate(command) if value == "-rtsp_transport"]
            self.assertTrue(transports)
            self.assertEqual(set(transports), {"udp"})
        command = app.publisher_command("192.0.2.1")
        self.assertEqual(command[command.index("-c:v") + 1], "copy")
        self.assertEqual(command[command.index("-frame_duration") + 1], "20")

    def test_tb3_framing_staleness_and_old_formats(self):
        from pc.talkback_protocol import HEADER, encode
        packet = make_packet(bytes(320), timestamp=1000)
        self.assertEqual(HEADER.size, 24)
        self.assertEqual(len(packet), 344)
        self.assertEqual(decode(packet, now_ms=1000)[1], bytes(320))
        self.assertIsNone(decode(packet, now_ms=4000))
        self.assertEqual(decode(make_packet(b"", stop=True, timestamp=1000), now_ms=1000)[0], "stop")
        for bad in (b"", packet[:23], packet + b"xx", packet[:-1],
                    b"TB1" + packet[3:], b"TB2" + packet[3:],
                    b"TB2" + packet[3:24] + bytes(16), b"TB2" + packet[3:] + bytes(16),
                    packet[:3] + b"\x02" + packet[4:],
                    make_packet(b"", stop=True, timestamp=1000) + b"xx"):
            self.assertIsNone(decode(bad, now_ms=1000))
        for pcm in (b"", b"x", bytes(322)):
            with self.assertRaises(ValueError):
                encode(pcm, 1, 0)
        with self.assertRaises(ValueError):
            encode(b"xx", 1, 0, stop=True)

    def test_jitter_reorders_deduplicates_bounds_and_discards_stale_frames(self):
        queue = JitterBuffer()
        frame = lambda seq: ("pcm", bytes([seq]) * 320, 7, seq, 1000 + seq * 20)
        self.assertTrue(queue.push(frame(1), 0.02))
        self.assertTrue(queue.push(frame(0), 0.025))
        self.assertFalse(queue.push(frame(1), 0.025))
        self.assertEqual(queue.pop(0.045), bytes(320))
        self.assertEqual(queue.pop(0.065), bytes([1]) * 320)
        self.assertFalse(queue.push(frame(0), 0.07))
        for seq in range(2, 15):
            queue.push(frame(seq), seq * 0.02)
        self.assertLessEqual(len(queue.frames), 6)
        self.assertIsNone(queue.pop(1))
        self.assertFalse(queue.push(frame(15), 2))

    def test_receiver_rejects_retired_sessions_and_delayed_stop(self):
        receiver = TalkbackReceiver()
        packet = lambda seq, stop=False: make_packet(b"" if stop else bytes(320),
                                                    session=42, sequence=seq, stop=stop)
        self.assertTrue(receiver.accept(packet(1), now=0))
        self.assertFalse(receiver.accept(packet(0, True), now=0))
        self.assertTrue(receiver.accept(packet(2, True), now=0.02))
        self.assertFalse(receiver.accept(packet(3), now=0.04))

    def test_stale_browser_stop_cannot_end_new_session(self):
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock())
        relay.stop("old-session")
        relay.udp.sendto.assert_not_called()

    def test_forward_queue_is_bounded(self):
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock())
        for _ in range(100):
            relay.queue.append((time.monotonic(), bytes(320)))
        self.assertEqual(len(relay.queue), 3)

    def test_forward_discards_old_audio_before_sending(self):
        relay = TalkbackRelay(("127.0.0.1", 9002), udp_socket=Mock())
        relay.queue.append((0, b"a" * 320))
        relay.queue.append((1, b"b" * 320))
        cancel = Mock()
        cancel.is_set.return_value = False
        cancel.wait.side_effect = [False, True]
        with patch("pc.talkback.time.monotonic", return_value=1):
            relay._forward(cancel, relay.session)
        relay.udp.sendto.assert_called_once()
        self.assertEqual(decode(relay.udp.sendto.call_args.args[0])[1], b"b" * 320)

    def test_camera_udp_probe_requires_received_video_packets(self):
        run = Mock(return_value=Mock(returncode=0, stdout='{"streams": [{"codec_type": "video"}]}'))
        self.assertFalse(check_camera("192.0.2.1", run)["verified"])
        run.return_value.stdout = '{"streams": [{"codec_type": "video", "nb_read_packets": "2"}]}'
        self.assertTrue(check_camera("192.0.2.1", run)["verified"])
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-rtsp_transport") + 1], "udp")

    def test_maix_ip_environment_is_respected(self):
        with patch.dict("os.environ", {"MAIX_IP": "192.0.2.3"}):
            self.assertEqual(app.parse_args([]).maix_ip, "192.0.2.3")
