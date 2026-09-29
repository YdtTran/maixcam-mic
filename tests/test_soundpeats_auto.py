import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from maix.soundpeats_auto import SoundpeatsConnector, main


class SoundpeatsConnectorTests(unittest.TestCase):
    def test_service_start_does_not_connect_saved_device(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token"
            token.write_text("a" * 32)
            selection = Path(directory) / "selected"
            selection.write_text("28:52:E0:16:73:CE\n")
            with patch("sys.argv", ["soundpeats_auto.py", "--token", str(token), "--selection", str(selection)]), \
                 patch("maix.soundpeats_auto.serve") as serve, \
                 patch("maix.soundpeats_auto.SoundpeatsConnector") as connector, \
                 patch("maix.soundpeats_auto.time.sleep", side_effect=KeyboardInterrupt):
                try:
                    main()
                except KeyboardInterrupt:
                    pass
            serve.assert_called_once()
            connector.assert_not_called()
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
            self.assertIn('profile "a2dp"', config.read_text())
            self.assertIn('profile "sco"', config.read_text())
            self.assertIn('capture.pcm "bt_input"', config.read_text())

    def test_starts_bluealsa_with_hands_free_gateway(self):
        spawned = []

        def run(command, timeout=20):
            return (1, "") if command[0] == "pidof" else (0, "Paired: yes\nConnected: yes")

        with tempfile.TemporaryDirectory() as directory:
            connector = SoundpeatsConnector("28:52:E0:16:73:CE", run=run,
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
            connector = SoundpeatsConnector("28:52:E0:16:73:CE", run=run, config_path=config, spawn=lambda *a, **kw: None)
            self.assertFalse(connector.attempt())
            self.assertFalse(config.exists())

    def test_rejects_invalid_mac(self):
        with self.assertRaisesRegex(ValueError, "MAC must be"):
            SoundpeatsConnector('28:52:E0:16:73:CE"; rm -rf /')


if __name__ == "__main__":
    unittest.main()
