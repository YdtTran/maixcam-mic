import tempfile
import unittest
from pathlib import Path

from maix.soundpeats_auto import SoundpeatsConnector


class SoundpeatsConnectorTests(unittest.TestCase):
    def test_pairs_then_connects_and_routes_playback_only(self):
        commands = []

        def run(command, timeout=20):
            commands.append(command)
            if command[1] == "info":
                return 0, "Paired: no\nConnected: no"
            return 0, "successful"

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".asoundrc"
            connector = SoundpeatsConnector("28:52:e0:16:73:ce", run=run, config_path=config, spawn=lambda *a, **kw: None)
            self.assertTrue(connector.attempt())
            self.assertIn(["bluetoothctl", "pair", "28:52:E0:16:73:CE"], commands)
            self.assertIn(["bluetoothctl", "connect", "28:52:E0:16:73:CE"], commands)
            self.assertIn("bluealsa", config.read_text())
            self.assertIn('device "28:52:E0:16:73:CE"', config.read_text())
            self.assertIn('channels 2', config.read_text())
            self.assertIn('capture.pcm "hw:0,0"', config.read_text())

    def test_failed_pair_does_not_change_audio_route(self):
        def run(command, timeout=20):
            if command[1] == "info":
                return 0, "Paired: no\nConnected: no"
            if command[1] == "pair":
                return 1, "ConnectionAttemptFailed"
            return 0, ""

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".asoundrc"
            connector = SoundpeatsConnector("28:52:E0:16:73:CE", run=run, config_path=config, spawn=lambda *a, **kw: None)
            self.assertFalse(connector.attempt())
            self.assertFalse(config.exists())

    def test_rejects_invalid_mac(self):
        with self.assertRaisesRegex(ValueError, "MAC must be"):
            SoundpeatsConnector('28:52:E0:16:73:CE"; rm -rf /')


if __name__ == "__main__":
    unittest.main()
