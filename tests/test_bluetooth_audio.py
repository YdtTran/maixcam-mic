import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from maix.bluetooth_audio import BluetoothAudioConnector, LEGACY_ROUTE_MARKER, ROUTE_MARKER, main, reconnect_headset


class BluetoothAudioConnectorTests(unittest.TestCase):
    def test_prepare_sco_cli_does_not_start_services_and_propagates_failure(self):
        arguments = ["bluetooth_audio.py", "--fixed-mac", "28:52:E0:16:73:CE",
                     "--playback-profile", "sco", "--sco-mtu", "120", "--prepare-sco"]
        with patch("sys.argv", arguments), patch("maix.bluetooth_audio.BluetoothAudioConnector") as factory, \
             patch("maix.bluetooth_audio.serve") as serve, patch("maix.bluetooth_audio.threading.Thread") as thread:
            connector = factory.return_value
            connector.prepare_sco.return_value = False
            with self.assertRaises(SystemExit) as failure:
                main()
            self.assertEqual(failure.exception.code, 1)
            connector._route_playback.assert_not_called()
            connector.prepare_sco.return_value = True
            main()
            connector._route_playback.assert_called_once()
            serve.assert_not_called()
            thread.assert_not_called()

    def test_unverified_mtu_prevents_bluealsa_start(self):
        commands = []
        def run(command, timeout=20):
            commands.append(command)
            return 0, "SCO MTU: 255:4\nUP RUNNING"
        connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run,
                                            playback_profile="sco", sco_mtu=120)
        self.assertFalse(connector.attempt())
        self.assertFalse(any(c[0] == "pidof" for c in commands))

    def test_prepare_sco_powers_controller_before_mtu_and_before_bluealsa(self):
        commands = []
        powered, mtu = False, 120

        def run(command, timeout=20):
            nonlocal powered, mtu
            commands.append(command)
            if command == ["hciconfig", "hci0", "up"]:
                powered, mtu = True, 255  # Controller initialization resets MTU.
            elif "scomtu" in command:
                mtu = 120
            if command[:2] == ["hciconfig", "hci0"]:
                return 0, f"SCO MTU: {mtu}:4\n\t{'UP RUNNING' if powered else 'DOWN'}\n"
            return 0, "Paired: yes\nTrusted: yes\nConnected: yes"

        with tempfile.TemporaryDirectory() as directory:
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run,
                config_path=Path(directory) / "alsa", playback_profile="sco", sco_mtu=120)
            self.assertTrue(connector.attempt())
        self.assertIn(["hciconfig", "hci0", "up"], commands)
        self.assertLess(commands.index(["hciconfig", "hci0", "up"]),
                        commands.index(["hciconfig", "hci0", "scomtu", "120:4"]))
        self.assertLess(commands.index(["hciconfig", "hci0", "scomtu", "120:4"]),
                        commands.index(["pidof", "bluealsa"]))
        self.assertEqual(mtu, 120)

    def test_prepare_sco_failed_power_up_prevents_audio_start(self):
        commands = []
        def run(command, timeout=20):
            commands.append(command)
            if command[-1] == "up":
                return 1, "not ready"
            return 0, "SCO MTU: 255:4\n\tDOWN\n"
        with tempfile.TemporaryDirectory() as directory:
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run,
                config_path=Path(directory) / "alsa", playback_profile="sco", sco_mtu=120)
            self.assertFalse(connector.attempt())
        self.assertFalse(any(c[0] in ("pidof", "bluetoothctl") or "scomtu" in c for c in commands))

    def test_failed_sco_reset_obeys_cooldown_and_blocks_reconnect_in_that_attempt(self):
        commands = []
        now = [30.0]
        def run(command, timeout=20):
            commands.append(command)
            if command[0] == "hcitool":
                return 0, "< eSCO 28:52:E0:16:73:CE handle 384 state 8"
            if command[-1] == "reset": return 1, "failed"
            return 0, "Paired: yes\nTrusted: yes\nConnected: yes"
        with tempfile.TemporaryDirectory() as directory:
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run,
                                                config_path=Path(directory) / "alsa", playback_profile="sco",
                                                recover_stuck_sco=True, monotonic=lambda: now[0])
            connector.stuck_sco_since = 0
            self.assertFalse(connector.attempt())
            self.assertFalse(any(c[0] == "bluetoothctl" for c in commands))
            now[0] = 40
            connector.attempt()
            self.assertEqual(sum(c[-1] == "reset" for c in commands), 1)

    def test_stuck_sco_recovery_waits_for_persistent_state_and_restores_mtu(self):
        now = [0.0]
        commands = []
        mtu = [120]
        def run(command, timeout=20):
            commands.append(command)
            if command[0] == "hcitool":
                return 0, "< eSCO 28:52:E0:16:73:CE handle 384 state 8 lm CENTRAL"
            if command[0] == "hciconfig":
                if command[-1] == "reset":
                    mtu[0] = 255
                elif "scomtu" in command:
                    mtu[0] = 120
                return 0, f"SCO MTU: {mtu[0]}:4\nUP RUNNING"
            return 0, "Paired: yes\nTrusted: yes\nConnected: yes"
        with tempfile.TemporaryDirectory() as directory:
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run,
                                                config_path=Path(directory) / "alsa", playback_profile="sco",
                                                sco_mtu=120, recover_stuck_sco=True, monotonic=lambda: now[0])
            connector.attempt()
            now[0] = 29
            connector.attempt()
            self.assertFalse(any(c[-1] == "reset" for c in commands))
            now[0] = 30
            connector.attempt()
            self.assertEqual(mtu[0], 120)
            now[0] = 31
            connector.attempt()
            now[0] = 61
            connector.attempt()
            self.assertEqual(sum(c[-1] == "reset" for c in commands), 1)

    def test_stuck_sco_recovery_refuses_other_devices_and_unknown_status(self):
        for output, code in [("< eSCO 28:52:E0:16:73:CE handle 384 state 8\n> ACL AA:BB:CC:DD:EE:FF handle 1 state 1", 0),
                             ("unavailable", 1)]:
            commands = []
            def run(command, timeout=20):
                commands.append(command)
                if command[0] == "hcitool": return code, output
                return 0, "Paired: yes\nTrusted: yes\nConnected: yes"
            with tempfile.TemporaryDirectory() as directory:
                connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run,
                                                    config_path=Path(directory) / "alsa", playback_profile="sco",
                                                    recover_stuck_sco=True)
                connector.stuck_sco_since = -100
                connector.attempt()
                self.assertFalse(any(c[-1] == "reset" for c in commands))

    def test_stuck_sco_recovery_requires_explicit_sco_profile(self):
        with self.assertRaises(ValueError):
            BluetoothAudioConnector("28:52:E0:16:73:CE", recover_stuck_sco=True)

    def test_sco_mtu_override_preserves_packet_count_and_avoids_repeated_mutations(self):
        commands = []
        current = [255]
        def run(command, timeout=20):
            commands.append(command)
            if command[:2] == ["hciconfig", "hci0"]:
                if len(command) == 4:
                    current[0] = int(command[3].split(":")[0])
                return 0, f"SCO MTU: {current[0]}:4\nUP RUNNING"
            return 0, "Paired: yes\nTrusted: yes\nConnected: yes"
        with tempfile.TemporaryDirectory() as directory:
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run,
                                                config_path=Path(directory) / "alsa",
                                                playback_profile="sco", sco_mtu=120)
            self.assertTrue(connector.attempt())
            self.assertTrue(connector.attempt())
        self.assertEqual([c for c in commands if "scomtu" in c], [["hciconfig", "hci0", "scomtu", "120:4"]])

    def test_failed_sco_mtu_override_does_not_change_route(self):
        def run(command, timeout=20):
            if command[0] == "hciconfig":
                return (0, "SCO MTU: 255:4\nUP RUNNING") if len(command) == 2 else (1, "denied")
            return 0, ""
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "alsa"
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run, config_path=config,
                                                playback_profile="sco", sco_mtu=120)
            self.assertFalse(connector.attempt())
            self.assertFalse(config.exists())

    def test_sco_mtu_override_is_explicit_and_even(self):
        for profile, mtu in [("a2dp", 120), ("sco", 255), ("sco", 0)]:
            with self.subTest(profile=profile, mtu=mtu), self.assertRaises(ValueError):
                BluetoothAudioConnector("28:52:E0:16:73:CE", playback_profile=profile, sco_mtu=mtu)

    def test_connected_trusted_headset_is_not_reconfigured_each_poll(self):
        commands = []
        def run(command, timeout=20):
            commands.append(command)
            return 0, "Paired: yes\nTrusted: yes\nConnected: yes"
        with tempfile.TemporaryDirectory() as directory:
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run,
                                                config_path=Path(directory) / "alsa")
            self.assertTrue(connector.attempt())
            self.assertTrue(connector.attempt())
        mutations = [c for c in commands if c[0] == "bluetoothctl" and c[1] != "info"]
        self.assertEqual(mutations, [])
        self.assertFalse(any(c[0] == "hcitool" for c in commands))

    def test_failed_status_query_does_not_attempt_pair_or_connect(self):
        commands = []
        def run(command, timeout=20):
            commands.append(command)
            return (1, "temporary D-Bus error") if command[1] == "info" else (0, "")
        with tempfile.TemporaryDirectory() as directory:
            connector = BluetoothAudioConnector("28:52:E0:16:73:CE", run=run,
                                                config_path=Path(directory) / "alsa")
            self.assertFalse(connector.attempt())
        self.assertFalse(any(c[1] in ("pair", "trust", "connect") for c in commands))

    def test_failed_reconnects_back_off_and_success_restores_normal_poll(self):
        connector = Mock()
        connector.attempt.side_effect = [False, False, False, False, False, True]
        stop = Mock()
        stop.is_set.return_value = False
        stop.wait.side_effect = [False] * 5 + [True]
        reconnect_headset(connector, stop)
        self.assertEqual([call.args[0] for call in stop.wait.call_args_list], [5, 10, 20, 30, 30, 5])

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
            selection = Path(directory) / "selected"
            selection.write_text("28:52:E0:16:73:CE\n")
            with patch("sys.argv", ["bluetooth_audio.py", "--selection", str(selection)]), \
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
