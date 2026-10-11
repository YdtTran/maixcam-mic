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
from pc.bluetooth_client import CameraBluetoothClient
from pc.operator_server import RecordingManager, make_handler as operator_handler
from pc.operator_server import main as operator_main


class BluetoothControlTests(unittest.TestCase):
    def test_standalone_operator_wires_camera_clock_to_talkback(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token"
            token.write_text("61" * 16)
            server = Mock()
            server.serve_forever.side_effect = KeyboardInterrupt
            with patch("sys.argv", ["operator", "--talkback-host", "192.0.2.1",
                                    "--talkback-token", str(token), "--recordings", directory]), \
                    patch("pc.bluetooth_client.CameraBluetoothClient") as client, \
                    patch("pc.operator_server.TalkbackRelay") as relay, \
                    patch("pc.operator_server.ThreadingHTTPServer", return_value=server):
                operator_main()
                self.assertIs(relay.call_args.kwargs["clock_sync"], client.return_value.talkback_clock)
            server.server_close.assert_called_once()

    def test_talkback_clock_tracks_camera_time_despite_pc_clock_jumps(self):
        client = CameraBluetoothClient("127.0.0.1", "secret")
        client.request = Mock(return_value=(200, {"time_ms": 1000000}))
        with patch("pc.bluetooth_client.time.monotonic", side_effect=[10, 10.02, 10.11]), \
                patch("pc.bluetooth_client.time.time", return_value=0):
            clock = client.talkback_clock()
            self.assertAlmostEqual(clock(), 1000100, delta=1)
        client.request.assert_called_once_with("clock")

    def test_talkback_clock_rejects_failed_slow_or_invalid_calibration(self):
        client = CameraBluetoothClient("127.0.0.1", "secret")
        for response, elapsed in (((403, {"error": "unauthorized"}), .02),
                                  ((200, {"time_ms": "1000"}), .02),
                                  ((200, {"time_ms": 1000}), 1.1)):
            client.request = Mock(return_value=response)
            with patch("pc.bluetooth_client.time.monotonic", side_effect=[10, 10 + elapsed]), \
                    self.assertRaisesRegex(RuntimeError, "Camera clock unavailable"):
                client.talkback_clock()

    def test_older_camera_clock_falls_back_to_synchronized_system_time(self):
        client = CameraBluetoothClient("127.0.0.1", "secret")
        client.request = Mock(return_value=(404, {}))
        with patch("pc.bluetooth_client.time.time", return_value=100):
            self.assertEqual(client.talkback_clock()(), 100000)

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

    def test_authenticated_camera_scan_and_operator_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selected"
            control = BluetoothControl(path, run=lambda command, timeout=20: (
                0, "Device AA:BB:CC:DD:EE:FF Headset\n" if command[-1] == "devices" else ""))
            camera = ThreadingHTTPServer(("127.0.0.1", 0), camera_handler(control, "secret"))
            camera_thread = threading.Thread(target=camera.serve_forever, daemon=True)
            camera_thread.start()
            client = CameraBluetoothClient("127.0.0.1", "secret")
            client.base = f"http://127.0.0.1:{camera.server_port}/bluetooth"
            operator = ThreadingHTTPServer(("127.0.0.1", 0),
                operator_handler(RecordingManager(directory), bluetooth=client))
            operator_thread = threading.Thread(target=operator.serve_forever, daemon=True)
            operator_thread.start()
            try:
                with self.assertRaises(HTTPError) as error:
                    urlopen(f"http://127.0.0.1:{camera.server_port}/bluetooth/status")
                self.assertEqual(error.exception.code, 403)
                with self.assertRaises(HTTPError) as error:
                    urlopen(f"http://127.0.0.1:{camera.server_port}/bluetooth/clock")
                self.assertEqual(error.exception.code, 403)
                self.assertGreater(client.request("clock")[1]["time_ms"], 0)
                base = f"http://127.0.0.1:{operator.server_port}/api/bluetooth"
                with urlopen(Request(base + "/scan", data=b"", method="POST")) as response:
                    self.assertEqual(json.load(response)["devices"][0]["name"], "Headset")
                body = json.dumps({"mac": "AA:BB:CC:DD:EE:FF"}).encode()
                with urlopen(Request(base + "/select", data=body, method="POST")) as response:
                    self.assertEqual(json.load(response)["selected"], "AA:BB:CC:DD:EE:FF")
                self.assertEqual(path.read_text().strip(), "AA:BB:CC:DD:EE:FF")
            finally:
                operator.shutdown()
                operator.server_close()
                camera.shutdown()
                camera.server_close()
                operator_thread.join()
                camera_thread.join()


if __name__ == "__main__":
    unittest.main()
