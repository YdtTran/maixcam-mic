# Restored commit redeployment — 2026-10-16

User requested restoring the latest commit, then redeploying all devices.
Tracked files were restored to `6e55f38`; existing untracked session evidence was retained.

## Deployment

- Used README combined `run_all.ps1 -DeployMaix -Build`, explicit SCO, established USB camera address, current PC Wi-Fi address and existing headset binding/token.
- Recording-idle preflight passed. Camera prerequisites and file installation passed.
- Camera backup: `/root/workercam-backup-173567171bbd4819a6094d02c6e93c0f`.
- Installer reboot command printed `sleep: missing operand`; subsequent SSH uptime confirmed an actual reboot and video port returned. No source repair made.
- Docker frontend build/types passed; image rebuilt and container recreated healthy. Windows HTTP check passed.
- Initial local helper failed loading the Windows PowerShell security module before deployment; used .NET SecureString construction and reran successfully. Credentials were not printed.
- Initial recreated PC container lacked `/headsetmic`. Camera sender/capture were running. Documented safe `stop_docker_pc.ps1` then `deploy_pc.ps1` restored G711 publication and browser peers. Underlying forwarding issue remains unproven.

## Verification and final runtime

- Real headless Chromium decoded H264 at 640×480 with no CSS rotation. Screenshot `.runtime/redeploy-latest-live.png` visually inspected and shows a clear physical scene.
- MediaMTX logs confirm WebRTC peers reading H264 `/maix01` and G711 `/headsetmic` after recovery.
- Camera eSCO connected, MTU120:4; one connector, duplex receiver, microphone sender and arecord were observed.
- PC Bluetooth status connected; talkback available without error. TCP/video and multistream settings retained.
- Audible speech/talkback and recording acceptance were not tested. No source changes or commits made as part of deployment.

- Independent two-second FFmpeg decode of /headsetmic succeeded. Additional browser audio readiness automation timed out; browser audible playback is not confirmed. An optional browser-launch command was rejected by automatic policy; services remain accessible at http://127.0.0.1:8000.
