# Project Brain and Index

Read this file first when resuming work. It records current decisions and points
to detailed evidence; session logs preserve the history. Last updated: 2026-10-10.

## Current State and User Decisions

- **Latest runtime (2026-10-10, approximately 19:19):** Docker Desktop restart
  did not restore Windows access to the host-network operator listeners. The
  operator container is stopped; a hidden native Windows `app.py` process now
  runs with explicit `--maix-ip 192.168.1.7 --rtsp-transport tcp --stream-mode
  video`. Windows operator HTTP returned 200, `/maix01` published one H.264
  track, and the talkback status API reported available. Browser playback and
  audible talkback were not remeasured in this follow-up. Logs/PID are in
  `.runtime/operator-native.*`. ThingsBoard and PostgreSQL were restarted and
  are running (PostgreSQL healthy). Stop native services before starting the
  operator container again; Docker localhost forwarding remains unresolved.
- **Latest user status (2026-10-10):** Video and PC-to-camera talkback latency
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
