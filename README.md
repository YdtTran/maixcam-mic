# WorkerCam Admin — Windows setup and redeployment

WorkerCam lets you watch the MaixCAM camera, hear the worker through their
Bluetooth earbuds, speak back to them, and save recordings from your Windows PC.

Follow this guide to **update or reinstall an existing WorkerCam system**,
including after changing Wi-Fi or moving to another laptop. Automatic setup
finds the network addresses for you.

![WorkerCam dashboard](imgs/dashboard-demo.png)

*Screenshots show the built-in demonstration worker and simulated video.*

## 1. Get everything ready

You need:

- A Windows PC with internet access to download software components.
- The complete WorkerCam project folder, extracted from its ZIP file if supplied.
  Keep it somewhere permanent, for example `C:\WorkerCam`.
- A MaixCAM already prepared for WorkerCam, with its usual Bluetooth earbuds.
- A USB **data cable** connecting the camera to the PC. A charging-only cable
  will not work.
- The camera and PC connected to the same Wi-Fi network. Power on the camera
  and take the powered-on earbuds out of their case.
- The camera login details supplied by your installer.

**Changing Wi-Fi?** Connect the camera to the new Wi-Fi first, using your
installer's camera instructions, or ask them to help. The deployment command
finds addresses; it does not connect the camera to a new Wi-Fi network.

**Before updating:** stop any recording in WorkerCam and wait until
**Finalizing...** disappears. Keep USB connected throughout setup.

**Keep your existing files.** When replacing project files with an update,
retain `.env`, `.talkback_token`, `.runtime`, and `recordings` in the project
folder. These hold settings, camera pairing, recovery information and videos.

**Moving to another laptop?** Bring the matching `.talkback_token` from the old
installation with the project. Set up the camera password again in step 3;
the saved password file from another laptop cannot be reused. Stop WorkerCam on
the old PC before redeploying. The camera sends its microphone sound to one PC,
so redeployment switches that destination to the new laptop.

This procedure updates a prepared camera. A brand-new or factory-reset camera
needs the [initial camera preparation](docs/docker-run-guide.md) completed by
your installer first, including Wi-Fi, USB networking and headset setup.

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

Windows may ask for administrator approval during preparation. Ordinary
WorkerCam deployment runs in a normal PowerShell window. You do not need Python,
Node.js or separate video tools.

### Open PowerShell in the project folder

1. Open the WorkerCam project folder in File Explorer. You should see
   `run_all.ps1`, `deploy_pc.ps1`, and the `scripts` folder.
2. Click File Explorer's address bar, type `powershell`, and press **Enter**.
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

## 3. Set up camera access — once per laptop and Windows account

Skip this section if this Windows account already deploys this camera successfully.

### Trust the camera connection

Ask your installer for the camera's **USB address**, password and SSH fingerprint.
The fingerprint identifies the camera when Windows first connects. Use the USB
address in this command; `10.172.16.1` below is an example:

```powershell
ssh root@10.172.16.1
```

If asked whether to continue connecting, compare the displayed fingerprint with
the one supplied by your installer. Type `yes` only when they match. Enter the
camera password when asked; no characters appear while you type it.

Once logged in, type `exit` and press **Enter** to return to Windows PowerShell.
If Windows warns that the camera identification has changed, ask your installer
to check it before continuing.

### Save the camera password

Paste these three lines into Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force .runtime | Out-Null
$credential = Get-Credential -UserName root -Message 'Enter the camera password supplied by your installer'
$credential | Export-Clixml .runtime\deploy-credential.xml
```

Enter the camera password in the prompt and confirm. Windows saves it encrypted
for your account on this PC. Do this again if the password changes.

If your installer supplied an SSH key instead of a password, use the
[key-based access instructions](scripts/README.md#credentials-once-per-windows-account).

## 4. Redeploy the camera and PC

With Docker Desktop running, USB connected and both devices on Wi-Fi, paste this
command into PowerShell and press **Enter**:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy.ps1
```

The script finds the camera, checks the connections, updates the saved addresses,
and installs the camera and PC software when needed. It keeps the camera's
existing earbuds selection and audio settings. Settings are backed up before
changes. You do not need to edit network addresses yourself.

**Wait for it to finish.** The camera may restart and its picture will disappear
briefly. The PC build may take several minutes, especially the first time.
Progress includes `[PC 1/5]` through `[PC 5/5]`, followed by connection checks.
Keep Docker Desktop running and leave the PowerShell window open.

Look for this final message:

```text
Deployment completed successfully.
```

`UNCHANGED (verified)` also means success: the installed version already matched
and its checks passed. If the script reports failure, use the help section below
before using the system.

To deliberately reinstall both devices even when nothing has changed, use this
command **instead of** the normal command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy.ps1 -Force
```

To check preparation without installing or restarting anything:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy.ps1 -DryRun
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_all.ps1
```

This starts the PC software and opens the browser. You do not need to reinstall
the camera each day. After moving to another network or laptop, repeat the
redeployment steps above with USB connected.

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
| Scripts are blocked | Copy the complete command, starting with `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`. If your organization's policy still blocks it, ask its IT team. |
| Script file cannot be found | Open PowerShell from the folder containing `run_all.ps1` and the `scripts` folder, then retry. |
| No USB camera or USB network adapter is found | Try a known USB data cable and another USB port. If it persists, ask your installer to check the camera USB network driver and setup. |
| Camera login is denied | Repeat step 3 with the correct camera password. On a new laptop, create a new saved password file. |
| Wi-Fi checks fail | Confirm the camera and PC are on the same Wi-Fi and can communicate. Guest Wi-Fi or a VPN may prevent this; ask your installer or network administrator. |
| A port is already in use | Close the previous WorkerCam installation on this PC. Ask your installer to stop any older background service. |
| Deployment seems stuck | Builds can take several minutes. Look for new Docker output. If it fails or stops progressing, collect the details below. |
| Updating or stopping is refused | Stop recording in the browser and wait for finalization. Retry when it finishes. |
| Page is blank or video is black | Check camera power, select Worker #07 and press **Ctrl+F5** to reload. Try **Settings → Diagnose camera**. |
| No worker sound | Click **Enable audio**, check PC volume and power on the earbuds outside their case. Try the restart below. |
| Worker cannot hear you | Allow browser microphone access, check the selected PC microphone and hold **Talk** while speaking. If unavailable, ask the installer to check the camera pairing file. |
| Deployment fails or reports incomplete recovery | Keep USB connected and preserve the printed backup path. Ask your installer for help using the error and logs below. Keep the backups. |

### Restart when worker sound is missing

Finish recordings and wait for finalization. Run these lines one at a time.
Continue to the second line only after the first succeeds:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop_docker_pc.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_all.ps1
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
Include any printed backup path. Keep passwords and the contents of
`.talkback_token` private.

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
