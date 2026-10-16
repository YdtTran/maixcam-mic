# Docker installation and recovery

The [customer README](../README.md) covers setup and daily use. This guide is for
the installer. Deployment now uses one `compose.yaml` with published ports.
The earlier native launchers and Docker host-network override were removed;
commands in dated session logs are historical evidence, not current instructions.

## Requirements and settings

- Windows PC: Docker Desktop with Linux containers, PowerShell and Docker Compose
  supporting `up --wait`. Host networking is not required.
- Camera installation: PuTTY `plink` and `pscp` supporting `-pwfile`, a verified
  host-key fingerprint, and root SSH access.
- Prepared MaixCAM: MaixPy launcher at `/maixapp/apps`, Python 3, BlueZ, BlueALSA,
  FFmpeg, `arecord`, `aplay`, and a compatible Bluetooth headset.
- Docker reaches `MAIX_IP` over the LAN. The camera sends microphone RTP to the
  PC's LAN address supplied as `deploy_maix.ps1 -PcIp`.

Copy `.env.example` to `.env` on a new installation and edit `MAIX_IP`. Keep
TCP/video selected. Compose sets independent microphone input to UDP 8004.
Old `.env` values for `HEADSET_RTP_PORT`, `RETURN_AUDIO_PORT` and `WEBRTC_HOSTS`
are no longer consumed. `RECORDING_MODE` defaults to `multistream` (video plus mixed/worker/operator audio);
select `legacy` explicitly for video-only recordings.

The scripts create `.talkback_token` only if missing and validate its 32-character
hexadecimal format. Preserve it across updates and deploy the same file to the
camera. It is mounted read-only, excluded from Git and never baked into an image.

## Camera installation

```powershell
.\deploy_maix.ps1 -MaixHost 10.172.16.1 -PcIp 192.168.1.4 -HeadsetMac 'AA:BB:CC:DD:EE:FF' -HostKey 'SHA256:YOUR_VERIFIED_FINGERPRINT' -Reboot
```

Replace the addresses and fingerprint. Enter the password at the private prompt,
or supply `-KeyPath` for a PuTTY private key. Password authentication uses a local
temporary `-pwfile`, removed in `finally`; the password is not printed or passed
as a command-line value.

The script stages files in a private camera directory, checks Python/shell syntax,
and backs up existing files under `/root/workercam-backup-<id>` before installing.
Backups include `/etc/rc.local`, the camera launcher app and metadata, token and
audio settings. Save the printed backup path for rollback.

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
requested, starts the service and verifies Windows HTTP access. Docker packages
the compiled interface, Python, FFmpeg and MediaMTX. No local language runtimes
or media binaries are required.

Routine startup uses `run_all.ps1`, which also opens the browser. Its optional
`-DeployMaix` path installs and reboots the camera first. Finish recordings before
either PC or camera updates. Only the Compose service `server` is managed;
other Docker projects and databases are not modified.

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

Back up `recordings/`, `.env` and `.talkback_token` while recording is stopped.
For PC rollback, restore a known project version and run `deploy_pc.ps1 -Build`
with the preserved settings and token.

For camera rollback, connect over SSH and inspect the saved backup directory.
Restore its `/root` modules/config/token, `rc.local` to `/etc/rc.local`,
`maix_rtsp` to `/maixapp/apps/maix_rtsp`, and launcher metadata to its original
paths. Restore only files present in that backup, then reboot once. If the token
changes, restore the matching PC token. Avoid duplicate audio processes.

## Linux Docker hosts

Use the same `.env`, matching token, `recordings/` directory and `compose.yaml`.
The Windows scripts are the customer entry points; Linux installers can use
`docker compose up --build -d --wait` and `docker compose stop server` after
checking recording status. Use a browser on the Docker host's local desktop.

Docker's [Compose service reference](https://docs.docker.com/reference/compose-file/services/)
documents the health checks, published ports and stop grace period used here.
