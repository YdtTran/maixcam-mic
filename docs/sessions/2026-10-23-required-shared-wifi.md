# Required shared Wi-Fi setup — 2026-10-23

The user requested an SSID parameter sent to MaixCAM, camera Wi-Fi MAC reporting
and a mandatory shared network with the PC host. On clarification, they chose
automatic switching with a supplied Wi-Fi password when the camera is on a
different network. Previous firewall changes in this working tree are retained.

## Behavior

`scripts/deploy.ps1` and `deploy_maix.ps1` require `-WifiSsid`; the connected PC
adapter's SSID must match exactly. `run_all.ps1 -DeployMaix` requires and forwards
the same parameter. Normal PC-only startup keeps its existing interface.

Example from elevated PowerShell, replacing the placeholder with the PC SSID:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& .\scripts\deploy.ps1 -WifiSsid 'YOUR_PC_WIFI_SSID' -WifiPassword (Read-Host 'Wi-Fi password' -AsSecureString)"
```

The automatic entry point identifies a prepared camera over verified USB SSH,
including when its Wi-Fi has no IP. It reports the camera Wi-Fi MAC and checks
the saved fixed headset identity before changes. If needed, supplied credentials
join the required PC network under project maintenance, renew DHCP and return
the new IP. Wi-Fi SSH must retain the USB host identity and MAC, and routing must
use the chosen PC Wi-Fi interface. Normal deployment then uses the discovered
addresses, including refreshing the UDP firewall rule.

`maix/setup_wifi.py` is executed through SSH stdin rather than installed as a
daemon. It selects the required network, saves supplicant configuration and
copies it atomically to `/boot/wpa_supplicant.conf` so camera reboot retains it.
It saves the current profile even when the camera is already on the required
SSID, without replacing its credentials or renewing DHCP. Private backups live
under `/root/workercam-wifi-backup-*`; failed setup restores previous files and
requests the prior association. Successful Wi-Fi changes survive later
application deployment rollback.

Windows receives the password as SecureString. JSON containing credentials goes
only through encrypted SSH stdin, excluded from Windows arguments and logs. The
camera derives a PSK before calling wpa_cli; no plaintext passphrase is placed
in that command's arguments. The PSK and backups remain sensitive camera files.
Camera `/root/workercam.env` receives `WIFI_SSID_B64` and `WIFI_MAC`, plus existing
PC/headset/audio settings. SSID data is encoded rather than interpolated into
shell syntax. Installer and post-deployment checks require the same SSID/MAC;
no new Bluetooth pairing or MAC mutation occurs.

Dry runs remain read-only, including when a Wi-Fi switch is needed. They report
the switch plan without requiring its password; future Wi-Fi routing and media
cannot be verified until an actual run. Root README, deployment guide and the
standalone camera example document the required flags.

## Verification and limits

Final check:

```text
python -m unittest tests.test_setup_wifi tests.test_start_scripts tests.test_network_deployment -v
Ran 56 tests in 88.575s — OK (55 passed, one POSIX boot-shell test skipped)
```

PowerShell syntax parsing passed for all five affected scripts/modules and
`git diff --check` passed. Password examples use `-Command` when launching a
child PowerShell, preserving SecureString input inside that process.
After that run, the SSH JSON payload was wrapped in base64 to preserve UTF-8
through Windows stdin encodings; its targeted credential-forwarding test,
PowerShell syntax parsing and diff checks passed again.

Focused tests cover Windows adapter selection, SSID mismatch rejection, SSH
stdin credential forwarding, read-only dry runs, switching over USB before
deployment, shell-sensitive and escaped UTF-8 SSIDs, camera MAC validation,
camera boot persistence, DHCP failure, association timeout, failed save recovery
and redacted error output. Existing deployment/recording/rollback tests use
updated fixtures with the required SSID. Tests mock network, camera and firewall
operations; they do not establish live acceptance.

Two new PowerShell fixture checks initially failed because this environment
could not auto-load Microsoft.PowerShell.Security for ConvertTo-SecureString.
Test fixtures now construct SecureString through .NET; production password
input remains Read-Host -AsSecureString. Both targeted checks then passed.
One intermediate documentation write introduced a Windows encoding/newline
mismatch; UTF-8 and line endings were corrected before final verification.

Provisioning supports WPA/WPA2-Personal with an 8–63 printable ASCII character
passphrase. Enterprise, open and WPA3-only provisioning is outside this change.
Unknown Windows netsh output formats or unavailable location permission fail
closed instead of guessing the SSID. A failed Wi-Fi switch may need USB recovery
and leaves maintenance retained; recovery requests are not proof of restored
radio/DHCP connectivity.

No live camera Wi-Fi configuration, firewall change, deployment or service
restart was performed. Implemented; redeployment verification pending, including
reboot persistence and picture/listening/Talk acceptance on actual devices.
