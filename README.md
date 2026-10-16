# WorkerCam Admin

Watch a worker's MaixCAM camera, listen through their Bluetooth headset microphone,
speak to them, and save recordings from a browser on your PC.

The PC software runs together in **Docker**. You do not need to install Python,
Node.js, FFmpeg or MediaMTX on the PC. The camera runs its own camera and Bluetooth
programs; the deployment script installs these directly on MaixCAM.

![WorkerCam dashboard showing the built-in demonstration worker](imgs/dashboard-demo.png)

*The screenshots show the application's built-in demo worker and synthetic video.
They illustrate the controls; they are not photographs from a connected camera.*

## What you can do

| Feature | How it works |
| --- | --- |
| Live view | Select **Worker #07** to watch the connected MaixCAM. |
| Rotate | **Original (0°)** is 768×432 (16:9). MaixCAM rotates its full 432×768 capture counter-clockwise before encoding. Manual **90° counter-clockwise** displays 432×768; **90° clockwise** turns the opposite way. Finish recording before changing rotation. |
| Listen | Click **Enable audio** to hear the worker's headset microphone. |
| Talk | Hold **Talk**, speak into your PC microphone, then release. |
| Record | Click **Record**, then **Stop Recording** when finished. |
| Review | Open **Recordings** to play or download an MP4. |
| Try the interface | Select **Worker #12**, the demonstration worker. Its recordings are simulated. |

**SCO duplex is the default headset pipeline**: listening
continues while you hold **Talk**, allowing speech in both directions at once.
SCO uses narrowband audio; microphone return quality still needs improvement.
A2DP is available as a fallback with higher-quality playback and turn-taking:
listening pauses while you talk.

## Before the first setup

You need a Windows PC, a prepared MaixCAM, a compatible Bluetooth headset,
and a network that both devices can reach. Use PC headphones to avoid feedback.

1. Install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
   Open it and wait until the engine is running. Use **Linux containers**.
   Docker's optional host-networking setting is not required by this project.
2. Extract the whole project into a folder you can keep, such as
   `C:\WorkerCam`. Recordings will be stored in this folder.
3. Ask your installer for the camera's network address and confirm the camera
   is powered on. Reserve the PC and camera addresses in the router where possible.
4. Open a PowerShell terminal in the project folder. The commands below run there.

If this PC previously ran WorkerCam outside Docker, have the installer stop that
old service first. The deployment script reports a port conflict if it finds one.

## First-time setup

### 1. Set the camera address

Copy the example settings file **once**, then open it:

```powershell
Copy-Item .env.example .env
notepad .env
```

If `.env` already exists, open it without copying over it. Change `MAIX_IP` to
the address supplied by your installer. For example:

```dotenv
MAIX_IP=192.168.1.7
RTSP_TRANSPORT=tcp
STREAM_MODE=video
RECORDING_MODE=multistream
```

Save the file. Keep `RTSP_TRANSPORT=tcp` and `STREAM_MODE=video`; these select the
camera route supported by the Docker deployment. The worker's microphone returns
separately on UDP port 8004.

The default setup is Docker on the PC, TCP video, independent headset microphone
return, and SCO duplex talkback. Recording defaults to `multistream`, saving
video with mixed audio and separate worker/operator audio tracks. Select `legacy` for video-only recordings.

### 2. Prepare the camera — installer step

**Skip this step if your installer has already configured this camera for this PC
and supplied its matching `.talkback_token` file.**

For a new camera, the installer needs Windows OpenSSH Client (`ssh.exe` and `scp.exe` on PATH), the
camera's SSH address and verified OpenSSH known_hosts entry, the PC's LAN address,
and the headset's Bluetooth address. MaixCAM must already have MaixPy, BlueZ,
BlueALSA, FFmpeg and ALSA tools installed. This script does not flash firmware.

Example — replace the addresses and headset binding with your installation's values:

```powershell
.\deploy_maix.ps1 -MaixHost 10.172.16.1 -PcIp 192.168.1.4 -HeadsetMac 'AA:BB:CC:DD:EE:FF' -Password (Read-Host 'Camera password' -AsSecureString) -AudioProfile sco -Reboot
```

The example requests the password privately. SSH key users can omit `-Password`
and add `-KeyPath` with their OpenSSH private-key file. `MaixHost` may be a USB address; `.env` should contain the
camera address reachable from Docker, usually its Wi-Fi/LAN address.

The script checks prerequisites, backs up camera files and startup settings,
installs the programs and shared pairing token, configures the headset and PC
destination, then reboots when `-Reboot` is supplied. Keep the printed backup
path. Camera installation replaces its WorkerCam boot configuration; use a device
prepared for this application. See [installer details and recovery](docs/docker-run-guide.md).

Both `deploy_maix.ps1` and `run_all.ps1 -DeployMaix` default to SCO when
`-AudioProfile` is omitted. The examples select it explicitly so the intended
profile is clear when updating the PC destination or headset binding.
SCO startup prepares the Bluetooth
controller before opening audio, preventing the silent-link startup race.
To use the A2DP fallback, replace it with `-AudioProfile a2dp` and redeploy with
`-Reboot`. Finish recordings before switching profiles. See the
[SCO duplex guide](docs/sco-duplex.md) for hardware checks and recovery.

### 3. Build and open WorkerCam

With Docker Desktop running and the camera ready:

```powershell
.\run_all.ps1 -Build
```

The first build downloads required components and may take several minutes.
After startup checks pass, your browser opens **http://127.0.0.1:8000**.

Sign in with username **admin** and password **admin**. Select **Worker #07**,
allow browser microphone access when asked, and click **Enable audio** to listen.
Confirm the picture, listening and talkback before starting a work session.
With SCO, confirm that the worker's microphone remains audible while **Talk**
is held, and check both directions again after a camera reboot.

If a pairing token was generated during PC setup, use `deploy_maix.ps1` to copy
that same token to the camera. A different token on each side prevents talkback
and headset status from working.

## Daily use

1. Power on the camera and headset. Open Docker Desktop on the PC.
2. Run `.\run_all.ps1`. Camera installation is only needed when camera software,
   its headset binding or the PC destination changes.
3. Select **Worker #07** and check the live view and headset status.
4. Click **Enable audio** to listen. Hold **Talk** to speak; release it
   when finished. SCO keeps listening active while you speak. Allow the browser
   permission prompt for the PC microphone.
5. Click **Record** to start saving. Click **Stop Recording** and wait for
   **Finalizing...** to finish before closing the system.

To shut down the PC service after recordings finish:

```powershell
.\stop_docker_pc.ps1
```

The script refuses to stop during an active recording or finalization. Recordings
stay on disk. Switch off the camera separately when the work session is over.

## Recordings

![WorkerCam Recordings page with a saved demonstration recording](imgs/recordings-demo.png)

*Demo recording shown. Worker #07 recordings come from the physical camera.*

Real recordings are stored in **`recordings/`** inside the project folder.
You can also play or download them from the **Recordings** page.

New recordings retain the camera's 768×432 stream, full frame and aspect
ratio. The MP4 stores any additional manual live rotation, so playback uses the
same orientation. Video is copied on the PC without re-encoding,
square cropping or stretching. Use a player that supports MP4 display rotation;
the browser player does. Existing recordings are unchanged. The rotation choice
is shared between managers and saved in `recordings/.camera-view.json`.

| Setting in `.env` | Saved MP4 |
| --- | --- |
| `RECORDING_MODE=multistream` — default | Camera video, a mixed audio track, and separate worker/operator audio tracks. |
| `RECORDING_MODE=legacy` — fallback | Camera video only. |

To change recording mode, finish the current recording, edit `.env`, then run
`.\deploy_pc.ps1`. Operator audio exists while **Talk** is held; missing
audio is filled with silence. SCO can record worker audio while **Talk** is held.
If you select the A2DP fallback, listening pauses appear as silence in the worker
track. A compatible player can select separate tracks.

Multistream recording uses temporary disk space: about **691 MB per hour for
audio**, plus video and the finished recording. Physical audio/video alignment,
long-session drift and VLC track selection still need hardware acceptance tests.
See the [recording guide](docs/multistream-recording.md) before relying on it for
evidence or synchronized analysis.

## Deployment scripts

### When the network changes

Connect MaixCAM by USB with both devices on Wi-Fi, then run:

```powershell
.\scripts\deploy.ps1
```

This discovers and verifies both network paths, preserves the camera's fixed
earbuds MAC, updates `.env`, installs/reboots the camera using Windows OpenSSH,
and rebuilds the Docker PC service. Unchanged deployments are verified and
skipped; use `-Force` to reinstall and rebuild, or `-DryRun` to preview.
See [automatic deployment](scripts/README.md) for credentials, requirements,
interface selection, health checks and recovery. The browser remains at
**http://127.0.0.1:8000**.

### Script reference

| File | Purpose |
| --- | --- |
| [`scripts/deploy.ps1`](scripts/deploy.ps1) | Discover USB/Wi-Fi addresses, preserve the headset binding, update configuration and redeploy both devices. |
| [`deploy_maix.ps1`](deploy_maix.ps1) | Install camera programs and startup settings, with backups. Use `-AudioProfile sco -Reboot` for the standard pipeline. |
| [`deploy_pc.ps1`](deploy_pc.ps1) | Start or update the PC Docker service and check access. Add `-Build` after a software update. |
| [`stop_docker_pc.ps1`](stop_docker_pc.ps1) | Safely stop this project's PC container, keeping recordings. |
| [`run_all.ps1`](run_all.ps1) | Start the PC service and open the browser. Add `-DeployMaix` only when camera installation is needed. |

### Update both PC and MaixCAM

Finish any active recording and wait for finalization. In the existing `.env`,
set `RECORDING_MODE=multistream`; keep `RTSP_TRANSPORT=tcp` and `STREAM_MODE=video`.
This also upgrades installations that still explicitly select `legacy`.

With Docker Desktop running, an installer can update both devices in one command:

```powershell
.\run_all.ps1 -DeployMaix -Build -MaixHost 10.172.16.1 -PcIp 192.168.1.4 -HeadsetMac 'AA:BB:CC:DD:EE:FF' -Password (Read-Host 'Camera password' -AsSecureString) -AudioProfile sco
```

This command checks that recording is idle, installs and reboots the camera
with SCO duplex, then rebuilds the PC Docker service with multistream recording.
Replace the addresses and headset binding with your own; verify the SSH host key;
keep the matching `.talkback_token`. After deployment, confirm the live picture,
worker microphone return and Talk audio. With `RECORDING_MODE=multistream`,
a saved MP4 contains video and mixed/worker/operator audio tracks.
Normal daily startup uses `.\run_all.ps1` without those installation arguments.
The camera retains its installed SCO profile across daily PC startup and reboot.

## Help with common problems

| What you see | What to do |
| --- | --- |
| Docker engine is unavailable | Open Docker Desktop, wait for it to finish starting, and retry. |
| PowerShell blocks scripts | For a project you trust, run `Set-ExecutionPolicy -Scope Process Bypass` in this terminal, then retry. |
| Deployment times out or the page does not open | Check `.env`, camera power and Docker Desktop. Run `docker compose logs --tail 80 server` and share the output with your installer. |
| Page opens but no camera picture | Select Worker #07, check camera power/network, then use **Settings → Diagnose camera**. |
| No worker sound | Click **Enable audio**, check PC volume, and keep the earbuds powered on and out of their case. A Bluetooth “connected” status alone does not confirm its microphone is available. See the recovery steps below. |
| Logs say `no stream is available on path 'headsetmic'` | The microphone return stream is unavailable. Follow the recovery steps below; check the camera's PC destination and inbound UDP 8004/8005 if it persists. |
| Talkback is unavailable | Allow browser microphone access, check the headset and matching pairing token, then retry. |
| Stop/update is refused | Stop recording in the interface and wait for finalization. If status cannot be read, inspect logs before forcing a container shutdown. |
| You need a safe demonstration | In a running operator, select Worker #12. Its controls use synthetic video and demo data. |

The Docker health check confirms that the operator API responds. It does not
certify an audible headset connection or physical camera latency. Earlier Docker
host-network trials had Windows access problems; this deployment uses published
ports and requires the checks above on the customer's PC.

### Recover a missing microphone return stream

1. Keep the earbuds on and nearby. Finish recordings and wait for finalization.
2. Run `.\stop_docker_pc.ps1`. If it refuses to stop, resolve the recording or
   finalization status before continuing; do not force shutdown.
3. Run `.\run_all.ps1` to restart the PC service. Select **Worker #07**, click
   **Enable audio**, and check worker speech and talkback again. This restart
   restored a failed Docker UDP forwarding path in the observed outage.
4. If the camera is unreachable over both USB and Wi-Fi, power-cycle it, wait
   for video to return, then check both audio directions. If video works but
   audio remains silent, ask the installer to check the headset's SCO profile
   and capture process before resetting Bluetooth.

These steps recovered the observed outage; the underlying Docker forwarding
and Bluetooth profile failures remain under investigation. The default SCO
setup includes the boot-order repair, but does not guarantee that every headset
disconnect will recover automatically. See the
[outage and recovery evidence](docs/sessions/2026-10-11-headsetmic-outage.md).

## For the installer and maintainer

- The supplied login is a **prototype interface login**, not production access
  control. The operator page is bound to the local PC; use this build on a trusted
  network. Remote browser access requires additional authentication and HTTPS.
- Keep `.env`, `.talkback_token` and `recordings/` when updating the project.
  The token is generated locally when missing and is excluded from Git and images.
- Install updates with `.\deploy_pc.ps1 -Build` after completing recordings.
  Camera updates use `deploy_maix.ps1`; ordinary PC updates do not require them.
- The Docker image includes the compiled browser interface. Its source is in
  `frontend/`; the generated HTML is built automatically and is not tracked.
- [Docker installation, diagnostics and recovery](docs/docker-run-guide.md)
- [Frontend development](frontend/README.md)
- [Architecture, data pipelines and protocol reference](docs/architecture.md)
- [Microphone return details](docs/headset-return-audio.md)
- [SCO duplex setup, validation and recovery](docs/sco-duplex.md)
- [Measurements and their limits](docs/rtsp-measurements.md)

| Folder | Contents |
| --- | --- |
| `maix/` | Camera and Bluetooth programs installed on MaixCAM. |
| `pc/` | Docker operator, media handling, recording and diagnostic tools. |
| `frontend/` | Browser interface source, build tools and browser tests. |
| `tests/` | Automated backend and deployment checks. |
| `docs/` | Installer guides and dated engineering evidence. |
| `imgs/` | Demonstration screenshots used in this guide. |
| `recordings/` | Your saved recordings; created locally and excluded from Git. |
