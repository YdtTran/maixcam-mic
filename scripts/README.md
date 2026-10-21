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
MaixCAM with this project's existing application and `/root/workercam.env`.
No shared application token is needed. Finish recordings/finalization first.
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
| `MAIXCAM_WIFI_IP`, `MAIX_IP` | Compose/app.py: camera RTSP, Bluetooth HTTP control, TB3 talkback |
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
container using the detected IP, Windows host UDP return listeners (ports 8004
and 8005, automatically recreated if dropped by Docker while idle), the camera
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
boot configuration and any optional legacy recovery token to `/root/workercam-backup-<id>/` before
replacement. On a failed deployment the wrapper restores `.env`, restores
camera backup files over USB and requests a reboot, and, if the PC update had
begun, recreates the previous Docker image. A failed first deployment with no
previous container/image requires inspection rather than an invented rollback.

If automatic recovery cannot reach USB, reconnect it and inspect the printed
`recovery.json` and camera backup directory. Restore files from that directory
to their original `/root`, `/etc/rc.local` and `/maixapp` locations before
rebooting. For an old token-based release, restore its matching private token
snapshot and the captured `rollback.compose.json`, including its old mount.
Local `.env` is in the same local backup. Never combine an old image with the
new Compose file. Saved recordings are retained throughout.
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
  Windows firewall and Docker UDP forwarding. If camera video was interrupted,
  do not attempt manual SSH restarts of `maix_rtsp/main.py` while `launcher_daemon`
  runs; use a clean camera reboot (`deploy_maix.ps1 -Reboot` or `/sbin/reboot`) to
  avoid ISP hardware read timeouts. The script reports failure and
  attempts rollback; it does not claim that a healthy HTTP server proves media.

Exit codes: **0** completed/verified or dry run; **2** local preflight;
**3** discovery/connectivity/read-only validation; **4** deployment;
**5** post-deployment health; **6** incomplete rollback. Remote commands and
network probes have deadlines; `-DeploymentTimeoutSeconds` controls each PC
deployment subprocess (default 900 seconds).

PC deployment displays stages `[PC 1/5]` through `[PC 5/5]` and streams Docker
build/start output immediately. The first build downloads base images and npm/
Debian dependencies and can take several minutes. If progress stops, report the
last stage and Docker output. Inspect `docker compose ps` and, if a container was
created, `docker compose logs --tail 80 server` from a second terminal.

Tests: `python -m unittest tests.test_network_deployment tests.test_start_scripts -v`.
They exercise adapter/route selection, subnet boundaries, exact configuration
preservation, timeout/failure handling, dry-run immutability, repeat/force
behavior, recording protection and rollback with mocked hardware/Docker.

## One-time TB3 migration

Use the combined workflow to update both sides. Direct PC-only or camera-only
updates can leave incompatible talkback versions; finish the paired update.
The wrapper stops the old PC before changing the camera, captures the actual old
container configuration/image/mounts, and verifies installed/running camera TB3,
PC TB3 without a token mount, process counts and actual video/headset-return decode.
Admin login, verified SSH and fixed earbuds binding remain as before.

Old tokens are optional private rollback material, never a new-release setup
requirement. Missing, malformed or mismatched recovery material permits the new
installation but produces an explicit unavailable old-release talkback recovery
warning. Failed activation attempts compatible-pair recovery and reports incomplete
recovery honestly. A stopped old runtime returns to its stopped state.
After successful pair/media verification, active legacy token files are removed
at their explicit PC/camera paths; cleanup failure only warns. Recovery snapshots,
recordings, SSH keys and Bluetooth bonds remain. Retain backups until human
picture, listening, Talk and recording acceptance; automatic checks do not prove
audible speech. Maintenance exclusion below protects recording throughout mutation.

## Recording-safe maintenance and crash recovery

All five entry points (`deploy_pc.ps1`, `stop_docker_pc.ps1`, `run_all.ps1`,
`deploy_maix.ps1`, `scripts/deploy.ps1`) share a project host lock and maintenance
owner. Acquisition refuses capture and finalization; new recording starts return
HTTP 409 throughout build, replacement, reboot, health checks, audio recovery and
rollback. Listings and playback remain available. The UI displays the owner.
The marker is `recordings/.maintenance.json`, separate from recording metadata;
container replacement preserves it. `-CheckOnly` and `-DryRun` never acquire it.
`.runtime/mutation.lock` is a host file handle lock; its remaining filename does
not mean maintenance is active. Never delete or replace it while scripts run.

Only the outer operation releases maintenance after successful verification.
Nested calls inherit `WORKERCAM_MAINTENANCE_OWNER` and verify the still-held host
lock and matching marker. An unrelated deployment refuses a stale marker. No
timer expires it. A failed operation leaves the marker and prints the owner.

After a failure or crash:

1. Check that the owning terminal/process and all child deployment processes have
   finished. Inspect Docker logs, camera state and any
   `.runtime/deploy-backups/<deployment-id>/recovery.json` before deciding whether
   to continue the new installation or use the saved runtime. This file records
   `maintenanceOwner`; preserve recordings, camera backups and optional private
   legacy token material. Do not start another operator PC during recovery.
2. Read the owner from `recordings/.maintenance.json`. Finish camera recovery
   and verify it is stable before allowing recording again. An unreachable
   running operator blocks recovery; restore its responsiveness first. A native
   media listener must be stopped through its normal recording-safe shutdown.
3. From the project folder run the following with that exact recorded owner:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\recover_maintenance.ps1 -Owner <32-character-owner>
   ```

   This takes the same host lock, verifies idle/finalization state and releases
   only that owner. It never starts a stopped container. A foreign owner is
   refused. A malformed marker also blocks starts: preserve it and inspect the
   operation logs to recover its owner before repairing the marker; do not
   blindly delete it or guess an owner.

First upgrade: an older image cannot honor this marker. After verifying idle,
the script stops it, then builds/starts a maintenance-aware replacement before
camera mutation. The initial legacy idle-check-to-stop interval cannot provide
atomic exclusion; avoid new recording starts during this one-time bootstrap.
A stopped/nonexistent operator gets a host marker after Docker/native-listener
checks. An unresponsive running operator is never treated as stopped.

Rollback restores the inspected previous PC configuration **stopped**, while
camera recovery may still be in progress. It reports exit 6 and retains the
owner for explicit recovery rather than automatically starting an image that
may ignore maintenance. After camera recovery, release maintenance as above,
then start the inspected saved Compose configuration (or rerun the paired
deployment to finish the new release). Keep the old PC stopped when migrating
to another PC: this guard only coordinates this checkout on this Windows host.

Reusable contract for the future desktop wizard (its proposal is unchanged):

- `GET /api/recordings/status` includes `maintenance: null` or `{ "owner": "..." }`.
  An invalid/unreadable marker instead reports a non-null maintenance diagnostic.
- `POST /api/maintenance/begin` with JSON `{ "owner": "<32 lowercase hex>" }`
  acquires under the recorder lock; matching-owner retry is idempotent.
- `POST /api/maintenance/end` with the same body releases only that owner after
  verifying idle state. Invalid input is 400; capture/finalization/foreign owner
  conflicts are 409; storage failures are 503. Existing Origin checking applies.
- Windows callers use `Enter-ProjectMaintenance` / `Exit-ProjectMaintenance` from
  `scripts/NetworkDeployment.psm1`, holding the returned context through all
  mutation and verification. Release with success only when recovery is verified;
  otherwise retain the marker. Do not implement a second independent lock or
  automatically clear a marker on wizard startup.
