# Hard-fresh Windows deployment

Run in administrator PowerShell from the repository, with Docker Desktop's Linux
engine running, the PC on Wi-Fi and MaixCAM connected over USB:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& .\scripts\deploy.ps1 -WifiSsid 'YOUR_PC_WIFI_SSID' -HeadsetMac '6C:16:29:7B:00:D4' -WifiPassword (Read-Host 'Wi-Fi password' -AsSecureString)"
```

Replace the headset MAC for other earbuds. Root/root camera SSH is automatic.
No existing `.env`, saved credentials or WorkerCam camera files are required.
The Wi-Fi password is needed when the camera has not joined the requested SSID.
Put previously unpaired earbuds into pairing mode and keep them powered on.

## Each run

1. Discover USB camera identity, hardware Wi-Fi MAC and PC Wi-Fi address. Validate
   that the requested SSID matches the PC. No old WorkerCam settings are read.
2. Acquire the project host lock. Stop **every running Docker container on the
   current Docker engine**, including other projects, then remove WorkerCam's
   containers/network. Other projects are left stopped, not restarted.
3. Reset any old maintenance marker and camera-view selection. Generate `.env`
   from `.env.example` and current discovered addresses; shell overrides for the
   runtime settings are cleared. Existing recording media is retained.
4. Join/persist camera Wi-Fi if needed. Validate firmware tools, upload sources,
   stop the old camera launcher/video/audio processes and their media children,
   reset the application ALSA/headset selection, overwrite programs and settings,
   and reboot. The defaults are SCO duplex, TCP video, native 768x432/20fps and
   PC multistream recording. Bluetooth bonds and OS networking remain available.
5. Build the PC image with `docker compose build --no-cache`, recreate/start it,
   refresh the camera UDP firewall rule and verify Windows HTTP/container health.
6. Verify camera process uniqueness, TB3 compatibility, both real media decodes
   and Talk availability. Release maintenance only after successful checks.

There is no application snapshot, old-image tagging, deployment hash shortcut or
rollback. `-Force` is accepted for compatibility; every normal run is forced.
Failed installs retain maintenance. Rerunning this same command takes a new lock,
stops everything again and replaces the stale marker; no manual recovery-owner
step is needed. Concurrent deployments still refuse the held host lock.
Finish recordings before deployment: hard stopping can interrupt an active file.

Wi-Fi provisioning retains its separate network-file recovery on failed joining;
that does not restore an old application release. The camera firmware, SSH/USB
networking, Python 3/MaixPy launcher, BlueZ, BlueALSA, FFmpeg, ALSA tools and SCO
controller utilities must already exist. Buildroot firmware is not flashed or
modified by this installer. Windows requires Docker Desktop and OpenSSH Client;
Docker builds the frontend and packages the PC runtime without host Node/Python.

Each install uses temporary SSH known_hosts rather than saved user keys. Within
the run, the Wi-Fi endpoint is checked against USB identity and hardware MAC.
Wi-Fi credentials travel through SSH stdin and are persisted for camera reboot.
WPA/WPA2-Personal (8–63 printable ASCII characters) is supported. No SSH password
prompt is needed; explicit key/password overrides remain supported.

## Entry points and checks

`run_all.ps1 -WifiSsid <SSID> -HeadsetMac <MAC>` invokes this same full workflow
and opens the browser after success (`-NoBrowser` suppresses opening).
The lower-level `deploy_pc.ps1` and `deploy_maix.ps1` remain component tools;
use the combined entry point for complete fresh installation.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy.ps1 -WifiSsid 'YOUR_PC_WIFI_SSID' -HeadsetMac '6C:16:29:7B:00:D4' -DryRun
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy.ps1 -WifiSsid 'YOUR_PC_WIFI_SSID' -HeadsetMac '6C:16:29:7B:00:D4' -WifiInterfaceIndex 20 -UsbInterfaceIndex 19 -UsbPeerIP 10.172.16.1
```

Dry run does discovery without changing files, network membership or services.
It does not prove installation or media acceptance. Interface indices/addresses
are examples; omit them for automatic discovery. USB needs an enabled RNDIS/NCM
adapter. For subnets wider than /22, provide `-UsbPeerIP` if no peer is discovered.
A supplied peer must still belong to the USB subnet.

## Windows firewall and missing headset microphone audio

Setup refreshes **MaixCAM headset UDP from camera**: inbound UDP 8004/8005,
all Windows network profiles, from the newly discovered camera Wi-Fi IP.
`deploy_pc.ps1` also applies this rule. Missing Windows UDP listeners trigger
one container recreation; missing headset media permits one PC stop/start to
refresh Docker forwarding before final verification. Persistent failures fail
deployment with logs; the same fresh command can be rerun after correction.

After success open http://127.0.0.1:8000, log in as admin/admin and select Worker
#07. Check moving video, rotation, Enable audio, held Talk, recording, playback
and download. Media decode and API availability cannot prove intelligible speech;
confirm both audible directions with a person. See the [customer README](../README.md).

For diagnostics:

```powershell
docker compose ps
docker compose logs --tail 80 server
```

Standalone component maintenance retains recording-safe checks and the recovery
tool `recover_maintenance.ps1`. These do not block a new combined fresh reinstall.
