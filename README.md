# WorkerCam Admin — Windows setup and redeployment

WorkerCam lets you watch the MaixCAM camera, hear the worker through their
Bluetooth earbuds, speak back to them, and save recordings from your Windows PC.

Follow this guide to **install or completely reinstall WorkerCam**,
including after changing Wi-Fi or moving to another laptop. Automatic setup
finds the network addresses for you.

![WorkerCam dashboard](imgs/dashboard-demo.png)

*Screenshots show the built-in demonstration worker and simulated video.*

## 1. Get everything ready

You need:

- A Windows PC with internet access to download software components.
- The complete WorkerCam project folder, extracted from its ZIP file if supplied.
  Keep it somewhere permanent, for example `C:\WorkerCam`.
- A MaixCAM with MaixPy firmware, USB networking, SSH, BlueZ/BlueALSA, FFmpeg and ALSA tools; WorkerCam need not already be installed.
- The Bluetooth MAC address of the earbuds, supplied as `-HeadsetMac`. For this unit: `6C:16:29:7B:00:D4` (EDIFIER X2 Plus).
- A USB **data cable** connecting the camera to the PC. A charging-only cable
  will not work.
- The PC connected to the required Wi-Fi network and its Wi-Fi password ready.
  Power on the camera and take the powered-on earbuds out of their case. Setup
  joins the camera to that same network over USB.
- Camera SSH enabled with the standard `root` username and `root` password.
  Setup supplies these automatically.

**Changing Wi-Fi?** Connect the PC to the required Wi-Fi first. Supply that
exact network name as `-WifiSsid` and enter its password at setup. Over USB,
setup connects MaixCAM to the same Wi-Fi and saves it across reboot. Using the
same SSID is required; setup refuses a different network name.

**Before updating:** stop any recording in WorkerCam and wait until
**Finalizing...** disappears. Keep USB connected throughout setup.

**Every setup is a hard-fresh application reinstall.** It stops **all running
Docker containers on this PC**, removes this project's container, resets the PC
configuration and camera view, stops camera application processes, overwrites the
camera programs/settings, reboots it and rebuilds the PC image without cache.
No application backup or automatic rollback is made. Finish recordings first;
an interrupted recording may be incomplete. Existing video files are retained.

**Moving to another laptop?** No application token or saved camera password
needs copying. Setup uses the standard camera login automatically. Stop WorkerCam on
the old PC before redeploying. The camera sends its microphone sound to one PC,
so redeployment switches that destination to the new laptop.

A camera needs the firmware components listed above. This installs WorkerCam;
it does not flash firmware or install Docker/Windows drivers. See the
[firmware prerequisites](docs/docker-run-guide.md).

## 2. Prepare Windows and open PowerShell

### Before the first setup — install Docker Desktop

Complete this once on each Windows PC. If Docker already works, skip to
**Install OpenSSH Client** below. WorkerCam uses Linux containers through WSL 2.

#### 1. Check Windows and virtualization

Check your Windows version with `winver` and compare it with the current
[Docker Desktop requirements](https://docs.docker.com/desktop/setup/install/windows-install/#system-requirements).
Open **Task Manager → Performance → CPU** and check **Virtualization**.
If disabled, enable hardware virtualization in BIOS/UEFI; ask your installer
or IT team if needed.

#### 2. Install or update WSL 2

WSL lets Docker run Linux containers on Windows. Open Start, search for
**PowerShell**, right-click it and select **Run as administrator**.
Check whether WSL is installed:

```powershell
wsl --version
```

If WSL is missing, install it without adding a separate Linux distribution:

```powershell
wsl --install --no-distribution
```

Restart Windows if prompted. Reopen PowerShell as administrator, then run:

```powershell
wsl --update
wsl --set-default-version 2
wsl --version
```

If WSL was already installed, run these update and verification commands too.
If installation fails, follow Microsoft's
[WSL installation guide](https://learn.microsoft.com/en-us/windows/wsl/install).
Finish any requested restart before continuing.

#### 3. Install and start Docker Desktop

1. Download the installer matching your PC's processor from
   [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
2. Run it. Select **Use WSL 2 instead of Hyper-V** if offered.
3. Finish installation and restart if requested.
4. Open **Docker Desktop** from Start, review and accept its terms to continue,
   and wait for the engine to start.
5. In **Settings → General**, enable **Use the WSL 2 based engine** if available.
   Apply changes if needed. Use **Linux containers**.

#### 4. Verify Docker before deploying

Open a new, normal PowerShell window and run:

```powershell
docker --version
docker compose version
docker info --format '{{.OSType}}'
docker run --rm hello-world
```

The first two commands should print versions, the third should print `linux`,
and the last should print **Hello from Docker!**. The test downloads a small
image, so internet access is required. Keep Docker Desktop running.

If a check fails:

- **Command not recognized:** reopen PowerShell after installation.
- **Cannot connect to Docker:** open Docker Desktop and wait for startup.
- **Output is `windows`:** choose **Switch to Linux containers** from Docker's
  system tray menu, if available, then retry.
- **WSL update or virtualization error:** repeat the WSL checks and confirm
  virtualization is enabled, then restart Windows.
- **Image download fails:** check internet, proxy or VPN settings and retry.

### Install OpenSSH Client

In Windows Settings, search for **Optional features**. Find **OpenSSH Client**
in the installed features. If missing, use **Add a feature** or **View features**
to install it. You need the Client, not the Server.

WorkerCam deployment requires **PowerShell → Run as administrator** so it can
allow the camera's microphone packets through Windows Firewall. You do not need Python,
Node.js or separate video tools.

### Open PowerShell in the project folder

1. Open the WorkerCam project folder in File Explorer. You should see
   `run_all.ps1`, `deploy_pc.ps1`, and the `scripts` folder.
2. Open Start, search for **PowerShell**, right-click it and select
   **Run as administrator**. Run `Set-Location 'C:\WorkerCam'`, replacing
   `C:\WorkerCam` with the full path of your project folder.
3. Paste these commands and press **Enter**:

```powershell
docker --version
ssh -V
```

Both should display a version. If either command is not recognized, finish its
installation, close PowerShell and open it again from the project folder.

**Every script command below includes `-ExecutionPolicy Bypass`.** Copy the
whole line. This allows that PowerShell run to execute the project scripts
without changing your permanent Windows script policy.

## 3. Camera access is automatic

Setup uses the camera's standard SSH login: **username `root`, password `root`**.
You do not need to enter, save or recheck the camera password, including on a new
laptop. Existing saved camera credential files are not loaded automatically.

Keep the camera connected by USB. Each install uses a temporary SSH host-key
file, so stale keys from earlier installations do not block setup. USB hardware
identity and the matching Wi-Fi identity are still checked during that run.

The Wi-Fi password requested by the setup command below is for the PC's Wi-Fi
network, separate from the automatic camera login.

## 4. Redeploy the camera and PC

With Docker Desktop running, USB connected and the PC on Wi-Fi, replace
`YOUR_PC_WIFI_SSID` with the exact network name shown in Windows. Run this
command in administrator PowerShell; enter the Wi-Fi password when prompted
(this is separate from the camera SSH password):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& .\scripts\deploy.ps1 -WifiSsid 'YOUR_PC_WIFI_SSID' -HeadsetMac '6C:16:29:7B:00:D4' -WifiPassword (Read-Host 'Wi-Fi password' -AsSecureString)"
```

Replace the example headset MAC with your own earbuds' Bluetooth address.
On a new camera, put the earbuds into pairing mode. The script finds USB/Wi-Fi
addresses, joins the requested Wi-Fi if needed, and installs both sides using
SCO duplex, TCP video and multistream recordings. Previous `.env` and camera
WorkerCam settings are ignored. No local Node or Python installation is needed.

**Wait for it to finish.** The camera may restart and its picture will disappear
briefly. The PC build may take several minutes, especially the first time.
Progress includes `[PC 1/5]` through `[PC 5/5]`, followed by connection checks.
Keep Docker Desktop running and leave the PowerShell window open.

Look for this final message:

```text
Deployment completed successfully.
```

Every run reinstalls both sides, even if the source is unchanged. `-Force` is
retained only for older commands and is no longer necessary. If setup fails,
fix the printed error and rerun the same command; it does not restore old code.

To check preparation without installing or restarting anything:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy.ps1 -WifiSsid 'YOUR_PC_WIFI_SSID' -HeadsetMac '6C:16:29:7B:00:D4' -DryRun
```

A successful dry run only confirms preparation checks. Complete normal deployment
and the picture/sound checks below before using the system.

## 5. Open WorkerCam and check picture and sound

1. Open Edge or Chrome on this PC and enter **http://127.0.0.1:8000** in the address bar.
2. Sign in with username **admin** and password **admin**.
3. Select **Worker #07**, the connected camera. **Worker #12** is a demonstration
   with simulated video; use #07 to check the real equipment.
4. Confirm the picture moves. Use the rotation control if needed; finish
   recording before changing rotation.
5. Click **Enable audio**. Ask the worker to speak and confirm you can hear them.
6. Allow browser microphone access. Hold **Talk**, speak, then release it. Ask
   the worker to confirm they heard you. PC headphones help prevent feedback.
7. Click **Record**, make a short test, then click **Stop Recording**. Wait for
   **Finalizing...** to finish. Open **Recordings**, play the test and check it.

The standard setup allows both people to speak and listen at the same time.
Talk uses the PC's communications microphone when available (for example, its
Bluetooth headset microphone), falling back to the default input when that
device is unavailable. Check Windows' communications microphone selection if
live speech is silent even though a test tone works.

To adjust sound in the camera earbuds, open **Live Workers**, select the camera worker, and in **Actions**
move **Earbud playback volume** (0–100%), then click **Apply earbud volume**.
The displayed result reflects the earbuds' actual volume steps. This controls
Talk playback in the camera earbuds; it does not change microphone input or
laptop speaker volume. At 100%, the hardware mixer is already at its maximum.

Earbud microphone sound is telephone quality. If your installer selected the
alternative audio mode, listening pauses while you hold **Talk**.

The script checks that video and microphone data arrive and that the talkback
service responds. These manual checks confirm that people can see and hear each
other. Keep USB connected until setup and these checks finish; normal use sends
picture and sound over Wi-Fi.

## Daily start and safe shutdown

For normal use on the same network, turn on the camera and earbuds, open Docker
Desktop, then run this from the project folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_all.ps1 -WifiSsid 'YOUR_PC_WIFI_SSID' -HeadsetMac '6C:16:29:7B:00:D4'
```

This runs the same complete fresh reinstall and opens the browser after success.
Keep USB connected. Supply `-WifiPassword` as in section 4 when changing Wi-Fi.

To shut down, stop recording and wait for finalization, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop_docker_pc.ps1
```

The script refuses to stop while a recording is being saved. Saved videos stay
in the project folder. Switch off the camera and earbuds separately.

## Find your recordings

![WorkerCam Recordings page](imgs/recordings-demo.png)

*The screenshot shows a demonstration recording.*

Open **Recordings** to play or download videos. The files are also stored in the
**`recordings`** folder inside your WorkerCam project folder. Back up this folder
if you need to keep the videos when replacing the PC.

The standard recording includes camera video and audio, with separate worker
and operator audio tracks available in a compatible player. Your voice is saved
while you hold **Talk**. An older installation may be configured for video-only
recording. Check a test before relying on it. Longer sessions need free disk
space for temporary files and the finished video; temporary audio alone uses
about 691 MB per hour. See [recording details](docs/multistream-recording.md).

## Help when something goes wrong

| Problem | What to do |
| --- | --- |
| Docker is unavailable | Open Docker Desktop and wait for its engine to start. Retry the command. |
| Scripts are blocked | Copy the complete command, including `-ExecutionPolicy Bypass`. If your organization's policy still blocks it, ask its IT team. |
| Script requires administrator rights | Open **PowerShell → Run as administrator**, change to the project folder and retry. |
| Script file cannot be found | Open PowerShell from the folder containing `run_all.ps1` and the `scripts` folder, then retry. |
| No USB camera or USB network adapter is found | Try a known USB data cable and another USB port. If it persists, ask your installer to check the camera USB network driver and setup. |
| Camera login is denied | Setup already uses `root` / `root`. Check camera power and SSH access; ask your installer if the prepared camera rejects that standard login. |
| Wi-Fi checks fail | Confirm `-WifiSsid` exactly matches the PC Wi-Fi and the supplied password is correct. Keep USB connected. Guest Wi-Fi or a VPN may prevent this; ask your installer or network administrator. |
| A port is already in use | Close the previous WorkerCam installation on this PC. Ask your installer to stop any older background service. |
| Deployment seems stuck | Builds can take several minutes. Look for new Docker output. If it fails or stops progressing, collect the details below. |
| Updating or stopping is refused | Stop recording and wait for finalization before component operations. For a failed combined install, fix the error and rerun the [fresh deployment](scripts/README.md#entry-points-and-checks). |
| Page is blank or video is black | Check camera power, select Worker #07 and press **Ctrl+F5** to reload. Try **Settings → Diagnose camera**. |
| No worker sound | Click **Enable audio**, check PC volume and power on the earbuds outside their case. Try the restart below. |
| `/headsetmic` repeatedly disappears or reports no stream | Windows Firewall may be blocking UDP microphone packets. Rerun automatic deployment as administrator to refresh the rule for the camera's current IP. See [firewall recovery commands and explanation](scripts/README.md#windows-firewall-and-missing-headset-microphone-audio). |
| Worker cannot hear you | Allow browser microphone access, check the selected PC microphone and hold **Talk** while speaking. If unavailable, ask the installer to check the camera pairing file. |
| Deployment fails or reports incomplete recovery | Keep USB connected, fix the printed error and rerun the same command. No automatic rollback is attempted. |

### Restart when worker sound is missing

Finish recordings and wait for finalization. Run these lines one at a time.
Continue to the second line only after the first succeeds:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop_docker_pc.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_all.ps1 -WifiSsid 'YOUR_PC_WIFI_SSID' -HeadsetMac '6C:16:29:7B:00:D4'
```

Select **Worker #07**, click **Enable audio**, and check speech in both directions
again. If still silent, ask your installer to check the camera and earbuds.

### Details to send to your installer

Keep the error and last progress stage shown in PowerShell. Open another
PowerShell window in the project folder and run:

```powershell
docker compose ps
docker compose logs --tail 80 server
```

Send the output and describe whether picture, listening or talking failed.
Include any printed backup path. Keep passwords and private recovery snapshots out of shared diagnostics.

## Technical help for installers

- [Automatic deployment: credentials, network selection, backups and recovery](scripts/README.md)
- [Initial camera preparation and Docker troubleshooting](docs/docker-run-guide.md)
- [Architecture and connections](docs/architecture.md)
- [Headset microphone return](docs/headset-return-audio.md)
- [Headset audio setup and recovery](docs/sco-duplex.md)
- [Recording tracks and validation limits](docs/multistream-recording.md)
- [Frontend development](frontend/README.md)

Use this build on a trusted network. The supplied `admin` login is a prototype
interface login; access from other computers requires additional security setup.
