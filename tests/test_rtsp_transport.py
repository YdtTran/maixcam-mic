import unittest
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import app
from maix.headset_mic_stream import publisher_command as mic_command
from pc.check_camera_udp import check_camera
from pc.measure_transport import distribution, summarize_log
from pc.operator_server import RecordingManager
from pc.talkback import TalkbackRelay


class TransportTests(unittest.TestCase):
    def test_modes_only_open_required_inputs_and_map_correct_streams(self):
        for transport in ("udp", "tcp"):
            for mode, inputs, maps in (("video", 1, ["0:v:0"]), ("audio", 1, ["0:a:0"]),
                                       ("combined", 2, ["0:v:0", "1:a:0"])):
                with self.subTest(transport=transport, mode=mode):
                    command = app.publisher_command("192.0.2.1", transport=transport, mode=mode)
                    self.assertEqual(command.count("-i"), inputs)
                    self.assertEqual([command[i + 1] for i, item in enumerate(command) if item == "-map"], maps)
                    self.assertEqual({command[i + 1] for i, item in enumerate(command) if item == "-rtsp_transport"}, {transport})
                    self.assertEqual("-c:v" in command, mode != "audio")
                    self.assertEqual("-c:a" in command, mode != "video")

    def test_defaults_and_environment_validate_transport(self):
        with patch.dict("os.environ", {"RTSP_TRANSPORT": "tcp", "STREAM_MODE": "audio", "HEADSET_RTP_PORT": ""}):
            self.assertEqual(app.parse_args([]).rtsp_transport, "tcp")
            self.assertEqual(app.parse_args([]).stream_mode, "audio")
        with patch.dict("os.environ", {"RTSP_TRANSPORT": "invalid"}), patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                app.parse_args([])

    def test_tcp_does_not_silently_leave_direct_audio_on_udp(self):
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            app.parse_args(["--rtsp-transport", "tcp", "--headset-rtp-port", "8004"])
        with self.assertRaises(ValueError):
            app.publisher_command("192.0.2.1", audio_sdp=Path("audio.sdp"), transport="tcp")
        with self.assertRaises(ValueError):
            mic_command("192.0.2.2", rtp_port=8004, transport="tcp")

    def test_camera_probe_requires_actual_tcp_video_not_audio_or_sdp(self):
        run = Mock(return_value=Mock(returncode=0, stdout='{"streams": [{"codec_type": "audio", "nb_read_packets": "20"}]}'))
        self.assertFalse(check_camera("192.0.2.1", run, "tcp")["verified"])
        run.return_value.stdout = '{"streams": [{"codec_type": "video", "nb_read_packets": "2"}]}'
        self.assertTrue(check_camera("192.0.2.1", run, "tcp")["verified"])
        self.assertEqual(run.call_args.args[0][4], "tcp")
        run.return_value.stdout = 'invalid'
        self.assertFalse(check_camera("192.0.2.1", run, "tcp")["verified"])

    def test_unverified_tcp_leaves_existing_stack_running(self):
        spawn, stop = Mock(), Mock()
        with patch("app.shutil.which", return_value="ffmpeg"):
            with self.assertRaisesRegex(RuntimeError, "TCP media unverified"):
                app.run(app.parse_args(["--rtsp-transport", "tcp"]), spawn=spawn, stop_existing=stop,
                        camera_probe=Mock(return_value={"verified": False, "error": "461"}))
        spawn.assert_not_called()
        stop.assert_not_called()

    def test_recording_and_microphone_use_selected_transport(self):
        command = mic_command("192.0.2.2", transport="tcp", rtsp_port=18554)
        self.assertEqual(command[-1], "rtsp://192.0.2.2:18554/headsetmic")
        self.assertEqual(command[command.index("-rtsp_transport") + 1], "tcp")
        with TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            spawn = Mock(return_value=process)
            manager = RecordingManager(directory, spawn=spawn, transport="tcp", mode="audio")
            manager.start()
            command = spawn.call_args.args[0]
            self.assertNotIn("-c:v", command)
            self.assertEqual(command[command.index("-rtsp_transport") + 1], "tcp")
            manager._close_process()

    def test_talkback_transport_changes_only_rtsp_decoder(self):
        relay = TalkbackRelay(b"t" * 16, ("192.0.2.1", 9002), udp_socket=Mock(), transport="tcp")
        process = Mock()
        cancel = threading.Event()
        def end_stream(*args):
            cancel.set()
            return b""
        process.stdout.read.side_effect = end_stream
        relay.spawn = Mock(return_value=process)
        relay._decode(cancel)
        command = relay.spawn.call_args.args[0]
        self.assertEqual(command[command.index("-rtsp_transport") + 1], "tcp")
        self.assertEqual(relay.target, ("192.0.2.1", 9002))

    def test_measurements_do_not_invent_loss_percent_or_physical_latency(self):
        summary = summarize_log('RTP: missed 4 packets\nmax delay reached\n'
            '[Parsed_ashowinfo_0] pts_time:0 nb_samples:960\n'
            '[Parsed_ashowinfo_0] pts_time:0.06 nb_samples:960\n')
        self.assertEqual(summary["reported_missing_rtp_packets"], 4)
        self.assertAlmostEqual(summary["audio_pts_gap_ms"]["median"], 40)
        self.assertIsNone(summary["end_to_end_latency_ms"]["median"])
        self.assertEqual(distribution(range(1, 21)), {"samples": 20, "median": 10.5, "p95": 19})
        timing = summarize_log('[vost#0:0/copy] muxer <- latency(total:0.25ms, demux-mux: 0.25ms)\n'
                               '[aost#0:1/opus] muxer <- latency(total:1.5ms, demux-mux: 1.5ms)')
        self.assertEqual(timing["ffmpeg_reported_processing_ms"]["video"]["median"], .25)
        self.assertEqual(timing["ffmpeg_reported_processing_ms"]["audio"]["p95"], 1.5)


if __name__ == "__main__":
    unittest.main()
