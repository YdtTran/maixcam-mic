"""Execute the boot script with stub audio services, without hardware access."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


@unittest.skipUnless(os.name != "nt" and shutil.which("sh"), "POSIX boot shell")
class ScoStartupTests(unittest.TestCase):
    def test_failed_preparation_retries_before_any_audio_service_starts(self):
        template = Path(__file__).resolve().parents[1] / "maix" / "background_services.rc.local"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "workercam.env").write_text(
                "PC_IP=192.0.2.1\nHEADSET_MAC=AA:BB:CC:DD:EE:FF\nAUDIO_PROFILE=sco\n")
            python = root / "python3"
            python.write_text('''#!/bin/sh
case "$*" in
  *--prepare-sco*)
    if test ! -f "$TEST_ROOT/attempted"; then
      touch "$TEST_ROOT/attempted"
      echo retry >> "$TEST_ROOT/events"
      exit 1
    fi
    touch "$TEST_ROOT/ready"
    echo ready >> "$TEST_ROOT/events"
    ;;
  *)
    if test ! -f "$TEST_ROOT/ready"; then
      echo premature >> "$TEST_ROOT/events"
    fi
    echo service >> "$TEST_ROOT/events"
    ;;
esac
''')
            python.chmod(0o755)
            sleep = root / "sleep"
            sleep.write_text("#!/bin/sh\nexit 0\n")
            sleep.chmod(0o755)
            for name in ("dmesg", "iw", "iwconfig"):
                stub = root / name
                stub.write_text("#!/bin/sh\nexit 0\n")
                stub.chmod(0o755)
            script = root / "boot.sh"
            script.write_text(template.read_text().replace("/root/", directory + "/"))
            subprocess.run(["sh", str(script)], check=True, timeout=5,
                           env={**os.environ, "PATH": directory + ":" + os.environ["PATH"],
                                "TEST_ROOT": directory})
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                events = (root / "events").read_text().splitlines()
                if events.count("service") == 3:
                    break
                time.sleep(0.01)
            self.assertEqual(events[:2], ["retry", "ready"])
            self.assertEqual(events.count("service"), 3)
            self.assertNotIn("premature", events)


if __name__ == "__main__":
    unittest.main()
