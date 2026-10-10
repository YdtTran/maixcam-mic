import tempfile
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from maix.bluetooth_control import BluetoothControl, make_handler as camera_handler, parse_devices
from maix.headset_mic_stream import selected_mac
from pc.bluetooth_client import CameraBluetoothClient
from pc.operator_server import RecordingManager, make_handler as operator_handler


class BluetoothControlTests(unittest.TestCase):
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
