# Hard-fresh paired reinstall — 2026-10-23

The user requested stopping all Docker containers and MaixCAM application
processes, reinstalling both devices on every run, ignoring saved application
configuration and backups, then performing actual deployment. This supersedes
the previous incremental deployment/rollback policy. Existing unrelated working
tree edits were retained.

## Resulting workflow

- `scripts/deploy.ps1` requires `-WifiSsid` and `-HeadsetMac`. Inventory checks
  board/network identity without requiring previous WorkerCam files or settings.
- Under the existing host lock, fresh maintenance stops every running container
  on the current Docker engine and removes this project's containers/network.
  Old maintenance and camera-view files are reset. Active captures may be
  interrupted; completed recording media is retained. Other projects stay stopped.
- `.env` is generated from the repository template and discovered addresses.
  Runtime shell overrides are cleared. Camera settings use the explicit headset
  MAC and SCO defaults. No saved headset/audio-profile configuration is read.
- Camera installation stages and validates sources, disables old autostart,
  stops the application launcher/video/audio processes and their children,
  resets application ALSA/headset selection, overwrites sources and boot setup,
  and reboots. Existing Bluetooth bonds and firmware networking are retained.
- The PC image is built with `--no-cache` and recreated. Verification includes
  protocol/process/media checks; source now also requires the headset connected.
- Removed hash-based skipping, application backups, rollback tagging/recovery
  and the unused previous-runtime snapshot helper. `-Force` remains accepted
  for compatibility. A failed combined install can be rerun directly: stale
  maintenance is replaced only after acquiring the host lock and stopping runtime.
- `run_all.ps1` delegates to the same complete reinstall and opens the browser
  after success. Component-specific deployment/stop tools remain available.
- Each fresh SSH context uses disposable known_hosts. This avoids stale keys
  while retaining USB/Wi-Fi identity matching during the run. Explicit standalone
  fingerprint checks retain the existing saved-key behavior.
- A previously unknown headset triggers bounded Bluetooth discovery before
  pairing. A transient D-Bus error still does not trigger pairing.

The installer requires Windows Docker Desktop/OpenSSH and camera firmware with
MaixPy, its app launcher, Python, BlueZ/BlueALSA, FFmpeg, ALSA and SCO utilities.
It installs the application, not Windows prerequisites or camera firmware.
Wi-Fi joining retains its independent network-file recovery; application
rollback has been removed. Customer and installer guides reflect these boundaries.

## Actual deployment

Two hidden elevated PowerShell runs completed with exit 0:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy.ps1 -WifiSsid 'P526_5G' -HeadsetMac '6C:16:29:7B:00:D4' -UsbPeerIP 10.172.16.1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_all.ps1 -WifiSsid 'P526_5G' -HeadsetMac '6C:16:29:7B:00:D4' -UsbPeerIP 10.172.16.1 -NoBrowser
```

Both reset configuration, installed/rebooted camera and rebuilt the entire PC
image without cache. PC Wi-Fi is 192.168.1.4, camera Wi-Fi 192.168.1.7, camera
hardware MAC a8:b5:8e:22:37:54. The second run selected the same board through
10.172.17.1 after deduplicating its two USB interfaces. An explicit peer is a
discovery hint within its matching subnet; it does not suppress other adapters.

The first run encountered a stale saved key at the secondary USB address but
successfully used the primary address. Disposable host-key handling was added;
the second run verified both USB endpoints without the old mismatch warning.

Before the second run, `/root/workercam.env` was deliberately removed over SSH.
The complete deployment succeeded without it, demonstrating the new camera
bootstrap path. Automatic review rejected removing local `.env` for the analogous
live experiment; that deletion was not performed. Missing local `.env` and empty
camera settings are exercised together in the isolated integration fixture.
The real installer overwrote local `.env` from the template on both runs.

Ignored transcripts: `.runtime/hard-fresh-deploy.log` and
`.runtime/hard-fresh-second-deploy.log`, with matching exit files. The elevated
runner is `.runtime/hard-fresh-deploy.ps1` (updated to the second command).

## Verification and acceptance

- Final Python suite: 221 tests ran, eight skipped, no failures. Evidence:
  `.runtime/hard-fresh-final-python-retry.log`. Focused deployment/Bluetooth
  checks also passed. One initial test still expected camera backups and was
  updated to assert process stopping before replacement. A full-suite attempt
  overlapping a fixture edit was interrupted; the final clean rerun above passed.
- Docker frontend compilation/type checks passed during both fresh builds.
  The unchanged frontend source/compiled browser unit suite was not rerun.
- Real Chromium: clear 768x432 live video at 0/90 degrees, Talk start/stop,
  rotation locking during capture, a seven-second recording, portrait playback,
  seeking, native download, HTTP 206 range and return to clear live all passed.
  Portrait screenshot was visually inspected; no page errors.
- Recording `20261023T064115Z_cd584a89.mp4`: 2,814,643 bytes; H.264 768x432,
  90-degree display matrix and three AAC tracks. Original and native download
  SHA256 both `86c243073c9810088e30565e4424cba8b3a48fe93aeed7306d8ff096a65510ee`.
- A real 60.178-second browser continuity check passed: 1,204 additional decoded
  frames (20.01 fps), increasing decoded
  video frames and PCMU audio bytes at every five-second sample, zero reported
  packet loss and no page errors. Audio was unmuted/playing.
- Independent headset return decode contained nonzero microphone data.
  The user explicitly confirmed **both speech directions audible** on the
  final deployment after refreshing their browser.
- `git diff --check` and PowerShell parsing passed.

Browser evidence: `.runtime/hard-fresh-live-ui-result.json`,
`.runtime/hard-fresh-live-{0,90,recording}.png`,
`.runtime/hard-fresh-live-continuity.{json,log,png}`.

Final runtime: Docker healthy, EDIFIER headset connected, TB3 Talk available,
rotation 0, recording idle and maintenance released. No automatic rollback or
old-release restoration occurred. Completed recordings and historical snapshots
were not deleted. The fresh application install was verified on the existing
supported firmware; factory-reset firmware, first physical pairing of an unknown
headset, long-duration stability and physical latency remain untested.

A final PC API snapshot briefly reported headset disconnected. A read-only Wi-Fi
SSH check then found connected Bluetooth ACL/eSCO links and a repeated PC status
returned connected; no repair was performed. The cause of the transient status
is unproven. USB 10.172.16.1 timed out during that check; Wi-Fi SSH succeeded.
The second deploy had already selected and verified USB 10.172.17.1. Audio logs
span boots and include earlier startup retries, so their undated messages are
not evidence of a current persistent failure.
