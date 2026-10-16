# Automatic USB discovery and full redeployment — 2026-10-16

User requested `scripts/deploy.ps1` to discover laptop/camera addresses, preserve
the fixed earbuds MAC, update configuration and redeploy both devices. Follow-up
requires Windows OpenSSH only and actual Docker/deployment verification. User
provided the existing camera password and asked for a simple runnable workflow.

## Repository findings and implementation

- PC: Docker Compose, `app.py`, FFmpeg, MediaMTX and operator HTTP UI. Existing
  TCP/video monitoring, independent UDP8004 headset return and multistream
  recording remain unchanged.
- Camera: existing `deploy_maix.ps1` staged installer, `/root/workercam.env`,
  Maix app launcher and `/etc/rc.local`. `PC_IP` controls microphone return;
  `HEADSET_MAC` is the fixed binding; existing audio profile is preserved.
- Ignored `.env` centralizes the six requested discovery values plus compatible
  `MAIX_IP`/`MAIX_USB_IP` aliases. No source-wide replacement. Browser endpoints
  remain local/relative. Added configuration/endpoint inventory in
  `scripts/README.md` and linked the one-command workflow in the root README.
- Added `scripts/NetworkDeployment.psm1`: adapter/subnet discovery, Windows
  routing selection, bounded concurrent SSH-port probes, process timeouts,
  configuration helpers and OpenSSH password/key support.
- Converted `deploy_maix.ps1` from PuTTY to Windows `ssh.exe`/`scp.exe`, retaining
  staged installation and backups. `scp -O` supports the camera's SCP server.
  Remote shell scripts travel through stdin, fixing nested reboot quoting.
  Fixed-MAC casing is preserved exactly. Existing video-rotation edits retained.
- Added `deploy_pc.ps1 -Recreate` for explicit restart after build; retained
  recording/finalization protection. Existing run_all accepts OpenSSH credentials
  without requiring a PuTTY fingerprint parameter.
- Entry point supports dry run, force, interface selection, encrypted local
  credentials or keys, input fingerprints, previous-image retention, local and
  camera backups, rollback and meaningful exit codes. Post-deployment checks
  inspect settings/processes/container/IP and decode both media streams.

## Evidence and failures

- Windows exposes physical Wi-Fi plus NCM and RNDIS USB adapters. Both USB
  subnets lead to one board, identified through the application installation,
  LicheeRv Nano board information and its Wi-Fi hardware MAC.
- Laptop Wi-Fi: `10.127.9.237`; camera Wi-Fi: `10.127.15.230`.
  Selected laptop USB: `10.172.16.100`; camera USB: `10.172.16.1`.
- Initial key-only Windows OpenSSH authentication failed. Supplied existing
  password worked through SSH_ASKPASS; saved Windows-encrypted credentials in
  ignored `.runtime/` for future one-command execution. No password/token value
  included in source, network configuration or session notes.
- Alternate USB `10.172.17.1` has a stale known_hosts entry and was rejected;
  discovery uses the verified NCM endpoint, without editing host keys.
- Real Windows PowerShell dry run passed: SSH identity verified across USB and
  Wi-Fi, routes validated, fixed headset recovered, Docker and idle recording
  preflight passed. No runtime configuration/service changes from dry run.
- Windows `Find-NetRoute` returns address and route objects: fixed strict-mode
  property handling. This environment cannot autoload Get-FileHash; input hashes
  now use .NET SHA256 directly. Both have regression coverage.
- First live install/reboot and Docker build succeeded; health verification
  failed because camera BusyBox has no `pgrep`. No success was reported. Automatic
  rollback restored the old local configuration, camera files and old Docker
  image from deployment `b2e54d4d10074f5582b125d068ef397a`.
- Replaced process checks with Python `/proc/*/cmdline` inspection (also detects
  duplicate audio processes and verifies microphone target). An isolated run of
  the corrected health function passed against the real deployed camera and
  Docker: settings, processes, container configuration, diagnostics/talkback APIs
  and both FFmpeg decodes.

- An immediate retry during rollback reboot saw no usable USB IPv4 adapter and
  exited at preflight without mutation. Retried after Windows re-enumerated the
  USB interfaces and DHCP completed.
- `python -m unittest tests.test_network_deployment tests.test_start_scripts -v`:
  initial 20 tests passed after the process-check correction. Coverage includes
  dry-run immutability, exact fixed-MAC preservation, interface filtering, route
  selection, configuration idempotence, force, recording protection, timeouts,
  SSH failure and failed-PC deployment rollback.
- PowerShell syntax parsing and `git diff --check` passed for the changed
  deployment files. Existing unrelated working-tree changes were retained.

- Second completed install/build hit the previously observed Windows Docker
  UDP-forwarding issue: video decoded but `/headsetmic` returned RTSP404. Camera
  processes and target were correct; Bluetooth was connected and talkback API
  available. The established recording-safe `stop_docker_pc.ps1` followed by
  `deploy_pc.ps1` restored return. The wrapper then passed its real checks and
  reported successful deployment. Backup id:
  `d795abf57a94411088636a09e8363975`.
- Added one bounded, recording-safe PC stop/start when headset return verification
  fails after deployment; verifies again and rolls back on persistent failure.
  Added a mocked regression. No camera/Bluetooth reset or media-route change.
  Ran the exact one-command entry point again to validate the finished script.

## Final unattended deployment

- Executed the exact `.\scripts\deploy.ps1` command from the project root in
  PowerShell 7, with no arguments and no manual intervention. It discovered both
  network paths, retained the exact headset setting/audio profile, installed and
  rebooted camera, built/recreated the PC Docker service and exited 0.
- Camera backup: `/root/workercam-backup-0ddc58ec4d474ec5b3e65b93c371bbda`;
  corresponding local backup retained under `.runtime/deploy-backups/`.
- Actual verification passed: one connector/talkback/microphone process with the
  correct target, camera return route using Wi-Fi, healthy Docker container with
  the detected camera address, camera diagnostics, talkback API, and FFmpeg
  decoding H.264 `/maix01` and G.711 `/headsetmic`. This run did not require the
  bounded UDP-forwarding recovery.
- Final automated suite: **21 tests passed**. Docker build completed using
  cached frontend/type-check and PC image layers. Syntax/diff checks passed.
- `.env`, encrypted credential and successful-deployment state are ignored by
  Git. No pairing token, earbuds MAC or adapter MAC was regenerated. Recordings
  retained. Docker healthy, operator recording=false. Audible speech/quality,
  physical latency and long stability were not tested.

- Repeated exact `.\scripts\deploy.ps1`: exited 0, reported no changed network
  keys and installation/build=False, skipped camera reboot and Docker rebuild,
  then passed both media decodes and application checks again. Configuration,
  laptop services and camera app reported **UNCHANGED (verified)**.

## Git publication validation

User requested committing/pushing the current changes and making them `main`.
Fetched origin and confirmed `origin/main` is an ancestor of the current
`experiment/sco-duplex` history, permitting a fast-forward without rewriting
remote history. The checkpoint includes pending video rotation/canvas work and
its required camera/PC modules together with automatic network deployment.

- Full Python suite: 140 tests run, 134 passed, 6 skipped.
- Frontend `npm test`: build/types succeeded; 30 source/compiled browser tests passed.
- Staged diff check passed; credential-pattern scan found no matches.
- `.env`, `.talkback_token`, `.runtime/` and recordings remain ignored and excluded.
- Git publication does not restart or redeploy the running devices.

Publication completed: implementation checkpoint `10cf819` was committed,
local `main` fast-forwarded, and `origin/main` pushed without force. GitHub's
default branch is already `main`. Local and remote commit IDs matched.

Switching through the older main revision removed the ignored local pairing
token and generated UI because that older revision still tracked those paths.
Restored the exact existing token from the camera and packaged UI from the
running container; no token was regenerated. SHA256 comparisons confirmed the
camera, local and container tokens match. Both paths remain ignored by Git.

User unplugged USB and requested Wi-Fi verification. Used Windows OpenSSH over
camera Wi-Fi `10.127.15.230`, bound to laptop Wi-Fi `10.127.9.237`, checking the
previously verified camera host identity. Camera settings/processes, Docker
health, actual video/headset-stream decoding and diagnostics/talkback APIs all
passed. No restart/redeploy was performed during this verification.

Final Bluetooth API status on two reads: fixed headset selected, connected=false.
The headset stream can decode without establishing current earbud speech capture;
audible duplex is not confirmed. No Bluetooth reset or pairing change performed.
