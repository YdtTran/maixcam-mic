# Portrait capture and Docker recovery — 2026-10-16

User requested force restart/redeployment and 480×640 capture, then clarified
that the existing web app should remain and only the video should rotate.
User selected 90° clockwise.

## Changes

- `maix/rtsp_av.py` captures 480×640 YVU420SP instead of 640×480.
- Physical live video receives a camera-only CSS class. The video swaps player
  dimensions and rotates 90° clockwise, with `contain` preserving the full image.
  Existing dashboard geometry, controls and demo orientation are retained.
- Source and compiled browser regression checks cover rotation and player bounds
  at 1366×768 and 1920×1080, and switching to the unrotated demo.
- README explains live rotation and original portrait orientation in saved files.

## Deployment and recovery

- Initial Docker Desktop restart completed, but container startup hung again.
- Rebuilt PC image successfully through `deploy_pc.ps1 -Build`; its container
  remained at Starting. A scoped forced restart of Docker processes and
  termination of `docker-desktop` did not clear the hang.
- WSL process inspection found `iptables` in D state, blocked in kernel module
  loading (`call_usermodehelper_exec` / `__request_module` / `nft_compat`). Kernel
  messages reported RCU task stalls. These are observed startup-block evidence;
  the original cause of the kernel stall remains unknown.
- Only `docker-desktop` was listed as a running WSL distribution. Stopped Docker
  processes, ran `wsl --shutdown`, and relaunched Docker Desktop hidden. Running
  `deploy_pc.ps1` then started the rebuilt container and passed health/Windows HTTP.
- Installed just the camera capture program at `/root/rtsp_av.py` and
  `/maixapp/apps/maix_rtsp/main.py`, with originals preserved in
  `/root/workercam-video-backup-20261016/`. Rebooted camera. Audio configuration,
  pairing token and PC destination were preserved.
- One initial inline Python deployment command failed local quoting validation
  before execution. Replaced with an ignored local helper; installation succeeded.
- First camera SSH check during reboot timed out; subsequent access succeeded.

## Verification and final runtime (approximately 09:57–09:58 local)

- `npm test`: 24 browser tests passed across source and compiled UI; build/types pass.
- `docker compose config --quiet` and `git diff --check` passed, with existing
  Windows line-ending warning for CSS.
- Camera TCP RTSP `ffprobe`: H.264, width 480, height 640.
- Real Chromium through Docker WHEP decoded 480×640 and advanced playback time.
  Computed matrix confirms clockwise rotation, object-fit is contain, and
  transformed bounds match the existing player (776×413 in the measured viewport).
  Screenshot inspected: `.runtime/portrait-live-20261016.png`.
- Container healthy; Windows operator HTTP verified. H.264 `/maix01` and G711
  `/headsetmic` publishers are online. No recording/finalization active.
- Camera has one video app, connector, duplex receiver and headset sender.
  Bluetooth controller SCO MTU remains 120:4, but `hcitool con` lists no headset
  connection, no arecord process is present, and PC Bluetooth API reports false.
  Talkback API reports available without an error; this does not prove audio.
  Headset sound and physical orientation of the camera scene need user acceptance.
- Saved recordings retain source portrait video; only the live web view rotates.
  No recording acceptance test was initiated. No commits made.
