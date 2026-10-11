# Operator startup repair — 2026-10-11

## Request and evidence

The user supplied a fatal MediaMTX 1.21.1 Linux startup log: the configured
4,194,304-byte UDP receive buffer was limited to 212,992 bytes. They also supplied
H.264 `non-existing PPS 0 referenced`, `decode_slice_header error`, and `no frame`
messages. The Docker operator was restarting; no native project stack was running.
Container logs included an FFmpeg failure to determine video dimensions with the
one-second analysis window. Packet reception alone did not prove decoded video.

## Changes

- `app.py` limits positive MediaMTX UDP buffer requests to Linux's current
  `/proc/sys/net/core/rmem_max`. If that file is missing, unreadable or invalid,
  it overrides the request with zero (OS default). Supported requests, zero,
  and native Windows behavior remain unchanged. Oversized environment overrides
  are capped too; invalid overrides are left for MediaMTX to report.
- `start_operator.ps1` checks restarting as well as running Docker operators
  before starting native services, preventing overlapping stacks.
- `start_docker.ps1` no longer requires global Docker VM sysctl changes.
  The Docker guide describes kernel tuning as optional.
- Added regression tests for low/adequate limits, environment overrides,
  unavailable limits and unchanged Windows behavior. Preserved the existing
  Bluetooth edits and session notes.

## Commands and results

- Stopped only `server` using the two-file Compose configuration.
- Direct camera TCP ffprobe: 152 decoded H.264 frames over five seconds,
  640×480, 23 bytes of codec extradata, no PPS errors.
- Initial Docker smoke check mounting only new `app.py` failed because the old
  image lacked `pc.headset_return`. Mounting current `pc/` resolved that mismatch.
- Docker smoke check with current code and pinned MediaMTX 1.21.1: Linux limit
  file was unavailable, so OS-default fallback was selected; RTSP and WebRTC
  listeners started, process stayed alive, and shut down cleanly.
- `python -m unittest tests.test_app tests.test_rtsp_transport -v`: 21 passed.
- `python -m unittest discover -s tests -v`: 80 run, OK, two skipped.
  Output saved to ignored `.runtime/startup-repair-tests.log`.
- `docker compose -f compose.yaml -f compose.host.yaml build server`: passed,
  including frontend type check and build. Image now contains return audio code
  and the startup repair. Existing stopped container still uses its old image;
  Docker deployment must recreate it before using that route.
- Rebuilt-image smoke check using `docker run --rm`: RTSP and WebRTC listeners
  started successfully using OS-default buffers; process remained alive and
  shut down cleanly. Both PowerShell helpers parsed without syntax errors;
  `git diff --check` passed.
- `./start_operator.ps1`: HTTP200; restored native PID28756 with TCP/video
  and independent return on UDP8004. Relay ffprobe decoded 144 H.264 frames over
  five seconds at 640×480 with no errors. `/headsetmic` published G711, and logs
  showed browser WebRTC readers for both paths. Talkback status available.

## Final runtime and limits

Native operator remains running; Docker operator remains stopped. Camera files,
Bluetooth services and media profiles were not changed. PPS errors were not
reproduced in the short native check, so no probing/buffering changes were made
to the accepted video path. This does not prove the errors can never recur.
Intelligible microphone speech, audible talkback, SCO duplex and physical latency
were not remeasured. Docker-to-Windows host-network access remains unresolved.
