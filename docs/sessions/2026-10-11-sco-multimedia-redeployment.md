# README and SCO/multistream redeployment — 2026-10-11

User requested README updates and redeployment of both PC and MaixCAM.
Updated README with a combined update procedure, explicit migration of existing
.env recording selection, recording/finalization prerequisites and output checks.

## Deployment

Docker Desktop was initially stopped. Started it with `docker desktop start`.
An early PC check failed while its HTTP service was still starting; subsequent
combined workflow passed recording-idle preflight. No protections were bypassed.

Ran `run_all.ps1 -DeployMaix -Build` using established pinned camera access,
USB 10.172.16.1, PC Wi-Fi 10.127.9.237, existing headset binding and explicit SCO.
Preserved the matching pairing token and .env camera address 10.127.15.230.
Credentials were passed privately and are omitted here.

Camera prerequisites, upload, installation and reboot/video-port checks passed.
Backup: `/root/workercam-backup-d3134105ca954330872ce99d3b7d296a`.
Docker build and container recreation passed. Container is healthy and Windows
operator HTTP check passed; the combined script opened the browser.

## Final evidence (approximately 08:55 UTC)

- Active container command includes `--recording-mode multistream`.
- Camera workercam.env selects SCO and PC destination 10.127.9.237.
- Controller SCO MTU 120:4; later eSCO and ACL both connected in state 1.
- One connector, duplex/SCO talkback receiver and headset sender; one SCO arecord
  capture at 8 kHz mono with 20 ms period and 80 ms buffer.
- PC Bluetooth API connected; talkback available with no reported error.
- Recording idle. No live recording was initiated for validation.
- MediaMTX logs show browser WebRTC peers reading H264 maix01 and G711 headsetmic.
- Capture log tail includes PCM-not-found retries followed by capture started.
  Persistent log lines lack timestamps, so their exact boot attribution is unknown.
- A check accidentally requested /bluetooth/status and got 404; corrected
  /api/bluetooth/status returned connected. No source repair was required.

`docker compose config --quiet` and `git diff --check` passed (existing line-ending
warnings only). Prior default update suite: 123 tests, OK, five skips.

Audible speech in both directions, saved track playback, physical synchronization
and prolonged hardware stability were not remeasured. Final runtime is the rebuilt
Docker PC stack with multistream configured and rebooted MaixCAM with SCO duplex.
