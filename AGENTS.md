# Project Brain and Index

Read this file first when resuming work. It records current decisions and points
to detailed evidence; session logs preserve the history. Last updated: 2026-10-11.

## Current State and User Decisions

- **SCO duplex trial (2026-10-11):** User requested a separate branch and
  sustained SCO investigation. `experiment/sco-duplex` starts from accepted
  recovery commit `4e8aafb` on clean `uplink-audio`. User confirmed simultaneous
  browser speech in both directions and accepted it as hearable, authorizing
  this checkpoint commit; Maix-to-PC quality remains bad.
  Live camera trial uses SCO/CVSD, 120-byte SCO MTU, and 20ms/80ms raw playback
  with paced silence during packet gaps. Twenty automated WHIP cycles connected;
  one earlier attempt failed strict camera clock calibration. Return HCI packets
  include invalid/no-data flags; exact cause remains unresolved. Opt-in scoped
  stuck-SCO recovery has regression coverage; a live normal disconnect recovered
  in27 seconds without triggering reset. A60-second hold connected but still
  logged underruns. 101 tests OK, two skipped. TCP/video,
  UDP8004 return and video-only recordings preserved. Boot remains A2DP;
  separate SCO template is uninstalled. No physical latency gain measured.
  See [SCO trial log](docs/sessions/2026-10-11-sco-duplex.md) and
  [procedure/rollback](docs/sco-duplex.md).

- **Audio recovery (2026-10-11, approximately 08:58 local):** Both audio routes
  failed with a stuck eSCO link and capture hw-parameter errors. Scoped audio
  restarts and reconnect did not recover SCO; resetting only hci0 restored
  sound. User confirmed both directions, A2DP talkback working perfectly, but
  noisy/choppy return. Fixed receiver pause deadline race (3s vs capture's
  2s termination wait). Requested 20ms capture periods/80ms buffer: exact-zero
  return frames fell from 252/300 to 13/298, then 2/300 in short samples. User
  reports much smoother return, still below talkback quality. No physical
  latency improvement measured. A2DP/half-duplex,
  TCP/video and recording unchanged. 91 tests OK, two skipped. See
  [audio recovery log](docs/sessions/2026-10-11-audio-recovery.md).

- **Stage 1 SCO validation (2026-10-11):** Live USB inspection confirmed
  SCO/CVSD playback and capture at 8kHz mono. Two isolated SCO tone tests
  exited successfully, but the user reported interrupted SCO sound. Two
  A2DP file tests timed out; capture processes reopened after all tests.
  Keep production A2DP: continuous audible SCO acceptance failed. No runtime
  route/startup, TB2, duplex, lifecycle, video or recording changes.
  Prepared separate `validation/a2dp-baseline` and `validation/sco-stage1`
  worktree branches with test helper, procedure and rollback. Browser-cycle
  comparison and physical latency remain pending; no latency gain measured.
  See [Stage 1 log](docs/sessions/2026-10-11-sco-stage1.md).

- **Talkback repair (2026-10-11, approximately 00:30):** Measured camera clock
  2.169 seconds ahead of Windows; Windows Time is stopped and cannot be started
  by this session. PC talkback now calibrates packet timestamps to an authenticated
  camera clock endpoint for each session without relaxing the two-second age
  limit. Sender deadlines also compensate for coarse Windows timer waits.
  Camera playback drops temporary full-pipe frames instead of restarting
  audio; normal release clears stale PC interruption status. Camera connector
  PID1260 and receiver PID1481 deployed; native PID9128 retains TCP/video and
  UDP8004 return. Silent device test kept one player through the hold and restored
  capture; Chromium validated video, return audio and talkback signaling. Audible
  speech still needs user confirmation. See [talkback repair log](docs/sessions/2026-10-11-talkback-repair.md).

- **Operator startup repair (2026-10-11, approximately 00:17):** Docker operator
  was restarting on MediaMTX's 4 MiB UDP request versus the Linux buffer limit.
  `app.py` now caps the request to `rmem_max`, or uses OS defaults if unreadable;
  native Windows sizing is unchanged. Native helper now detects restarting
  Docker operators too; Docker helper no longer requires VM sysctl changes.
  Docker image rebuilt, but operator container remains stopped. Native PID28756
  restored TCP/video plus UDP8004 return; HTTP200, decoded H.264 and available
  talkback verified. PPS errors did not recur in the short native check.
  See [startup repair log](docs/sessions/2026-10-11-startup-repair.md).

- **Bluetooth reconnect repair (2026-10-11, approximately 00:09):** Documented
  pinned PuTTY login works via USB 10.172.16.1. Camera connector PID3846 now
  avoids redundant Bluetooth mutations on healthy polls, does not re-pair on
  failed status reads, and backs off failed reconnects to 30 seconds. Camera
  logs showed historical busy/unknown/timeouts and missing playback PCM; the
  physical drop cause remains unproven. BlueALSA4.1.1/BlueZ5.68 expose both SCO
  directions and A2DP playback. Only the connector was restarted; accepted
  TCP/video plus independent return and A2DP/pause talkback remain unchanged.
  See the Bluetooth stability log for backup paths and validation.

- **User acceptance (2026-10-11):** The user reports that latency is great after
  direct deployment and requested committing this implementation before further
  work. Preserve TCP/video plus independent PCMU return on UDP8004. This is user
  feedback, not a numeric physical measurement or confirmation of SCO duplex.

- **Direct deployment (2026-10-10, approximately 23:57):** Native Windows app
  PID16660 runs TCP/video with independent return on UDP8004. Existing camera
  RTP sender feeds `/headsetmic`; real Chromium decoded H.264 and received PCMU,
  audio element unmuted/playing. Six-second input level was very quiet (mean
  -76.3dB, peak -50dB), so intelligible earbuds speech remains unverified.
  Talkback status reports available. SSH root authentication failed twice,
  including the requested retry, so camera files/profiles were not changed;
  SCO duplex remains pending and legacy talkback pauses capture. See deployment log.

- **Headset return implementation (2026-10-10, approximately 23:50):** An independent
  PCMU RTP receiver and browser `/headsetmic` WHEP audio are implemented. Native
  `start_operator.ps1` enables UDP8004 return by default (`-ReturnAudioPort 0`
  disables it); video/recordings remain video-only. Synthetic real Chromium
  media and regression checks passed; physical headset capture/duplex and latency
  remain unverified because SSH authentication was unavailable. Production
  processes were not restarted. Final HTTP8000 check was refused and no
  MediaMTX/FFmpeg processes were present at that check, before direct deployment.
  Default camera A2DP talkback still pauses capture;
  explicit SCO/duplex options need hardware validation. See the return guide/log.

- **Earlier runtime (2026-10-10, approximately 19:19):** Docker Desktop restart
  did not restore Windows access to the host-network operator listeners. The
  operator container is stopped; a hidden native Windows `app.py` process now
  runs with explicit `--maix-ip 192.168.1.7 --rtsp-transport tcp --stream-mode
  video`. Windows operator HTTP returned 200, `/maix01` published one H.264
  track, and the talkback status API reported available. Browser playback and
  audible talkback were not remeasured in this follow-up. Logs/PID are in
  `.runtime/operator-native.*`. ThingsBoard and PostgreSQL were restarted and
  are running (PostgreSQL healthy). Stop native services before starting the
  operator container again; Docker localhost forwarding remains unresolved.
- **Earlier user status (2026-10-10):** Video and PC-to-camera talkback latency
  are acceptable. Earbuds → MaixCAM → PC microphone audio remains unimplemented
  end to end. Existing microphone service/code must not be treated as completion
  of that path. Preserve the accepted video and talkback operation.
- **Keep TCP video-only monitoring.** The user chose the configuration observed
  around 18:38–18:40 on 2026-10-10 and asked to retain it while they investigate
  audio latency. Local `.env` contains `RTSP_TRANSPORT=tcp` and `STREAM_MODE=video`;
  both were verified in the earlier running Docker container. The latest native
  workaround passes equivalent explicit flags. Do not switch back to
  combined mode or UDP as routine cleanup.
- Code defaults remain UDP/combined for compatibility. Compose reads `.env`;
  native `python app.py` does not automatically load it. Pass explicit flags for
  equivalent native operation.
- Video path: MaixCAM RTSP/TCP → PC FFmpeg H.264 copy → MediaMTX RTSP/TCP →
  admin browser WebRTC/WHEP over UDP. Installed camera TCP-interleaved support
  was verified by actual received H.264 packets.
- Current monitored stream and recordings exclude headset microphone audio.
  The original camera microphone service still publishes direct RTP/UDP to PC
  port 8004, but video-only FFmpeg does not consume it. WHIP talkback and the
  authenticated sequenced-UDP TB2 camera relay remain independently available.
- Preserve the working architecture. Diagnose buffering and stream timing before
  major changes; do not assume TCP reduces latency. Do not start duplicate camera
  capture or Bluetooth audio processes.

## Documentation Index

| Read this | For |
|---|---|
| [README.md](README.md) | Current configuration, startup and project overview |
| [Docker run guide](docs/docker-run-guide.md) | Installation and operational troubleshooting; apply the current README settings when older guide defaults differ |
| [Transport and measurement guide](docs/rtsp-transport.md) | TCP/UDP selection, isolated modes, physical stopwatch capture and timing diagnostics |
| [Measured results](docs/rtsp-measurements.md) | Physical latency, packet/continuity metrics, evidence and limitations |
| [2026-10-10 session log](docs/sessions/2026-10-10-rtsp-latency.md) | Investigation history, final user decision and next steps |
| [UDP protocol/deployment history](docs/udp-media.md) | Earlier UDP validation, protocol details and fallback |
| [Frontend guide](frontend/README.md) | UI development, API and persistence boundaries |
| [Headset return guide](docs/headset-return-audio.md) | Independent microphone return, duplex prerequisites, exact device/Windows commands and pending hardware checks |
| [Headset implementation log](docs/sessions/2026-10-10-headset-return.md) | Code changes, synthetic verification and unchanged live runtime |
| [Headset deployment log](docs/sessions/2026-10-10-headset-deployment.md) | Active native runtime, real camera RTP/browser delivery and remaining SSH/duplex limitation |
| [Headset acceptance log](docs/sessions/2026-10-11-headset-acceptance.md) | User latency feedback and implementation commit scope |
| [Bluetooth stability log](docs/sessions/2026-10-11-bluetooth-stability.md) | USB access, reconnect-handler repair, deployment and remaining physical-drop investigation |

## Findings and Open Questions

- Physical Edge pilots: UDP video-only 175 ms median / 200 ms p95 (12 clear
  samples); TCP video-only 230 / 240 ms (7); earlier UDP combined 1,710 / 1,980 ms
  (13). These are provisional, short trials, not guarantees or a fully controlled
  mode comparison. The user's original 10.23-second delay was not reproduced.
- Short UDP arrival-versus-PTS traces showed approximately −0.91 ms/s delay growth
  at the camera and +4.80 ms/s at combined relay output. This suggests examining
  the PC combined path; it does not isolate FFmpeg from MediaMTX or measure
  absolute stage latency.
- The user observed lower video **and audio** delay around 18:38–18:40. That time
  matches TCP video-only. Video measurements support the observation; the audio
  source remains unresolved because the publisher excluded microphone audio.
  The latest clarification accepts PC talkback latency and identifies earbuds →
  MaixCAM → PC audio as unimplemented; the earlier observation does not establish
  that the earbuds microphone path works.
- Physical synchronized audio/video testing is unavailable until a matching
  flash/click stimulus is arranged. Browser buffers, PTS offsets and startup time
  must not be reported as physical end-to-end or A/V synchronization measurements.
- Desktop capture works; built-in OCR was unreliable. Use simultaneous saved
  stopwatch images and clear manual readings. ROIs depend on the current desktop
  layout; reject occluded, ambiguous and reconnection samples.

## Session Memory Maintenance

After substantial work, add a dated log under `docs/sessions/` with user requests,
changes, commands/results, failures, unresolved questions and final runtime state.
Link it here and update current decisions. Separate measured facts, user reports
and hypotheses. Keep raw captures/logs in ignored `.runtime/`, recordings in
`recordings/`, and credentials/tokens out of session notes. Preserve unrelated
working-tree edits; the 2026-10-10 session began with extensive existing changes.

## Codex Runtime Conventions

Use `.codex/config.toml` as the baseline when present (absent in this checkout at
the last update). Keep MCP usage task-driven. Prefer project-local role files in
`.codex/agents/` when available, and follow current delegation instructions.
Project skills in `.agents/skills/` should describe concrete Codex workflows and
artifacts without Claude-only commands or hidden runtime assumptions.

## Repository Guidelines

## Project Structure & Module Organization

This project relays MaixCAM video and Bluetooth headset audio to the WorkerCam Admin interface. `app.py` supervises the PC stack; `pc/` contains the operator HTTP server, recording, Bluetooth client, and talkback relay. `maix/` contains camera programs and device startup templates. `frontend/src/` holds React/TypeScript UI code; `frontend/scripts/` packages the interface and generates demo media. Python tests live in `tests/`, browser tests in `frontend/tests/`, screenshots in `imgs/`, and runtime recordings in `recordings/`.

## Build, Test, and Development Commands

Run these from the repository root:

- Current working Windows route: `./start_operator.ps1` (`-Build` rebuilds frontend). It reads the three relevant `.env` settings, stops only the Docker operator if needed, reuses matching native operation and checks Windows HTTP access. Native defaults are TCP/video.
- `./stop_operator.ps1`: stop native project processes after stopping recording; rejects an active recording. Direct native alternative: `python app.py --maix-ip 192.168.1.7 --rtsp-transport tcp --stream-mode video` after stopping prior stacks.
- `./start_docker.ps1` (or `-Build`): start the Docker host-network route with saved `.env` settings after stopping native services; Windows localhost access on that route remains unresolved.
- `docker compose -f compose.yaml -f compose.host.yaml up --build -d`: build and start the host-network PC services directly.
- `docker compose logs -f`: inspect service logs; `docker compose down` stops services.
- `python app.py --rtsp-transport tcp --stream-mode video`: run the current configuration directly on Windows with FFmpeg on `PATH` and `mediamtx.exe` beside `app.py`; stop Docker first.
- `python -m unittest discover -s tests -v`: run Python tests.

Run these from `frontend/`:

- `npm ci`: install locked dependencies.
- `npm run dev`: start Vite; `/api` proxies to the separately running PC server on port 8000.
- `npm run build`: type-check and build the self-contained `pc/operator_test.html`. Regenerate this file after UI changes.
- `npx playwright install chromium`: install the browser required by tests.
- `npm test`: build and test both source and compiled interfaces.

## Coding Style & Naming Conventions

Match existing code: four-space Python indentation, two-space TypeScript indentation, and descriptive names. Use `snake_case` for Python functions/modules and `camelCase` for TypeScript functions/variables; React components and types use `PascalCase`. Keep media handling in `media.ts` and persistence/API access in `data.ts`. No dedicated formatter or linter is configured; the frontend build checks types.

## Testing Guidelines

Use Python `unittest` with `test_*.py` files and `test_*` methods; use Playwright `*.spec.ts` files for browser behavior. Mock hardware and media services in automated tests. No numeric coverage threshold is configured. Add regression coverage for changed behavior; document physical-device checks separately.

## Commit & Pull Request Guidelines

History uses short descriptive subjects without a consistent prefix scheme. Write imperative subjects, such as `Fix headset reconnect handling`. PRs should explain behavior changes, list validation commands/results, link relevant issues, and include screenshots for UI changes. Document hardware requirements when applicable.

## Security & Configuration

Keep PC and camera talkback tokens synchronized without exposing their values in logs or reviews. Treat frontend login as a prototype, not API authorization. Configure camera addressing through `MAIX_IP`; keep recordings and generated runtime files out of commits.
