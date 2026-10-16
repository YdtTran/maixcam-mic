# Automatic Windows deployment

From the project root, with MaixCAM connected by a USB **data** cable and both
devices connected to Wi-Fi:

```powershell
.\scripts\deploy.ps1
.\scripts\deploy.ps1 -DryRun
.\scripts\deploy.ps1 -Force -Verbose
```

Requirements: Windows PowerShell 5.1 or PowerShell 7, Windows OpenSSH Client
(`ssh.exe`, `scp.exe`), running Docker Desktop with Linux containers, a prepared
MaixCAM with this project's existing application and `/root/workercam.env`,
and the matching local `.talkback_token`. Finish recordings/finalization first.
No local Node, Python, PuTTY, serial port or administrator session is required
for deployment. Docker builds the frontend and PC runtime.

## Credentials (once per Windows account)

The script uses an existing SSH key/agent by default. An explicit OpenSSH key
can be supplied with `-KeyPath C:\path\id_ed25519` (PuTTY PPK files are not
OpenSSH keys). For a camera using a password, save a Windows-encrypted local
credential once:

```powershell
New-Item -ItemType Directory -Force .runtime | Out-Null
$credential = Get-Credential -UserName root -Message 'MaixCAM SSH password'
$credential | Export-Clixml .runtime/deploy-credential.xml
```

Subsequent runs need only `.\scripts\deploy.ps1`. The encrypted credential is
usable by the same Windows user on the same laptop and is ignored by Git.
Alternatively pass `-Password (Read-Host 'MaixCAM password' -AsSecureString)`
or `-CredentialPath <encrypted-credential.xml>`. Passwords are never logged or
included in `.env`; OpenSSH receives them through a temporary askpass helper.

SSH host keys use normal OpenSSH `known_hosts` verification. On a new laptop,
verify the camera fingerprint using an independent trusted source, then connect
once with `ssh root@<USB-IP>` and accept that verified key. A changed key is an
error; investigate before editing `known_hosts`. `deploy_maix.ps1` also uses
Windows OpenSSH now. Its optional legacy `-HostKey SHA256:...` must match an
existing OpenSSH known_hosts fingerprint.

## Discovery and configuration

Discovery filters active physical Wi-Fi and USB RNDIS/NCM adapters, excluding
virtual/VPN/Bluetooth interfaces and unusable IPv4 addresses. It probes SSH only
within detected USB subnets, using existing neighbors/routes and a bounded scan
of subnets up to /22. USB endpoint verification requires a known SSH identity,
MaixCAM board information and the installed application files. The camera is
then queried for its wireless interface IP and hardware MAC. No adapter MAC is
modified. Wi-Fi SSH is bound to the selected laptop address and checks the same
SSH identity as USB. The Windows route and camera return route must use Wi-Fi.

Two USB interfaces exposing the same camera are deduplicated by its Wi-Fi MAC;
the previously configured USB endpoint is preferred. For multiple cameras or
interfaces, inspect `Get-NetAdapter` and select explicitly:

```powershell
.\scripts\deploy.ps1 -WifiInterfaceIndex 18 -UsbInterfaceIndex 17
.\scripts\deploy.ps1 -UsbInterfaceIndex 17 -UsbPeerIP 10.131.167.1 -DryRun
```

An explicit peer is still subnet checked and SSH identity verified. It is also
required when a USB subnet wider than /22 has no useful neighbor/route entry.
The supplied example is not a built-in camera address.

The ignored root `.env` is the central runtime configuration. Only named,
changed keys are updated; comments and unrelated settings are retained:

| Setting | Consumer / purpose |
|---|---|
| `LAPTOP_WIFI_IP` | Camera deployment's `PC_IP`: headset RTP return destination |
| `MAIXCAM_WIFI_IP`, `MAIX_IP` | Compose/app.py: camera RTSP, Bluetooth HTTP control, TB2 talkback |
| `LAPTOP_USB_IP` | Discovered laptop USB address for diagnostics |
| `MAIXCAM_USB_IP`, `MAIX_USB_IP` | Windows SSH/SCP deployment and PC camera diagnostics |
| `MAIXCAM_WIFI_MAC` | Camera's existing Wi-Fi hardware identity |
| `EARBUDS_MAC` | Exact existing `HEADSET_MAC` from camera `/root/workercam.env` |

`MAIX_IP` and `MAIX_USB_IP` retain the existing application/Compose interface.
`deploy_maix.ps1` renders `/root/workercam.env` using `PC_IP`, unchanged
`HEADSET_MAC` and the existing `AUDIO_PROFILE`. Conflicting saved earbuds
settings cause an error rather than replacing either value. There is no
Bluetooth discovery, re-pairing or MAC generation in network discovery.

Endpoint inventory: `app.py` creates camera URLs for the PC publisher,
Bluetooth client and talkback relay. Compose supplies their camera address;
`pc/camera_diagnostics.py` receives the USB alias. Camera
`background_services.rc.local` passes `PC_IP` to `headset_mic_stream.py`.
Frontend HTTP/API URLs are relative; browser WHEP/WHIP uses the existing local
PC endpoints. Compose and MediaMTX intentionally publish browser services to
localhost. Their loopback addresses must remain loopback. Source defaults,
README examples, standalone diagnostic CLI defaults and test fixtures are
fallbacks/examples, not generated network configuration. Old `.env`
`WEBRTC_HOSTS`/`HEADSET_RTP_PORT` entries are unused by this Compose workflow.

## Deployment, verification and recovery

The entry point checks Docker and recording-idle status before changing files.
It calls the existing `deploy_maix.ps1` installer/reboot and
`deploy_pc.ps1 -Build -Recreate`. TCP/video, independent UDP return,
recording mode, camera image rotation and audio profile are preserved.
It never flashes firmware, changes Wi-Fi settings or resets adapters.

A successful run requires installed camera settings/processes, a healthy
container using the detected IP, the camera diagnostics and talkback APIs,
and actual FFmpeg decoding of both video and headset microphone return inside
Docker. This verifies media delivery; audible quality and physical latency
still need human acceptance. If the headset stream fails verification after a
deployment, one recording-safe PC stop/start refreshes Docker's UDP forwarding,
then verification repeats. Persistent failure triggers rollback.
Repeated execution skips installation/build when
configuration and deployment inputs match the last successful run, and repeats
health checks. `-Force` reinstalls/reboots/rebuilds even when unchanged.

`-DryRun` performs real read-only discovery, SSH and Docker/recording preflight.
It creates no project configuration/backups/state and does not restart services.
Temporary encrypted SSH helper files are removed on exit. Installation and
post-deployment media checks are explicitly reported as not run.

Before mutation, local configuration and recovery metadata are saved in
`.runtime/deploy-backups/<id>/`; the previous image is retained under
`workercam-rollback:<id>`. The existing camera installer backs up application,
boot configuration and pairing token to `/root/workercam-backup-<id>/` before
replacement. On a failed deployment the wrapper restores `.env`, restores
camera backup files over USB and requests a reboot, and, if the PC update had
begun, recreates the previous Docker image. A failed first deployment with no
previous container/image requires inspection rather than an invented rollback.

If automatic recovery cannot reach USB, reconnect it and inspect the printed
`recovery.json` and camera backup directory. Restore files from that directory
to their original `/root`, `/etc/rc.local` and `/maixapp` locations before
rebooting; retain the matching token. Local `.env` is in the same local backup.
The backup also contains a Compose override pointing to the previous image,
when an image rollback was attempted. Saved recordings are retained throughout.
Do not delete backups until the deployment is accepted.

Troubleshooting:

- No USB adapter: check the data cable, enable MaixCAM's USB network gadget,
  install/enable its RNDIS/NCM network driver in Device Manager, and enable DHCP.
- SSH denied: verify the camera root password/key and the saved credential's
  Windows account; log in with Windows `ssh.exe` to diagnose.
- Wi-Fi validation fails: check both devices' Wi-Fi membership, AP client
  isolation and VPN routes. Correct routes instead of disabling unrelated adapters.
- Docker fails: open Docker Desktop, select Linux containers, inspect
  `docker compose logs --tail 80 server`. Remove stale shell `MAIX_IP` or
  `MAIX_USB_IP` variables if they override `.env`.
- Media verification fails: check camera/headset power, Bluetooth connection,
  Windows firewall and Docker UDP forwarding. The script reports failure and
  attempts rollback; it does not claim that a healthy HTTP server proves media.

Exit codes: **0** completed/verified or dry run; **2** local preflight;
**3** discovery/connectivity/read-only validation; **4** deployment;
**5** post-deployment health; **6** incomplete rollback. Remote commands and
network probes have deadlines; `-DeploymentTimeoutSeconds` controls each PC
deployment subprocess (default 900 seconds).

Tests: `python -m unittest tests.test_network_deployment tests.test_start_scripts -v`.
They exercise adapter/route selection, subnet boundaries, exact configuration
preservation, timeout/failure handling, dry-run immutability, repeat/force
behavior, recording protection and rollback with mocked hardware/Docker.
