# Docker deployment and project cleanup — 2026-10-11

## User request and scope

User requested a deep scan for unnecessary files, Docker-only PC deployment,
exactly four PowerShell scripts for camera installation, PC installation,
Docker shutdown and combined startup, and a customer-readable README with demo
images. Later the user changed both Wi-Fi networks and confirmed USB access.
Continued the earlier uncommitted cleanup rather than reverting it.

## Result

- Replaced six PowerShell files with `deploy_maix.ps1`, `deploy_pc.ps1`,
  `stop_docker_pc.ps1` and `run_all.ps1`. PC and combined deployment protect
  recording/finalization. Routine startup does not reinstall the camera.
- Consolidated Compose into one published-port configuration: TCP/video,
  independent PCMU input on UDP8004/8005, loopback browser access, API health
  check, bounded Docker logs and a two-minute shutdown grace period. Legacy
  recording remains default; `.env` can select multistream.
- Camera installation checks prerequisites and staged syntax, backs up programs,
  launcher and startup settings, synchronizes the token, installs the app and
  writes PC/headset settings. Optional reboot waits for the video port.
  One boot template replaces the separate SCO file; A2DP remains the default.
  Experimental SCO requires explicit selection.
- Removed the old launchers, standalone FFmpeg PowerShell publisher, host-network
  override, unreliable stopwatch OCR adapter, original screenshot, historical
  implementation prompts and unused key. Capture/manual CSV measurement remains.
- Removed the generated HTML and pairing token from Git tracking while preserving
  both local files. Docker rebuilds HTML; missing tokens are generated locally.
  Build context excludes credentials, settings, dependencies, evidence and tools
  unnecessary for the runtime image.
- Rewrote the README with setup, daily controls, recording choices, shutdown,
  troubleshooting and network-change instructions. Updated current guides while
  preserving dated session history. Captured two actual interface screenshots
  using the offline demo worker; captions identify simulated data. The retained
  screenshot helper makes them reproducible.

The retained Python tests, diagnostic modules, frontend source/demo assets and
session history have distinct uses. Content hashes found only identical empty
Python package markers; both remain required package files. Saved recordings,
runtime evidence, existing dependencies and unrelated edits were retained.

## Validation and resolved failures

- `python -m unittest discover -s tests -v`: 116 tests, 112 passed, four optional
  integration tests skipped. Deployment tests exercise active/finalizing/unknown
  recording states, startup HTTP failure, upload/preflight/install failures and
  combined-startup ordering. Capture regression rejects untranscribed latency.
- `npm test`: build/type checks and 22 source/compiled browser tests passed;
  the completed test report is in ignored `frontend/test-results/.last-run.json`.
- `docker compose -f compose.yaml config --quiet`: passed.
- `docker compose -f compose.yaml build server`: passed. Inspected the built image
  for generated HTML and imports; token, local settings and measurement tooling
  are absent. An initial build-context allowlist included too many directory
  descendants; corrected its ordering and rebuilt.
- Isolated Docker fixture: Windows HTTP/API access, real Chromium decoded H.264
  and played PCMU return over published UDP, and Linux FFmpeg finalized an MP4
  with H.264 plus three AAC tracks. Temporary containers/network and the synthetic
  audio process were cleaned up. Camera boot/installer POSIX shell syntax passed.
- Fixture-only failures were resolved: a DNS camera alias failed the diagnostics
  IPv4 contract; using the container IPv4 fixed it. Recording controls reject
  nonempty bodies; changed the fixture POST to an empty body. Windows text stdin
  converted shell LF to CRLF; binary stdin fixed the syntax-check harness.
- Four project PowerShell files parsed successfully. Local Markdown links and
  `git diff --check` passed. No camera installer or reboot was executed.

Raw build/test/media logs and the isolated harness remain under ignored `.runtime`.

## New network and physical state

Read-only pinned PuTTY inspection via USB `10.172.16.1` confirmed camera Wi-Fi
`10.127.15.230/16`. Windows Wi-Fi is `10.127.9.237/16`. Updated only `MAIX_IP` in
local ignored `.env`, preserving the other settings. A temporary password file
was removed after use; no credentials are recorded here.

Camera inspection showed A2DP/default connector and receiver plus microphone
sender still targeting the former PC address `192.168.1.4:8004`. Docker diagnostics
reached camera SSH and Bluetooth control at its new Wi-Fi address; RTSP port8554
was unavailable. Physical video, microphone return and talkback cannot be accepted
from these checks. Deployment needs the current PC destination and an active
camera video app. The installer script prepares those settings, but was not run
on the device during this cleanup.

Docker Desktop was started for the image build and isolated checks. The real
project application was not deployed or restarted; no Bluetooth profile or
camera process was changed. Physical A/V sync, long drift, VLC selection and
customer-PC acceptance remain pending. Changes remain uncommitted for review.
