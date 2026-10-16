# Project Brain and Index

Read this file first when resuming work. It records current decisions and points
to detailed evidence; session logs preserve the history. Last updated: 2026-10-16.

## Current State and User Decisions

- **Restored commit redeployed (2026-10-16):** User requested latest-commit restore and redeployment of both devices. Camera installed/rebooted and Docker rebuilt healthy from  `6e55f38`. Clear 640×480 landscape video visually verified in Chromium. SCO connected at MTU120; PC stop/start restored initially missing G711 return. Talkback available; audible acceptance untested. See [deployment log](docs/sessions/2026-10-16-restored-commit-redeployment.md).

- **Architecture reference and safe local cleanup (2026-10-16):** User reports
  the architecture works well and requests documentation without code changes.
  Added source-checked architecture/pipeline/protocol reference and rendered
  diagram. Preserved all existing source/configuration edits and live services.
  Permanent cleanup was rejected by automatic approval policy; moved six
  disposable cache/build/test-output directories (46 files, 1,576,087 bytes) into
  ignored `.runtime/cleanup-quarantine-2026-10-16/` for reversible cleanup instead.
  Settings, token, recordings, dependencies, packaged UI and session evidence
  retained. See [architecture](docs/architecture.md) and
  [session log](docs/sessions/2026-10-16-architecture-cleanup.md).

- **SCO/multistream deployed (2026-10-11):** User requested README update and
  redeployment of both devices. Combined workflow installed/rebooted MaixCAM
  with SCO and rebuilt/recreated the healthy Docker PC with multistream.
  Windows HTTP passed; browser peers read H264 video and G711 headset return.
  Camera eSCO connected, MTU120:4, one capture; PC Bluetooth connected and
  talkback available. No recording/audio acceptance trial performed. See
  [redeployment log](docs/sessions/2026-10-11-sco-multimedia-redeployment.md).

- **SCO and multimedia defaults (2026-10-11):** User requested SCO and multimedia
  as the default pipeline, reporting SCO already in use. Multimedia means the
  existing multistream recorder: video plus mixed/worker/operator audio. Compose,
  `.env.example`, local `.env`, app and recorder defaults now select multistream;
  camera startup fallback also selects SCO. Explicit legacy/A2DP remain available.
  TCP/video monitoring and independent UDP8004 return are preserved. Suite ran
  123 tests successfully with five skips; Compose validation passed. No services
  restarted; recording changes activate at the next PC rebuild/deployment. See
  [default pipeline log](docs/sessions/2026-10-11-sco-multimedia-default.md).

- **SCO deployment defaults aligned (2026-10-11):** User reiterated recovered
  SCO setup is the default. `deploy_maix.ps1` and `run_all.ps1` now default
  `AudioProfile` to `sco`; explicit `a2dp` remains fallback. README and installer
  guides agree and include safe missing-headsetmic recovery. Legacy recording
  remains default, multistream optional. Ten deployment checks passed. No runtime
  restart in this update. Supersedes the earlier docs-only/A2DP script-default
  decision below. See [default update log](docs/sessions/2026-10-11-readme-sco-default.md).

- **Headset return recovery (2026-10-11,08:34–08:39 UTC):** User authorized
  fixing the outage. Safe PC stop/start restored UDP8004 publication and browser
  audio connection. Headset reconnect remained busy; scoped reset attempt lost
  camera access, then user hard-rebooted camera. After reconnect retries, SCO
  capture returned. Final six-second `/headsetmic` decode produced48000 samples,
  34190 nonzero; no new return loss in inspected post08:38:30 logs. Docker healthy,
  SCO120, talkback available. Audible user confirmation pending; underlying
  forwarding/profile failure causes remain unproven. No source fix in this
  recovery. See [outage/recovery evidence](docs/sessions/2026-10-11-headsetmic-outage.md).

- **Headset return outage (2026-10-11,08:31–08:32 UTC):** User pasted missing
  `/headsetmic` stream errors. Read-only checks found no SCO link, capture
  PCM-not-found retries, and PC receiver publication timeout/backoff. Camera
  still sends UDP8004 packets; eight-second container check saw none during
  receiver backoff. Addressing unchanged, Docker API healthy; no repair done.
  Cause of packet delivery loss remains unisolated. See
  [outage evidence](docs/sessions/2026-10-11-headsetmic-outage.md).

- **README standard SCO pipeline (2026-10-11):** User requested README use SCO
  duplex as the default pipeline. Camera and combined deployment examples now
  explicitly pass `-AudioProfile sco`, explain simultaneous listening/talkback,
  post-reboot checks and A2DP fallback. This documentation change does not alter
  script parameter defaults (A2DP when omitted), recordings or live services.
  See [README update log](docs/sessions/2026-10-11-readme-sco-default.md).

- **SCO boot-order repair (2026-10-11):** User requested root-cause fix.
  Traced boot confirmed MTU120 applied while down, power-up resetting to255,
  capture/eSCO opening at255, and connector overriding too late. SCO boot now
  synchronously powers/prepares/verifies MTU before audio clients start. Tests
  cover reset ordering and failed preparation; actual shell retry test passed.
  Fixed traced reboot opened capture/eSCO only at120; user confirmed steady
  WHIP tone without manual reconnect. Production probe removed; second clean
  reboot verified connected SCO120, stable capture and successful WHIP relay.
  Final suite121 tests/five skips; POSIX startup test separately passed in Docker.
  See [repair evidence](docs/sessions/2026-10-11-sco-boot-order.md).

- **SCO talkback recovery (2026-10-11):** User authorized a fix. Headset was
  connected and unmuted but initial WHIP tone was inaudible. Clean pause/ack,
  scoped headset disconnect/reconnect and capture resume restored delivery;
  user confirmed a steady tone through a 20-second browser-path WHIP test.
  Source, video, PC runtime and recording mode unchanged. Exact silent-link
  cause and prolonged stability remain unproven. See
  [recovery evidence](docs/sessions/2026-10-11-readme-redeployment.md).

- **Post-reboot SCO check (2026-10-11):** User rebooted camera. Read-only check
  confirmed one SCO connector, duplex receiver, microphone sender and SCO capture;
  eSCO connected, MTU 120:4. PC healthy, Bluetooth connected, talkback available;
  video/return republished after reboot. Persistent audio logs contain errors
  without enough timestamps to assign them to this boot. No fixes performed;
  audible duplex unverified. See
  [redeployment evidence](docs/sessions/2026-10-11-readme-redeployment.md).

- **SCO redeployment follow-up (2026-10-11):** User requested SCO duplex.
  Combined deployment with `-AudioProfile sco` passed camera reboot/video-port,
  Docker build/health and Windows HTTP checks. Camera configuration confirmed
  SCO in both directions at 8 kHz mono and MTU 120:4. Extra process inspection
  failed on unsupported BusyBox `ps -ww`; stopped checks without fixes as
  requested. Audible duplex remains unverified. See
  [redeployment evidence](docs/sessions/2026-10-11-readme-redeployment.md).

- **README redeployment (2026-10-11):** User requested both devices redeployed
  with failures reported and no fixes. Combined README workflow completed:
  MaixCAM installed/rebooted with default A2DP and PC destination 10.127.9.237;
  Docker rebuilt/recreated, healthy, Windows HTTP verified and browser opened.
  Logs confirmed online H.264 video and G.711 return. Audible checks remain
  untested. See [redeployment evidence](docs/sessions/2026-10-11-readme-redeployment.md).

- **Docker deployment cleanup (2026-10-11):** User chose Docker for all PC
  deployment and exactly four PowerShell entry points: `deploy_maix.ps1`,
  `deploy_pc.ps1`, `stop_docker_pc.ps1`, `run_all.ps1`. One Compose configuration
  now defaults to TCP/video plus independent UDP8004 return, with local browser
  port publication. Camera programs remain on MaixCAM; one parameterized boot
  template supports A2DP by default and opt-in experimental SCO. Generated HTML
  and the local pairing token are no longer tracked. README is a customer guide
  with actual demo screenshots. This supersedes older native startup instructions
  below; those entries retain the history. See
  [deployment cleanup evidence](docs/sessions/2026-10-11-docker-cleanup.md).

- **Repository cleanup (2026-10-11):** Removed two obsolete implementation prompts
  and unreferenced `auto.key`. Retained runtime files, packaged UI, diagnostic
  tools, package markers and session evidence. No live services changed. See
  [cleanup log](docs/sessions/2026-10-11-repository-cleanup.md).

- **PC multistream recorder (2026-10-11):** Implemented opt-in
  `--recording-mode multistream` / native `-RecordingMode multistream`. Independent
  H.264-copy staging and reconnecting 48 kHz PCM decoders produce mixed default,
  worker and operator AAC tracks on asynchronous stop. Monotonic audio timeline
  with silence; video arrival timestamps use a fixed PC clock bridge. Legacy
  recorder remains default. No camera, Bluetooth, live TCP/video route or runtime
  deployment changes. 105 Python tests passed, four skipped; two isolated real
  media tests and 22 browser tests passed. Physical flash/click synchronization,
  long hardware drift and VLC acceptance remain pending. See
  [recording guide](docs/multistream-recording.md) and
  [session evidence](docs/sessions/2026-10-11-multistream-recording.md).

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
| [Architecture and protocols](docs/architecture.md) | Current Docker/SCO architecture, four data pipelines, port map, TB2 format and storage boundaries |
| [Docker run guide](docs/docker-run-guide.md) | Installation and operational troubleshooting; apply the current README settings when older guide defaults differ |
| [Transport and measurement guide](docs/rtsp-transport.md) | TCP/UDP selection, isolated modes, physical stopwatch capture and timing diagnostics |
| [Measured results](docs/rtsp-measurements.md) | Physical latency, packet/continuity metrics, evidence and limitations |
| [2026-10-10 session log](docs/sessions/2026-10-10-rtsp-latency.md) | Investigation history, final user decision and next steps |
| [UDP protocol/deployment history](docs/udp-media.md) | Earlier UDP validation, protocol details and fallback |
| [Frontend guide](frontend/README.md) | UI development, API and persistence boundaries |
| [Multistream recording](docs/multistream-recording.md) | Default PC recorder, timeline strategy, four-track MP4, recovery and physical acceptance procedure |
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

- `./run_all.ps1`: start the Docker PC service and open its local browser UI.
- `./deploy_pc.ps1 -Build`: build/update the Docker image after changes. Refuses
  active recordings and verifies container health plus Windows HTTP access.
- `./stop_docker_pc.ps1`: stop only this project's container after recording and
  finalization complete; retains saved recordings.
- `./deploy_maix.ps1 -MaixHost <address> -PcIp <PC-LAN-IP> -HeadsetMac <MAC>
  -HostKey <verified-key> -Reboot`: install camera programs with backups, then
  activate by reboot. Requires a prepared camera and PuTTY. Default SCO;
  A2DP fallback requires explicit `-AudioProfile a2dp`.
- `docker compose config --quiet`: validate the single Compose configuration.
- `docker compose logs --tail 80 server`: inspect PC service logs.
- `python -m unittest discover -s tests -v`: run developer Python checks. Local
  Python/media tools are development dependencies, not customer requirements.

Run these from `frontend/`:

- `npm ci`: install locked dependencies.
- `npm run dev`: start Vite; `/api` proxies to the separately running PC server on port 8000.
- `npm run build`: type-check and generate ignored `pc/operator_test.html`. Docker generates it during image builds; do not commit the compiled copy.
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
