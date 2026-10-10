# Run the WorkerCam prototype with Docker

This guide runs the PC relay, operator API, recording service, and compiled React UI in one container. The camera and Bluetooth audio programs run on MaixCAM itself. Docker builds the frontend and installs FFmpeg and MediaMTX; you do not need Python, Node, FFmpeg, or `mediamtx.exe` installed on the PC for this route.

## Current Windows access issue and working alternative

As of 2026-10-10, approximately 19:19, the operator runs **natively on Windows**
with TCP video-only settings. The Docker operator container is stopped. Windows
could not reach localhost TCP 8000 or 8889 even though the operator returned
HTTP 200 inside the host-network container. Desktop host networking was enabled;
a Desktop restart and operator recreation did not resolve access. The precise
Docker forwarding cause remains unknown. ThingsBoard and PostgreSQL were
restarted afterward and are running; PostgreSQL reported healthy.

Use the [README native startup instructions](../README.md#run-the-configured-stack)
for the working route. Python, FFmpeg on `PATH`, and `mediamtx.exe` in the project
root are required for that alternative. The current hidden process has its PID
and stdout/stderr in `.runtime/operator-native.*`. Do not start Docker's operator
while the native stack owns the ports.

Daily native startup is `.\start_operator.ps1`; it reads the saved camera,
transport and mode settings, reuses a matching running stack, and verifies HTTP
200 from Windows. `-Build` rebuilds the frontend. Stop recording first, then use
`.\stop_operator.ps1` before testing Docker. The Docker helper now rejects a
running native operator and checks Windows HTTP access before printing success;
if that check fails, switch with `.\start_operator.ps1`.

Open **http://127.0.0.1:8000/operator_test.html** and sign in with **admin / admin**.
The page is served by the PC; MaixCAM does not need an additional program for it
to open. Camera services are required for video and talkback. The native
workaround passed Windows HTTP 200, camera TCP packet checks, H.264 publication,
and talkback API availability. Browser playback and audible talkback were not
physically retested after switching. See the [session log](sessions/2026-10-10-rtsp-latency.md).

The Docker instructions below remain available for retesting after native
services are stopped. Preserve `RTSP_TRANSPORT=tcp` and `STREAM_MODE=video`.
Earbuds → MaixCAM → PC audio remains unimplemented end to end; the historical
microphone deployment and automated checks below do not establish feature completion.

## 1. Choose the network mode

Use `compose.yaml` together with `compose.host.yaml` for this UDP prototype. On Linux, host networking avoids Docker bridge translation of RTSP's negotiated UDP ports. Linux host mode is provided but has not been physically validated in this project.

On Windows, install Docker Desktop **4.34 or newer**, use Linux containers, and enable **Settings → Resources → Network → Enable host networking**, then apply/restart Docker Desktop. Docker documents that Desktop host networking operates at layer 4 and differs from Linux host networking. See [Docker's host networking guide](https://docs.docker.com/engine/network/drivers/host/).

**Earlier verification:** Docker Desktop host mode passed camera media reception, Chromium UDP playback, and silent WebRTC talkback checks using direct microphone RTP. These precede the current Windows localhost failure above. The earlier Desktop bridge configuration failed actual RTP delivery. Host mode alone did not fix incoming RTSP microphone publishing: Desktop rewrites UDP source ports, so the camera microphone was configured to send direct RTP to UDP 8004. Chromium also needs microphone permission to advertise usable IP candidates rather than unresolved mDNS names. Always verify actual media in step 6; a login page or successful RTSP connection alone is insufficient.

Use a current Docker Compose release supporting the override's `!reset` tag; Compose 2.24.4 or later is a conservative minimum for this guide. See [Compose merge behavior](https://docs.docker.com/reference/compose-file/merge/).

```powershell
docker version
docker compose version
```

The commands below use PowerShell unless marked Bash. Run Docker commands from the repository root.

## 2. Identify the camera and PC addresses

On the current hardware:

| Address | Purpose |
| --- | --- |
| `192.168.1.7` | MaixCAM Wi-Fi; video and camera control |
| `192.168.1.4` | PC Wi-Fi; camera microphone publishes here |
| `10.172.16.1` | MaixCAM USB NCM; diagnostic fallback |
| `10.172.16.100` | PC USB NCM adapter |
| `10.172.17.1` | Alternate MaixCAM USB RNDIS address |
| `10.172.17.100` | PC USB RNDIS adapter |

These Wi-Fi addresses can change. Check the PC with `ipconfig` on Windows or `ip -4 addr` on Linux. The camera microphone's target must be the **Docker host's LAN address**, not `127.0.0.1`, a container address, or `host.docker.internal`.

Connect MaixCAM and the PC to the same LAN. Connect USB as well if you want diagnostic access when Wi-Fi fails. Power on the fixed earbuds and disconnect them from other devices.

The fixed earbuds currently have Bluetooth address `6C:16:29:7B:00:D4`. To use another pair deliberately, change `--fixed-mac` in `maix/background_services.rc.local` before deploying it.

## 3. Prepare the project configuration

```powershell
Set-Location C:\Users\trand\orca\maixcam-mic
```

Create or edit a root `.env` file with these entries. Preserve other entries if the file already exists:

```dotenv
MAIX_IP=192.168.1.7
MAIX_USB_IP=10.172.16.1
RTSP_TRANSPORT=tcp
STREAM_MODE=video
HEADSET_RTP_PORT=8004
WEBRTC_HOSTS=127.0.0.1,192.168.1.4
```

Compose reads this file automatically. `MAIX_IP` selects the media camera; `MAIX_USB_IP` is diagnostic-only and does not automatically reroute media.

TCP/video is the accepted configuration. `HEADSET_RTP_PORT` is unused by the
video-only publisher; recordings contain no microphone audio. Native startup
does not read this file automatically and needs explicit transport/mode flags.

`HEADSET_RTP_PORT` must match the camera's `--rtp-port` (an even port from 1024 through 65534, with the next port reserved for RTCP). `WEBRTC_HOSTS` includes the PC's LAN address; update it if the PC address changes. The host override uses IPv4 relay listeners and also gathers interface candidates for WebRTC.

Make the persistent recording directory:

```powershell
New-Item -ItemType Directory -Force recordings | Out-Null
```

On Linux, use `mkdir -p recordings` instead.

The root `.talkback_token` must be an existing **file containing 32 hexadecimal characters**. Keep an existing token: it must match `/root/.talkback_token` on MaixCAM. The upload script copies it for you. Docker mounts this file read-only; it is excluded from the image.

Only if the file is missing, generate it without printing its value:

```powershell
if (-not (Test-Path -LiteralPath .talkback_token)) {
  docker run --rm -v "${PWD}:/work" -w /work python:3.11-slim-bookworm python -c "import pathlib,secrets; p=pathlib.Path('.talkback_token'); p.open('x').write(secrets.token_hex(16))"
}
```

Bash equivalent for Linux:

```bash
if [ ! -f .talkback_token ]; then
  docker run --rm --user "$(id -u):$(id -g)" -v "$(pwd):/work" -w /work python:3.11-slim-bookworm python -c "import pathlib,secrets; p=pathlib.Path('.talkback_token'); p.open('x').write(secrets.token_hex(16))"
fi
chmod 600 .talkback_token
```

Do not regenerate the token on each startup. If you replace it, redeploy it to the camera and restart both sides.

## 4. Set up MaixCAM once, or after changing camera programs

For the currently working video/talkback device, skip camera redeployment.
Opening the operator page requires only the PC server. The microphone setup
below documents earlier experiments and does not complete the pending earbuds
audio feature.

If this device is already running the deployed Docker prototype with `--rtp-port 8004` and its PC target is still correct, skip to step 5. A camera previously configured for RTSP `/headsetmic` must be updated for this host override. These steps require the existing MaixPy camera runtime, BlueZ, BlueALSA, FFmpeg, and ALSA tools on the device; the PC container does not install camera firmware or Bluetooth dependencies.

### Upload from Windows over USB

Install PuTTY so `plink` and `pscp` are available. Check the PC IP target in `maix/background_services.rc.local`:

```sh
nohup python3 /root/headset_mic_stream.py --target 192.168.1.4 --rtp-port 8004 </dev/null >>/root/headset-mic-stream.log 2>&1 &
```

Replace `192.168.1.4` with the Docker host's actual LAN address if necessary.

The repository startup template defaults to RTSP for compatibility with the native stack. Add `--rtp-port 8004` to that microphone command before uploading for this Docker guide. The deployed camera's `/etc/rc.local` already includes it. Omitting this option on both sides retains the original RTSP microphone mode.

The following fingerprint and root password belong to the currently deployed camera. Verify a different camera's SSH fingerprint before using it. A firmware reflash may change the key.

```powershell
$cameraHost = '10.172.16.1'
$cameraKey = 'SHA256:MMjQMht0IcoEBBkw5OVPuwa2wrbSHpiEYHn27tdGcmY'
./upload_maix.ps1 -MaixHost $cameraHost -Password root -HostKey $cameraKey
```

If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process Bypass` in this terminal and retry. The script backs up existing upload targets in `/root/backup-<timestamp>`, copies all camera programs plus the shared TB2 protocol and token, and normalizes the startup script's line endings. Uploading alone does not activate them.

### Back up startup configuration and activate

Back up the launcher configuration separately before replacing it:

```powershell
plink -batch -hostkey $cameraKey -pw root "root@$cameraHost" 'backup=/root/startup-backup-$(date +%Y%m%d-%H%M%S); mkdir -p "$backup" && chmod 700 "$backup" && cp -p /etc/rc.local "$backup/rc.local" && { if test -d /maixapp/apps/maix_rtsp; then cp -rp /maixapp/apps/maix_rtsp "$backup/"; fi; } && { if test -f /maixapp/auto_start.txt; then cp -p /maixapp/auto_start.txt "$backup/"; fi; } && { if test -f /maixapp/apps/app.info; then cp -p /maixapp/apps/app.info "$backup/"; fi; } && echo "$backup"'
```

Ensure this command succeeds and save the printed backup path. Install the touchscreen-free camera app:

```powershell
plink -batch -hostkey $cameraKey -pw root "root@$cameraHost" 'mkdir -p /maixapp/apps/maix_rtsp && cp /root/rtsp_av.py /maixapp/apps/maix_rtsp/main.py && cp /root/rtsp_app.yaml /maixapp/apps/maix_rtsp/app.yaml && python3 /maixapp/apps/gen_app_info.py /maixapp/apps && printf maix_rtsp > /maixapp/auto_start.txt'
```

Install the background audio startup file and reboot:

```powershell
plink -batch -hostkey $cameraKey -pw root "root@$cameraHost" 'cp /root/background_services.rc.local /etc/rc.local && sh -n /etc/rc.local && reboot'
```

Wait for SSH to return. The launcher starts the camera; `/etc/rc.local` starts Bluetooth, the microphone publisher, and talkback. Do not launch duplicate copies manually. On Linux, use your trusted `ssh`/`scp` setup to deploy the same files listed in `upload_maix.ps1` and run the same remote commands.

## 5. Build and start Docker

If a native `python app.py` session is already running, stop it with **Ctrl+C in its terminal** first. A previously hidden launch must be stopped using its verified project PID and command line. Do not kill every Python or FFmpeg process. Native and Docker stacks compete for the same ports.

The tuned relay requests 4 MiB UDP buffers. Linux's default socket buffer ceiling can be lower, causing MediaMTX to exit with `unable to set UDP read buffer size`. On Windows, use the helper, which starts Docker if needed, reapplies the VM limits, validates Compose, and builds/starts the stack:

```powershell
./start_docker.ps1 -Build
```

The helper requires Desktop host networking to be enabled first. Docker Desktop may reset Linux limits on an engine/VM restart, so use this helper for daily startup too. Its buffer command is:

```powershell
wsl -d docker-desktop -u root -- sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304
```

On a Linux Docker host, set the limits before starting; to retain them across reboots:

```bash
printf 'net.core.rmem_max=4194304\nnet.core.wmem_max=4194304\n' | sudo tee /etc/sysctl.d/90-workercam-udp.conf
sudo sysctl -p /etc/sysctl.d/90-workercam-udp.conf
```

Manual Compose startup after the limits are configured:

```powershell
docker compose -f compose.yaml -f compose.host.yaml config --quiet
docker compose -f compose.yaml -f compose.host.yaml up --build -d
docker compose -f compose.yaml -f compose.host.yaml ps
docker compose -f compose.yaml -f compose.host.yaml logs --tail 100 server
```

Use **both `-f` arguments for every operation** in this guide. The image build compiles the React UI, installs FFmpeg, and copies the pinned MediaMTX binary. The container supervises all PC services; camera programs remain outside Docker.

Expected current-mode logs include MediaMTX listeners, `Operator UI: http://127.0.0.1:8000/operator_test.html`, and `/maix01` online with one H.264 track. TCP video-only does not consume the microphone input. In an explicitly selected combined/direct-RTP test, FFmpeg reads an internally generated SDP file describing PCMU/8 kHz mono on UDP 8004. The UI can load before media is ready.

Host mode has no published-port listing in `docker compose ps`; that is expected. The UI and WHEP HTTP listeners are bound to loopback by the override, so open the browser on the Docker host.

## 6. Verify the complete media path

Check reachability from inside the container using explicit addresses. The diagnostic CLI does not inherit the supervisor's command-line `--maix-ip`, so pass your configured values:

```powershell
docker compose -f compose.yaml -f compose.host.yaml exec server python -m pc.camera_diagnostics --maix-ip 192.168.1.7 --maix-usb-ip 10.172.16.1
docker compose -f compose.yaml -f compose.host.yaml exec server python -m pc.check_camera_udp --maix-ip 192.168.1.7
```

The first command tests TCP services. It checks USB only if all tested Wi-Fi services fail. The second must report `"verified": true`, `"transport": "udp"`, and a positive video packet count. It briefly opens an additional camera reader; do not run it continuously while assessing loss.

If the UDP probe fails on Windows Desktop while SSH works from Windows, inspect Docker networking and firewall rules. USB adapter reachability from the Windows host also does not guarantee reachability from Docker Desktop. The earlier bridge failure is recorded in [the validation notes](udp-media.md).

Open **http://127.0.0.1:8000/operator_test.html** and sign in with **admin / admin**:

1. Open **Live Workers** and select the physical **Worker #07**. Worker #12 is a demo.
2. On Docker Desktop, allow **Microphone** for this localhost site in browser site settings and reload. Alternatively, press the talk button once, accept the microphone permission prompt, release it, and let playback reconnect. Without this permission, Chromium can hide its IP behind a `.local` mDNS candidate the Docker VM cannot resolve.
3. Confirm actual camera video and the WebRTC/UDP transport status.
4. Current TCP video-only mode has no monitored microphone audio. Earbuds microphone implementation and validation remain future work.
5. Hold the talk button, speak, and release it. Confirm sound at the camera/earbuds separately from API availability.
6. Start a short recording, stop it, and open it under **Recordings**. Stopping finalizes the MP4.
7. Under **Settings**, use **Diagnose camera** if the feed is unavailable.

Use localhost for browser microphone access. Viewing the UI through a remote HTTP LAN address requires further binding, ICE address, and secure-context configuration; this guide covers a browser on the Docker host.

## 7. Daily startup, updates, and shutdown

After initial setup, power on MaixCAM and the earbuds, then run:

On Windows, start with `./start_docker.ps1` so the Docker VM buffer limits are reapplied. On Linux with persistent sysctl settings, use the following directly:

```powershell
docker compose -f compose.yaml -f compose.host.yaml up -d
docker compose -f compose.yaml -f compose.host.yaml logs -f server
```

Ctrl+C exits log following without stopping the container. It has `restart: unless-stopped`; start Docker after a PC reboot. The supervisor retries a lost publisher, and the camera retries headset connection. An interrupted recording requires a new recording; seamless recovery within one MP4 is not implemented.

After changing frontend code, PC code, or `mediamtx.yml`, rebuild:

```powershell
docker compose -f compose.yaml -f compose.host.yaml up --build -d
```

After changing `.env`, use `up -d` to apply the configuration; `restart` alone does not apply changed Compose settings. Camera code changes require step 4 separately. See [Docker's restart documentation](https://docs.docker.com/reference/cli/docker/compose/restart/).

Stop recording in the UI before shutting down:

```powershell
docker compose -f compose.yaml -f compose.host.yaml down
```

MP4s and metadata remain in the host `recordings/` directory. The token also remains on the host. Containers can be recreated without losing these files.

## 8. Ports and troubleshooting

| Location | Port | Purpose |
| --- | --- | --- |
| PC loopback | TCP 8000 | UI, operator API, saved recordings |
| PC loopback | TCP 8889 | WebRTC WHEP/WHIP signaling |
| PC | UDP 8189 | Browser WebRTC media |
| PC | TCP 8554 | MediaMTX RTSP control; camera mic connects here |
| PC | UDP 8002 / 8003 | MediaMTX RTP / RTCP |
| PC | UDP 8004 / 8005 | Direct headset G.711 RTP / RTCP |
| Camera | TCP 8554 | Camera RTSP control |
| Camera | TCP 8765 | Authenticated Bluetooth control |
| Camera | UDP 9002 | Authenticated talkback PCM |
| Camera | TCP 22 | SSH diagnosis/deployment |

Camera RTSP UDP media also uses ports negotiated during RTSP setup, including PC FFmpeg receive ports in its default 5000–65000 range. Allow the relevant container/Docker processes and camera traffic on the trusted LAN; allowing TCP 8554 alone does not allow media. Host networking avoids needing to publish every negotiated port. Keep LAN firewall rules scoped to the intended host/camera.

| Symptom | Checks |
| --- | --- |
| Container will not start | Check Docker is running, token is a file, recording directory exists, and native services have released the ports. Read Compose logs. |
| Windows cannot open the page, but container HTTP works | This failure persisted after Desktop restart and operator recreation on 2026-10-10. Use the README native TCP/video startup route after stopping the operator container; preserve unrelated containers. The Docker forwarding cause remains unresolved. |
| Page returns 404 | Use `/operator_test.html`, not `/operaator_test.html`. MaixCAM does not serve this PC page. |
| MediaMTX cannot set UDP buffer size | Run `./start_docker.ps1` on Windows or apply the Linux sysctl settings above. |
| UI loads, camera stays offline | Run the container UDP probe; check MaixCAM launcher, camera Wi-Fi IP, host mode, and firewall. |
| Headset input absent | In this guide `/headsetmic` is unused. Check camera `--target`, `--rtp-port 8004`, matching `HEADSET_RTP_PORT`, and UDP 8004/8005. Read `/root/headset-mic-stream.log`. |
| WebRTC ICE connection times out | Allow browser microphone permission, reload, check `WEBRTC_HOSTS`, and confirm Desktop host networking is enabled. |
| Video corruption or freezes | Look for `RTP: missed` / `RTP packets lost`. The current configuration uses 4 MiB receive buffers and 1200-byte relay payloads; Wi-Fi loss can still damage upstream H.264 frames. |
| Headset audio missing | Click Enable audio, check fixed-earbud status, disconnect earbuds from other devices, and read `/root/bluetooth-audio.log`. |
| Talkback unavailable | Check matching tokens without printing them, microphone permission, UDP 9002, `/root/talkback-receiver.log`, and PC/camera clocks within two seconds. |
| Wi-Fi unreachable | Use USB SSH; check `ip -4 addr`, `netstat -lnt`, and camera logs. USB diagnostics do not switch the media path. |
| Recording does not play | Stop recording first. Check host `recordings/`, free disk space, and recording API status. |

Read camera logs over USB, using the variables from step 4:

```powershell
plink -batch -hostkey $cameraKey -pw root "root@$cameraHost" 'ip -4 addr; netstat -lnt; tail -n 40 /root/bluetooth-audio.log; tail -n 40 /root/headset-mic-stream.log; tail -n 40 /root/talkback-receiver.log; date -u'
```

The camera sends 640 × 480 hardware H.264 using the RTSP encoder defaults (30 fps / 3 Mbps). Current video-only monitoring and saved MP4s contain H.264 without microphone audio. Combined-mode code supports Opus monitoring and AAC recording, but earbuds → MaixCAM → PC feature completion remains pending. The login is a prototype UI gate, not API authorization. Physical latency and audible talkback quality remain separate hardware checks. See [protocols and measured validation](udp-media.md) for details.
