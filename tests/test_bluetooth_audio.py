import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from maix.bluetooth_audio import BluetoothAudioConnector, LEGACY_ROUTE_MARKER, ROUTE_MARKER, main, reconnect_headset


class BluetoothAudioConnectorTests(unittest.TestCase):
    def test_migrates_previous_managed_audio_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".asoundrc"
            config.write_text(LEGACY_ROUTE_MARKER + "\nold route\n")
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", config_path=config)
            connector._route_playback()
            self.assertTrue(config.read_text().startswith(ROUTE_MARKER))
            self.assertIn('device "28:52:E0:16:73:CE"', config.read_text())

    def test_service_start_reconnects_saved_fixed_device(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token"
            token.write_text("a" * 32)
            selection = Path(directory) / "selected"
            selection.write_text("28:52:E0:16:73:CE\n")
            with patch("sys.argv", ["bluetooth_audio.py", "--token", str(token), "--selection", str(selection)]), \
                 patch("maix.bluetooth_audio.serve") as serve, \
                 patch("maix.bluetooth_audio.BluetoothAudioConnector") as connector, \
                 patch("maix.bluetooth_audio.threading.Thread") as thread:
                main()
            serve.assert_called_once()
            connector.assert_called_once_with("28:52:E0:16:73:CE")
            thread.return_value.start.assert_called_once()
            self.assertTrue(serve.call_args.args[0].fixed_mac)

    def test_reconnect_retries_unavailable_headset_and_recovers(self):
        connector = Mock()
        connector.attempt.side_effect = [False, OSError("offline"), True]
        stop = Mock()
        stop.is_set.return_value = False
        stop.wait.side_effect = [False, False, True]
        reconnect_headset(connector, stop)
        self.assertEqual(connector.attempt.call_count, 3)
        self.assertEqual(stop.wait.call_args.args, (5,))
    def test_pairs_then_connects_and_routes_playback_only(self):
        commands = []

        def run(command, timeout=20):
            commands.append(command)
            if command[1] == "info":
                return 0, "Paired: no\nConnected: no"
            return 0, "successful"

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".asoundrc"
            connector = BluetoothAudioConnector("28:52:e0:16:73:ce", run=run, config_path=config, spawn=lambda *a, **kw: None)
            self.assertTrue(connector.attempt())
            self.assertIn(["bluetoothctl", "pair", "28:52:E0:16:73:CE"], commands)
            self.assertIn(["bluetoothctl", "connect", "28:52:E0:16:73:CE"], commands)
            self.assertIn(["bluetoothctl", "trust", "28:52:E0:16:73:CE"], commands)
            self.assertIn("bluealsa", config.read_text())
            self.assertIn('device "28:52:E0:16:73:CE"', config.read_text())
            self.assertIn('profile "a2dp"', config.read_text())
            self.assertIn('profile "sco"', config.read_text())
            self.assertIn('capture.pcm "bt_input"', config.read_text())

    def test_starts_bluealsa_with_hands_free_gateway(self):
        spawned = []

        def run(command, timeout=20):
            return (1, "") if command[0] == "pidof" else (0, "Paired: yes\nConnected: yes")

        with tempfile.TemporaryDirectory() as directory:
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run,
                                            spawn=lambda command, **kwargs: spawned.append(command),
                                            config_path=Path(directory) / ".asoundrc")
            self.assertTrue(connector.attempt())

        self.assertIn("hfp-ag", spawned[0])

    def test_failed_pair_does_not_change_audio_route(self):
        def run(command, timeout=20):
            if command[1] == "info":
                return 0, "Paired: no\nConnected: no"
            if command[1] == "pair":
                return 1, "ConnectionAttemptFailed"
            return 0, ""

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".asoundrc"
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run, config_path=config, spawn=lambda *a, **kw: None)
            self.assertFalse(connector.attempt())
            self.assertFalse(config.exists())

    def test_rejects_invalid_mac(self):
        with self.assertRaisesRegex(ValueError, "MAC must be"):
            BluetoothAudioConnector('28:52:E0:16:73:CE"; rm -rf /')


if __name__ == "__main__":
    unittest.main()
