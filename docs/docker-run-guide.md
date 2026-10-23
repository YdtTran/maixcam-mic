# Docker installation and recovery

The [customer README](../README.md) covers setup and daily use. This guide is for
the installer. Deployment now uses one `compose.yaml` with published ports.
The earlier native launchers and Docker host-network override were removed;
commands in dated session logs are historical evidence, not current instructions.

## Requirements and settings

- Windows PC: Docker Desktop with Linux containers, PowerShell and Docker Compose
  supporting `up --wait`. Host networking is not required.
- Camera installation: Windows OpenSSH `ssh.exe` and `scp.exe`, and standard
  root/root SSH access (supplied automatically).
- Prepared MaixCAM: MaixPy launcher at `/maixapp/apps`, Python 3, BlueZ, BlueALSA,
  FFmpeg, `arecord`, `aplay`, and a compatible Bluetooth headset.
- Docker reaches `MAIX_IP` over the LAN. The camera sends microphone RTP to the
  PC's LAN address supplied as `deploy_maix.ps1 -PcIp`.

Copy `.env.example` to `.env` on a new installation and edit `MAIX_IP`. Keep
TCP/video selected. Compose sets independent microphone input to UDP 8004.
Old `.env` values for `HEADSET_RTP_PORT`, `RETURN_AUDIO_PORT` and `WEBRTC_HOSTS`
are no longer consumed. `RECORDING_MODE` defaults to `multistream` (video plus mixed/worker/operator audio);
select `legacy` explicitly for video-only recordings.

The release uses token-free TB3 for talkback and camera HTTP control. No token
file, mount or copy step is needed. Update PC and camera together using
[combined deployment](../scripts/README.md). Old versions
are incompatible; optional legacy tokens remain private rollback material only.

## Camera installation

```powershell
powershell -ExecutionPolicy Bypass -Command "& .\deploy_maix.ps1 -WifiSsid 'YOUR_PC_WIFI_SSID' -WifiPassword (Read-Host 'Wi-Fi password' -AsSecureString) -MaixHost 10.172.16.1 -PcIp 192.168.1.4 -HeadsetMac 'AA:BB:CC:DD:EE:FF' -Reboot"
```

Replace the addresses and SSID. The private prompt is for the Wi-Fi password;
camera SSH automatically uses root/root. No camera password entry or saved
credential setup is needed. Install OpenSSH Client as described in the
[Windows setup guide](../README.md#install-openssh-client).
New host keys are accepted automatically; changed saved keys still stop setup.
Explicit OpenSSH `-KeyPath`, SecureString `-Password` and `-HostKey` overrides
remain supported. The temporary askpass helper is removed on exit; camera
passwords are not printed or passed as command-line values.

The script stages files, checks Python/shell syntax, stops old WorkerCam camera
processes and overwrites the installed application without making backups.
For complete fresh installation use [combined deployment](../scripts/README.md).

It installs the camera app at `/maixapp/apps/maix_rtsp`, sets it as the launcher's
startup app, and replaces `/etc/rc.local` with the project background template.
Use a device prepared for WorkerCam. `/root/workercam.env` holds `PC_IP`,
`HEADSET_MAC` and `AUDIO_PROFILE`; the shared template reads them at boot.
Uploads do not start duplicate capture processes. `-Reboot` activates the files;
without it, activation waits for the operator to reboot the camera.

Camera deployment defaults to `-AudioProfile sco`, the CVSD/120-byte-MTU duplex
setup. Explicit `-AudioProfile a2dp` selects the half-duplex fallback. Follow
the [headset acceptance procedure](sco-duplex.md) for the target unit.
The reboot check verifies the RTSP port, and PC startup checks received video
packets. Neither check certifies audible headset performance.

## PC deployment

```powershell
.\deploy_pc.ps1 -Build
```

This validates Compose and transport settings, rejects a conflicting native
listener, checks recording status in the existing project container, builds when
requested, starts the service and verifies Windows HTTP access. It also verifies
Windows host UDP return-audio listeners (ports 8004 and 8005), recreating the
single `server` container (`docker compose up -d --force-recreate --no-deps server`)
if Docker Desktop drops a port binding while recording is idle. Docker packages
the compiled interface, Python, FFmpeg and MediaMTX. No local language runtimes
or media binaries are required.

`run_all.ps1 -WifiSsid <SSID> -HeadsetMac <MAC>` now runs the combined hard-fresh
workflow and opens the browser. It stops all running containers on the current
Docker engine. The standalone component tools manage only this project's service.

## Network and firewall

| Connection | Required access |
| --- | --- |
| Browser → operator | PC loopback TCP 8000. |
| Browser → WebRTC signaling | PC loopback TCP 8889. |
| Browser ↔ WebRTC media | PC loopback UDP 8189. |
| Local diagnostics → relay | PC loopback TCP 8554. |
| PC → camera video | Camera TCP 8554, H.264 over RTSP/TCP. |
| Camera → PC microphone | PC UDP 8004/8005, published through Docker. |
| PC → camera talkback | Camera UDP 9002. |
| PC → camera status/clock | Camera TCP 8765. |
| Installer → camera SSH | Camera TCP 22. |

MediaMTX advertises `127.0.0.1` for the local browser and does not advertise
container-only interfaces. Camera microphone input is the host mapping that
accepts LAN traffic. On Windows Private networks, an administrator can allow the
known camera address (replace the example):

```powershell
New-NetFirewallRule -DisplayName 'WorkerCam microphone' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 8004,8005 -RemoteAddress 192.168.1.7 -Profile Private
```

No router forwarding is needed. Do not expose the prototype API to the internet.
Remote browsers require separate authentication and HTTPS.

Earlier bridge failures involved RTSP's negotiated UDP path. This route uses TCP
for RTSP and fixed UDP microphone ports. It still needs physical verification on
the customer's PC; configuration changes do not establish a latency improvement.

## Diagnostics

```powershell
docker compose config --quiet
docker compose ps
docker compose logs --tail 80 server
docker compose exec server python -m pc.camera_diagnostics --maix-ip 192.168.1.7
docker compose exec server python -m pc.check_camera_udp --maix-ip 192.168.1.7 --transport tcp
docker compose exec server cat .runtime/headset-return.ffmpeg.log
```

`healthy` means the recording-status API responds. Confirm live video, enable
microphone return, speak in each direction and save/play a short recording.
An unavailable camera fails the startup TCP probe and the container retries;
check camera power and `MAIX_IP`. If Docker is healthy but Windows HTTP fails,
inspect Docker Desktop forwarding and port ownership.

If camera video freezes or drops, do not kill the process and start manual
`python3 /maixapp/apps/maix_rtsp/main.py` instances over SSH; `launcher_daemon`
manages camera video and unsynchronized manual restarts race ISP/MMF hardware
teardown, triggering camera read timeouts. Recover with a recording-safe clean
reboot instead (`deploy_maix.ps1 -Reboot`, `scripts/deploy.ps1`, or `/sbin/reboot`).

Container logs rotate at 10 MB with three files. Recordings persist through their
host bind mount. Decoder logs inside `.runtime` in the container are temporary;
collect them before replacing a container if needed for troubleshooting.

## Stop, backup and rollback

```powershell
.\stop_docker_pc.ps1
```

The helper checks status inside the container, refuses recording/finalization,
then runs `docker compose stop server`. If status cannot be read while running,
it refuses to guess. Inspect logs and recordings before any manual forced stop.
Docker's two-minute grace period is a fallback, not a guarantee that a long
multistream mux finishes under forced shutdown. Finish recording in the UI first.

Back up `recordings/`, `.env` and private recovery snapshots while recording is
stopped. To recover a prior token-based release, use the captured old image and
`rollback.compose.json` with its private legacy token mount, rather than the
new token-free Compose file. Missing/malformed/mismatched legacy material means
old-release talkback recovery is unavailable; it does not block new TB3 setup.

For camera rollback, restore the saved `/root` modules/configuration,
`rc.local` to `/etc/rc.local`, launcher app and metadata to their original paths,
and optional matching old token only for an old release. Keep PC stopped until
camera restoration finishes, reboot once, then restore the matching PC snapshot.
Reverify media/control before claiming recovery. Avoid duplicate audio processes.

## Linux Docker hosts

Use the same `.env`, `recordings/` directory and `compose.yaml`.
The Windows scripts are the customer entry points; Linux installers can use
`docker compose up --build -d --wait` and `docker compose stop server` after
checking recording status. Use a browser on the Docker host's local desktop.

Docker's [Compose service reference](https://docs.docker.com/reference/compose-file/services/)
documents the health checks, published ports and stop grace period used here.
