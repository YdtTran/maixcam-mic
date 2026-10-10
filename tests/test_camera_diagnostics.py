import unittest
from unittest.mock import Mock

from pc.camera_diagnostics import CameraDiagnostics, DEFAULT_USB_IP, probe
import app


class CameraDiagnosticsTests(unittest.TestCase):
    def test_usb_fallback_when_wifi_services_unreachable(self):
        probe_host = Mock(side_effect=[{"reachable": False}, {"reachable": True}])
        result = CameraDiagnostics("192.168.1.7", probe_host=probe_host).check()
        self.assertEqual([call.args[0] for call in probe_host.call_args_list], ["192.168.1.7", DEFAULT_USB_IP])
        self.assertIn("use USB to diagnose", result["message"])
        self.assertEqual(result["media_ip"], "192.168.1.7")

    def test_service_failure_on_reachable_wifi_does_not_trigger_usb(self):
        probe_host = Mock(return_value={"reachable": True})
        result = CameraDiagnostics("192.168.1.7", probe_host=probe_host).check()
        probe_host.assert_called_once_with("192.168.1.7")
        self.assertIsNone(result["usb"])

    def test_connection_failures_are_reported_per_service(self):
        connect = Mock(side_effect=OSError("unreachable"))
        result = probe("10.172.16.1", connect)
        self.assertFalse(result["reachable"])
        self.assertEqual(result["tcp_services"], {"ssh": False, "rtsp_control": False, "bluetooth_control": False})

    def test_both_networks_unreachable_is_reported(self):
        result = CameraDiagnostics("192.168.1.7", probe_host=lambda host: {"reachable": False}).check()
        self.assertIn("Wi-Fi and USB services unreachable", result["message"])

    def test_cli_default_and_override(self):
        self.assertEqual(app.parse_args([]).maix_usb_ip, DEFAULT_USB_IP)
        self.assertEqual(app.parse_args(["--maix-usb-ip", "10.172.17.1"]).maix_usb_ip, "10.172.17.1")
