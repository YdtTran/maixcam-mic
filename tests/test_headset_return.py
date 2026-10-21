import tempfile
import socket
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app
from pc.headset_return import HeadsetReturn, receiver_command
from maix.bluetooth_audio import BluetoothAudioConnector
from maix.talkback_receiver import TalkbackReceiver
from maix import headset_mic_stream as mic


class CameraPcmuSenderTests(unittest.TestCase):
    def test_main_retries_network_failure(self):
        with patch.object(sys, "argv", ["headset_mic_stream.py", "--target", "192.0.2.1", "--rtp-port", "8004"]), \
                patch.dict("os.environ", {"RTSP_TRANSPORT": "udp"}), patch.object(mic.signal, "signal"), \
                patch.object(mic, "publish_audio", side_effect=[OSError("network unavailable"), KeyboardInterrupt]) as publish, \
                patch.object(mic.time, "sleep") as sleep, patch("builtins.print"):
            mic.main()
            self.assertEqual(publish.call_count, 2)
            sleep.assert_called_once_with(3)

    def test_udp_packets_have_exact_headers_payload_and_counter_wraparound(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(2)
            sender = mic.RtpPcmUlawSender("127.0.0.1", receiver.getsockname()[1])
            sender.sequence, sender.timestamp, sender.ssrc = 65535, 0xffffffa0, 0x12345678
            try:
                sender.send(mic.SILENCE)
                sender.send(struct.pack("<h", 32767) * 160)
                first, second = receiver.recv(2048), receiver.recv(2048)
            finally:
                sender.close()
            self.assertEqual(len(first), 172)
            self.assertEqual(first[:12], struct.pack("!BBHII", 0x80, 0, 65535, 0xffffffa0, 0x12345678))
            self.assertEqual(first[12:], b"\xff" * 160)
            self.assertEqual(second, struct.pack("!BBHII", 0x80, 0, 0, 64, 0x12345678) + b"\x80" * 160)

    def test_fallback_encoder_known_vectors_and_all_samples_against_audioop(self):
        table = mic.ulaw_table()
        samples = [-32768, -1000, -1, 0, 1, 1000, 32767]
        self.assertEqual(bytes(table[s & 65535] for s in samples), bytes([0, 78, 126, 255, 255, 206, 128]))
        if mic.audioop is not None:
            pcm = struct.pack("<65536H", *range(65536))
            if sys.byteorder != "little":
                pcm = mic.audioop.byteswap(pcm, 2)
            self.assertEqual(table, mic.audioop.lin2ulaw(pcm, 2))
        with patch.object(mic, "audioop", None), patch.object(mic.socket, "socket") as sock:
            sender = mic.RtpPcmUlawSender("192.0.2.1", 8004)
            try:
                sender.send(struct.pack("<h", -1000) * 160)
                self.assertEqual(sock.return_value.sendto.call_args.args[0][12:], b"\x4e" * 160)
            finally:
                sender.close()

    def test_paused_udp_publisher_sends_silence_without_subprocess_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pause, ack = root / "pause", root / "ack"
            pause.touch()
            packets = []
            def sent(packet, target):
                self.assertTrue(ack.exists())
                packets.append((packet, target))
            with patch.object(mic.subprocess, "Popen") as spawn, patch.object(mic.socket, "socket") as sock:
                sock.return_value.sendto.side_effect = sent
                with patch.object(mic.time, "sleep", side_effect=[None, KeyboardInterrupt]), self.assertRaises(KeyboardInterrupt):
                    mic.publish_audio("192.0.2.1", root / "selection", pause, ack, rtp_port=8004)
                spawn.assert_not_called()
                sock.return_value.close.assert_called_once()
            self.assertFalse(ack.exists())
            self.assertEqual(len(packets), 2)
            self.assertTrue(all(packet[12:] == b"\xff" * 160 and target == ("192.0.2.1", 8004)
                                for packet, target in packets))
            self.assertEqual((struct.unpack("!H", packets[1][0][2:4])[0] -
                              struct.unpack("!H", packets[0][0][2:4])[0]) & 65535, 1)

    def test_socket_backpressure_drops_frame_and_other_errors_propagate(self):
        with patch.object(mic.socket, "socket") as sock:
            sender = mic.RtpPcmUlawSender("192.0.2.1", 8004)
            try:
                sequence, timestamp = sender.sequence, sender.timestamp
                sock.return_value.sendto.side_effect = BlockingIOError
                sender.send(mic.SILENCE)
                self.assertEqual(sender.sequence, (sequence + 1) & 65535)
                self.assertEqual(sender.timestamp, (timestamp + 160) & 0xffffffff)
                sock.return_value.sendto.side_effect = OSError("network unavailable")
                with self.assertRaises(OSError):
                    sender.send(mic.SILENCE)
                with self.assertRaises(ValueError):
                    sender.send(b"\0")
            finally:
                sender.close()

    def test_udp_selected_headset_spawns_only_arecord_and_sends_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "selection").write_text("AA:BB:CC:DD:EE:FF")
            with patch.object(mic.subprocess, "Popen") as spawn, patch.object(mic.os, "set_blocking", create=True), \
                    patch.object(mic.os, "read", return_value=struct.pack("<h", 1000) * 160), \
                    patch.object(mic.time, "sleep", side_effect=KeyboardInterrupt), \
                    patch.object(mic.socket, "socket") as sock:
                spawn.return_value.poll.return_value = None
                with self.assertRaises(KeyboardInterrupt):
                    mic.publish_audio("192.0.2.1", root / "selection", root / "pause", root / "ack", rtp_port=8004)
                spawn.assert_called_once()
                self.assertEqual(spawn.call_args.args[0], mic.capture_command("AA:BB:CC:DD:EE:FF"))
                self.assertEqual(sock.return_value.sendto.call_args.args[0][12:], b"\xce" * 160)
                spawn.return_value.terminate.assert_called_once()
                sock.return_value.close.assert_called_once()

    def test_explicit_rtsp_mode_keeps_ffmpeg_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(mic.subprocess, "Popen") as spawn, patch.object(mic.os, "set_blocking", create=True), \
                    patch.object(mic.os, "write", return_value=320), \
                    patch.object(mic.time, "sleep", side_effect=KeyboardInterrupt):
                spawn.return_value.poll.return_value = None
                with self.assertRaises(KeyboardInterrupt):
                    mic.publish_audio("192.0.2.1", root / "selection", root / "pause", root / "ack", transport="tcp")
                command = spawn.call_args.args[0]
                self.assertEqual(command[0], "ffmpeg")
                self.assertEqual(command[-1], "rtsp://192.0.2.1:8554/headsetmic")
                spawn.return_value.terminate.assert_called_once()


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
            receiver = TalkbackReceiver(pause_path=pause, ack_path=ack, duplex=True)
            receiver._pause_mic()
            self.assertFalse(pause.exists())
            self.assertFalse(ack.exists())
