import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import app


@contextmanager
def fake_media_executable():
    with TemporaryDirectory() as directory:
        executable = Path(directory) / app.media_executable().name
        executable.touch()
        with patch("app.media_executable", return_value=executable):
            yield


class AppTests(unittest.TestCase):
    def test_media_executable_matches_host_platform(self):
        self.assertEqual(app.media_executable("nt"), app.ROOT / "mediamtx.exe")
        self.assertEqual(app.media_executable("posix"), app.ROOT / "mediamtx")

    def test_stops_only_previous_processes_for_this_host(self):
        processes = [
            {"id": 101, "path": str(app.ROOT / "mediamtx.exe"), "command_line": ""},
            {"id": 102, "path": r"C:\other\mediamtx.exe", "command_line": ""},
            {"id": 103, "path": r"C:\tools\ffmpeg.exe", "command_line":
             "ffmpeg -i rtsp://10.127.15.230:8554/live -c:a libopus -f rtsp rtsp://127.0.0.1:8554/maix01"},
            {"id": 104, "path": r"C:\tools\ffmpeg.exe", "command_line":
             "ffmpeg -i rtsp://127.0.0.1:8554/maix01 recording.mp4"},
            {"id": 105, "path": r"C:\Python\python.exe", "command_line":
             '"C:\\Python\\python.exe" app.py'},
            {"id": 106, "path": r"C:\Python\python.exe", "command_line":
             'python -m pc.operator_server --source rtsp://10.127.9.237:8554/maix01'},
            {"id": 107, "path": r"C:\Python\python.exe", "command_line":
             'python unrelated_app.py'},
        ]
        killed = []

        app.stop_previous_host(processes, killed.append, current_pid=999,
                               operator_pids={105, 106, 107})

        self.assertEqual(killed, [101, 103, 105, 106])

    def test_publisher_reads_camera_and_publishes_to_local_relay(self):
        command = app.publisher_command("10.127.15.230", "ffmpeg")
        self.assertIn("rtsp://10.127.15.230:8554/live", command)
        self.assertIn("rtsp://127.0.0.1:8554/air6mic", command)
        self.assertEqual(command[-1], "rtsp://127.0.0.1:8554/maix01")
        self.assertEqual(command[command.index("-map") + 3], "1:a:0")
        self.assertEqual(command[command.index("-bsf:v") + 1],
                         "filter_units=remove_types=0,dump_extra=freq=keyframe")
        self.assertEqual(command[command.index("-c:a") + 1], "libopus")
        self.assertNotIn("-rw_timeout", command)
        self.assertIn("nobuffer", command)

    def test_stops_both_children_when_server_exits(self):
        relay = Mock()
        publisher = Mock()
        relay.poll.return_value = None
        publisher.poll.return_value = None
        server = Mock()
        server.handle_request.side_effect = KeyboardInterrupt
        spawn = Mock(side_effect=[relay, publisher])
        args = app.parse_args(["--maix-ip", "10.127.15.230"])

        with fake_media_executable(), patch("app.shutil.which", return_value="ffmpeg"):
            app.run(args, spawn=spawn, server_factory=lambda *a, **k: server,
                    wait_for_relay=lambda process: None, wait_for_audio=lambda process: None,
                    stop_existing=lambda: None)

        self.assertEqual(spawn.call_count, 2)
        self.assertEqual(Path(spawn.call_args_list[0].args[0][0]).name, "mediamtx.exe")
        self.assertEqual(spawn.call_args_list[1].args[0][0], "ffmpeg")
        relay.terminate.assert_called_once()
        publisher.terminate.assert_called_once()
        server.server_close.assert_called_once()

    def test_restarts_publisher_after_headset_mic_reconnects(self):
        relay = Mock()
        first_publisher = Mock()
        next_publisher = Mock()
        relay.poll.return_value = None
        first_publisher.poll.return_value = 1
        next_publisher.poll.return_value = None
        server = Mock()
        server.handle_request.side_effect = KeyboardInterrupt
        spawn = Mock(side_effect=[relay, first_publisher, next_publisher])
        wait_for_audio = Mock()

        with fake_media_executable(), patch("app.shutil.which", return_value="ffmpeg"):
            app.run(app.parse_args([]), spawn=spawn, server_factory=lambda *a, **k: server,
                    wait_for_relay=lambda process: None, wait_for_audio=wait_for_audio,
                    stop_existing=lambda: None)

        self.assertEqual(spawn.call_count, 3)
        self.assertEqual(wait_for_audio.call_count, 2)
        next_publisher.terminate.assert_called_once()

    def test_restarts_stalled_publisher_when_relay_path_disappears(self):
        relay = Mock()
        stalled_publisher = Mock()
        replacement = Mock()
        relay.poll.return_value = None
        stalled_publisher.poll.return_value = None
        replacement.poll.return_value = None
        server = Mock()
        server.handle_request.side_effect = KeyboardInterrupt
        spawn = Mock(side_effect=[relay, stalled_publisher, replacement])
        path_available = Mock(return_value=False)

        with fake_media_executable(), patch("app.shutil.which", return_value="ffmpeg"), \
             patch("app.time.monotonic", side_effect=[0, 11, 11]):
            app.run(app.parse_args([]), spawn=spawn, server_factory=lambda *a, **k: server,
                    wait_for_relay=lambda process: None, wait_for_audio=lambda process: None,
                    stop_existing=lambda: None, path_available=path_available)

        path_available.assert_called_once_with("maix01")
        stalled_publisher.terminate.assert_called_once()
        replacement.terminate.assert_called_once()

    def test_cleans_previous_host_before_starting_new_relay(self):
        events = []
        relay = Mock()
        publisher = Mock()
        relay.poll.return_value = None
        publisher.poll.return_value = None
        server = Mock()
        server.handle_request.side_effect = KeyboardInterrupt

        def spawn(*args, **kwargs):
            events.append("spawn")
            return relay if events.count("spawn") == 1 else publisher

        with fake_media_executable(), patch("app.shutil.which", return_value="ffmpeg"):
            app.run(app.parse_args([]), spawn=spawn,
                    server_factory=lambda *a, **k: server,
                    wait_for_relay=lambda process: None, wait_for_audio=lambda process: None,
                    stop_existing=lambda: events.append("cleanup"))

        self.assertEqual(events[:2], ["cleanup", "spawn"])

    def test_cleans_up_relay_if_it_does_not_start(self):
        relay = Mock()
        relay.poll.return_value = None
        spawn = Mock(return_value=relay)
        args = app.parse_args([])

        with fake_media_executable(), patch("app.shutil.which", return_value="ffmpeg"):
            with self.assertRaisesRegex(RuntimeError, "MediaMTX"):
                app.run(args, spawn=spawn,
                        wait_for_relay=lambda process: (_ for _ in ()).throw(RuntimeError("MediaMTX failed")),
                        wait_for_audio=lambda process: None,
                        stop_existing=lambda: None)

        self.assertEqual(spawn.call_count, 1)
        relay.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
