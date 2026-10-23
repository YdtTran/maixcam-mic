import tempfile
import json
import threading
import unittest
from unittest.mock import Mock, patch
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from maix.bluetooth_control import BluetoothControl, make_handler as camera_handler, parse_devices
from maix.headset_mic_stream import selected_mac
from maix.bluetooth_control import read_capture_volume
from pc.bluetooth_client import CameraBluetoothClient
from pc.operator_server import RecordingManager, make_handler as operator_handler
from pc.operator_server import main as operator_main


class BluetoothControlTests(unittest.TestCase):
    def test_capture_volume_persists_zero_without_changing_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'selected'
            run = Mock()
            control = BluetoothControl(path, run=run, fixed_mac='AA:BB:CC:DD:EE:FF')
            self.assertEqual(control.capture_volume(), {'volume': 100})
            for value in (50, 0, 100):
                self.assertEqual(control.capture_volume(value), {'volume': value})
                self.assertEqual(read_capture_volume(path), value)
                self.assertEqual(BluetoothControl(path).capture_volume(), {'volume': value})
            run.assert_not_called()
            for value in (-1, 101, True, 1.2, '50'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    control.capture_volume(value)
            path.with_suffix('.capture-volume').write_text('corrupt')
            with self.assertRaises(ValueError):
                control.capture_volume()
            control.capture_volume(100)
            path.unlink()
            with self.assertRaises(RuntimeError):
                control.capture_volume(0)

    def test_pc_entry_points_ignore_legacy_token_files(self):
        import app
        from tests.test_app import fake_media_executable
        for content in (None, "invalid", "62" * 16):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if content is not None:
                    (root / ".talkback_token").write_text(content)
                server = Mock()
                server.serve_forever.side_effect = KeyboardInterrupt
                with patch("sys.argv", ["operator", "--talkback-host", "192.0.2.1", "--recordings", directory]), \
                        patch("pc.operator_server.PROJECT_ROOT", root), \
                        patch("pc.bluetooth_client.CameraBluetoothClient") as client, \
                        patch("pc.operator_server.TalkbackRelay") as relay, \
                        patch("pc.operator_server.ThreadingHTTPServer", return_value=server):
                    operator_main()
                    client.assert_called_once_with("192.0.2.1")
                    self.assertIs(relay.call_args.kwargs["clock_sync"], client.return_value.talkback_clock)
                server.handle_request.side_effect = KeyboardInterrupt
                child = Mock()
                child.poll.return_value = None
                (root / "mediamtx.yml").write_text("# fixture")
                with fake_media_executable(), patch("app.ROOT", root), \
                        patch("app.shutil.which", return_value="ffmpeg"), \
                        patch("app.CameraBluetoothClient") as client, patch("app.TalkbackRelay") as relay:
                    app.run(app.parse_args(["--recordings", directory]), spawn=Mock(return_value=child),
                            server_factory=lambda *a, **k: server, wait_for_relay=lambda p: None,
                            wait_for_audio=lambda p: None, stop_existing=lambda: None)
                    self.assertIs(relay.call_args.kwargs["clock_sync"], client.return_value.talkback_clock)

    def test_removed_token_flags_are_unknown(self):
        import app
        with self.assertRaises(SystemExit):
            app.parse_args(["--talkback-token", "unused"])
        client = CameraBluetoothClient("127.0.0.1", open_url=Mock(side_effect=OSError("offline")))
        self.assertEqual(client.request("status")[0], 503)
        with self.assertRaises(ValueError):
            client.request("unsupported")

    def test_talkback_clock_tracks_camera_time_despite_pc_clock_jumps(self):
        client = CameraBluetoothClient("127.0.0.1")
        client.request = Mock(return_value=(200, {"time_ms": 1000000, "talkback_protocol": "TB3"}))
        with patch("pc.bluetooth_client.time.monotonic", side_effect=[10, 10.02, 10.11]), \
                patch("pc.bluetooth_client.time.time", return_value=0):
            clock = client.talkback_clock()
            self.assertAlmostEqual(clock(), 1000100, delta=1)
        client.request.assert_called_once_with("clock")

    def test_talkback_clock_rejects_failed_slow_or_invalid_calibration(self):
        client = CameraBluetoothClient("127.0.0.1")
        for response, elapsed in (((403, {"error": "unauthorized"}), .02),
                                  ((200, {"time_ms": "1000", "talkback_protocol": "TB3"}), .02),
                                  ((200, {"time_ms": 1000, "talkback_protocol": "TB3"}), 1.1)):
            client.request = Mock(return_value=response)
            with patch("pc.bluetooth_client.time.monotonic", side_effect=[10, 10 + elapsed]), \
                    self.assertRaisesRegex(RuntimeError, "Camera clock unavailable"):
                client.talkback_clock()

    def test_incompatible_camera_requires_paired_update(self):
        client = CameraBluetoothClient("127.0.0.1")
        for response in ((404, {}), (200, {"time_ms": 1000}),
                         (200, {"time_ms": 1000, "talkback_protocol": "TB2"})):
            client.request = Mock(return_value=response)
            with self.assertRaisesRegex(RuntimeError, "update PC and camera together"):
                client.talkback_clock()

    def test_fixed_binding_survives_restart_and_rejects_other_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selected"
            control = BluetoothControl(path, fixed_mac="6c:16:29:7b:00:d4",
                                       run=lambda *a, **k: (0, "Connected: no"))
            self.assertEqual(BluetoothControl(path).selected(), "6C:16:29:7B:00:D4")
            self.assertTrue(control.status()["fixed"])
            with self.assertRaisesRegex(ValueError, "fixed headset"):
                control.select("28:52:E0:16:73:CE")
            self.assertEqual(control.select("6C:16:29:7B:00:D4")["selected"], control.fixed_mac)

    def test_fixed_scan_does_not_discover_or_offer_other_headsets(self):
        commands = []

        def run(command, timeout=20):
            commands.append(command)
            return 0, "Device 6C:16:29:7B:00:D4 Earbuds\nDevice 28:52:E0:16:73:CE Other\n"

        with tempfile.TemporaryDirectory() as directory:
            control = BluetoothControl(Path(directory) / "selected", run=run,
                                       fixed_mac="6C:16:29:7B:00:D4")
            self.assertEqual(control.scan(), [{"mac": control.fixed_mac, "name": "Earbuds"}])
            self.assertEqual(commands, [["bluetoothctl", "devices"]])

    def test_scan_lists_discovered_devices_and_selection_persists(self):
        commands = []

        def run(command, timeout=20):
            commands.append(command)
            if command[-1] == "devices":
                return 0, "Device 28:52:E0:16:73:CE Bluetooth Headset\nDevice AA:BB:CC:DD:EE:FF Speaker\n"
            return 0, ""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selected"
            control = BluetoothControl(path, run=run)
            devices = control.scan()
            self.assertEqual(devices[0]["name"], "Bluetooth Headset")
            self.assertIn(["bluetoothctl", "--timeout", "15", "scan", "on"], commands)
            self.assertIn(["bluetoothctl", "scan", "off"], commands)
            control.select("aa:bb:cc:dd:ee:ff")
            self.assertEqual(control.selected(), "AA:BB:CC:DD:EE:FF")
            self.assertEqual(selected_mac(path), "AA:BB:CC:DD:EE:FF")

    def test_rejects_unknown_or_invalid_device(self):
        with tempfile.TemporaryDirectory() as directory:
            control = BluetoothControl(Path(directory) / "selected", run=lambda *a, **k: (0, ""))
            with self.assertRaises(ValueError):
                control.select("../../bad")
            with self.assertRaises(ValueError):
                control.select("AA:BB:CC:DD:EE:FF")

    def test_scan_includes_all_known_devices_alongside_recent_discoveries(self):
        def run(command, timeout=20):
            if command[-1] == "devices":
                return 0, "Device AA:BB:CC:DD:EE:FF Nearby\nDevice 11:22:33:44:55:66 Old device\n"
            if "scan" in command and command[-1] == "on":
                return 0, "[NEW] Device AA:BB:CC:DD:EE:FF Nearby\n"
            return 0, ""

        with tempfile.TemporaryDirectory() as directory:
            control = BluetoothControl(Path(directory) / "selected", run=run)
            self.assertEqual([item["name"] for item in control.scan()], ["Nearby", "Old device"])
            control.select("11:22:33:44:55:66")

    def test_selection_explicitly_connects_before_activating_audio(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selected"
            control = BluetoothControl(path, run=lambda command, timeout=20: (
                0, "Device AA:BB:CC:DD:EE:FF Headset\n" if command[-1] == "devices" else ""),
                connect=lambda mac: calls.append(mac) or True)
            control.scan()
            self.assertFalse(path.exists())
            control.select("AA:BB:CC:DD:EE:FF")
            self.assertEqual(calls, ["AA:BB:CC:DD:EE:FF"])
            self.assertEqual(path.read_text().strip(), calls[0])

    def test_failed_manual_connection_does_not_activate_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selected"
            control = BluetoothControl(path, run=lambda command, timeout=20: (
                0, "Device AA:BB:CC:DD:EE:FF Headset\n" if command[-1] == "devices" else ""),
                connect=lambda mac: False)
            control.scan()
            with self.assertRaisesRegex(RuntimeError, "Could not connect"):
                control.select("AA:BB:CC:DD:EE:FF")
            self.assertFalse(path.exists())

    def test_device_parser_ignores_noise(self):
        self.assertEqual(parse_devices("junk\nDevice aa:bb:cc:dd:ee:ff Headset\n"),
                         [{"mac": "AA:BB:CC:DD:EE:FF", "name": "Headset"}])

    def test_token_free_camera_scan_and_operator_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selected"
            def run(command, timeout=20):
                return 0, "Device AA:BB:CC:DD:EE:FF Headset\n" if command[-1] == "devices" else ""
            control = BluetoothControl(path, run=run)
            camera = ThreadingHTTPServer(("127.0.0.1", 0), camera_handler(control))
            camera_thread = threading.Thread(target=camera.serve_forever, daemon=True)
            camera_thread.start()
            client = CameraBluetoothClient("127.0.0.1")
            client.base = f"http://127.0.0.1:{camera.server_port}/bluetooth"
            operator = ThreadingHTTPServer(("127.0.0.1", 0),
                operator_handler(RecordingManager(directory), bluetooth=client))
            operator_thread = threading.Thread(target=operator.serve_forever, daemon=True)
            operator_thread.start()
            try:
                for action in ("status", "clock"):
                    with urlopen(f"http://127.0.0.1:{camera.server_port}/bluetooth/{action}") as response:
                        self.assertEqual(json.load(response)["talkback_protocol"], "TB3")
                for body in (b"[]", b"null", b"{", b"{}", bytes(257)):
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(f"http://127.0.0.1:{camera.server_port}/bluetooth/select", data=body))
                    self.assertEqual(error.exception.code, 400)
                self.assertGreater(client.request("clock")[1]["time_ms"], 0)
                base = f"http://127.0.0.1:{operator.server_port}/api/bluetooth"
                with urlopen(Request(base + "/scan", data=b"", method="POST")) as response:
                    self.assertEqual(json.load(response)["devices"][0]["name"], "Headset")
                body = json.dumps({"mac": "AA:BB:CC:DD:EE:FF"}).encode()
                with urlopen(Request(base + "/select", data=body, method="POST")) as response:
                    self.assertEqual(json.load(response)["selected"], "AA:BB:CC:DD:EE:FF")
                self.assertEqual(path.read_text().strip(), "AA:BB:CC:DD:EE:FF")
                with urlopen(base + '/capture-volume') as response:
                    self.assertEqual(json.load(response)['volume'], 100)
                for value in (0, 50, 100):
                    with urlopen(Request(base + '/capture-volume', data=json.dumps({'volume': value}).encode())) as response:
                        self.assertEqual(json.load(response)['volume'], value)
                    self.assertEqual(read_capture_volume(path), value)
                for origin in (base, f'http://127.0.0.1:{camera.server_port}/bluetooth'):
                    for data in (None, b''):
                        with self.subTest(origin=origin, data=data), self.assertRaises(HTTPError) as error:
                            urlopen(Request(origin + '/volume', data=data))
                        self.assertEqual(error.exception.code, 404)
                    for body in (b'{"volume":-1}', b'{"volume":101}', b'{"volume":true}', b'{}',
                                 b'{"volume":null}', b'[]', b'{', b'{"volume":50,"mac":"other"}'):
                        with self.subTest(origin=origin, body=body), self.assertRaises(HTTPError) as error:
                            urlopen(Request(origin + '/capture-volume', data=body))
                        self.assertEqual(error.exception.code, 400)
            finally:
                operator.shutdown()
                operator.server_close()
                camera.shutdown()
                camera.server_close()
                operator_thread.join()
                camera_thread.join()


if __name__ == "__main__":
    unittest.main()
