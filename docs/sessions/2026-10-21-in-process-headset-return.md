# Section 3: in-process headset return and boot tuning

## Scope and implementation

User selected section 3 of `optimize-maixcam-cpu-and-video-transport`.
Implemented tasks 3.1 and 3.2; section 4 and paired deployment remain separate.

- `maix/headset_mic_stream.py`: direct `--rtp-port` mode uses a nonblocking
  in-process UDP sender. Each 320-byte S16LE frame becomes a 160-byte PCMU
  payload and a 12-byte RTP header (version 2, payload type 0). Random initial
  sequence/timestamp/SSRC, one-packet sequence increments and 160-sample
  timestamp increments include field wraparound. Socket backpressure drops
  stale frames; network failures close resources and enter the existing retry
  loop. `audioop` encodes where available; Python 3.13+ uses a 64 KiB table.
- Existing capture selection, retry, pause acknowledgement, silence generation
  and 20 ms pacing are preserved. Selected headset capture still uses `arecord`;
  direct UDP mode starts no FFmpeg process. Explicit RTSP audio retains FFmpeg.
- `maix/background_services.rc.local`: best-effort console verbosity and Wi-Fi
  power-save commands execute before SCO preparation/background service startup,
  with procfs and `iwconfig` fallbacks. Existing SCO ordering remains intact.
- Updated `docs/headset-return-audio.md` and tests. Boot shell tests stub tuning
  commands to avoid changing their host. Three existing transport test fixtures
  now inject the readiness wait into `app.run`: patching its module name did
  not replace the function already bound as a default argument. Combined with
  their frozen clock, that caused an indefinite wait without live MediaMTX.

## Verification

- Focused `python -m unittest tests.test_headset_return tests.test_start_scripts -v`:
  26 tests, success, one POSIX-only skip on Windows.
- Packet tests receive actual loopback UDP datagrams and assert exact header
  bytes, payloads and counter wraparound. Tests cover selected-headset capture,
  paused silence without subprocesses, RTSP compatibility, cleanup, frame
  validation and socket backpressure/errors. All 65,536 fallback table entries
  match `audioop`; known signed sample vectors also pass without `audioop`.
- Isolated `docker run --rm --network none` using existing
  `maix-cam-server:local`, read-only repository mount: nine sender/boot tests
  passed, including real POSIX shell fallback failure paths and SCO ordering.
- Compose configuration, OpenSpec validation and diff whitespace checks passed.
- Full Python suite: 178 tests ran successfully, eight skipped (optional media
  integrations, camera NumPy/OpenCV and POSIX-only shell checks on Windows).
  Log: ignored `.runtime/section-three-python-tests.log`. A subsequent additional
  unit test passed for main-loop network-error retry; no runtime code changed
  after the full run except an explanatory encoder comment.

## Runtime state and limits

Implemented; redeployment verification pending. No camera deployment, service
restart, local `.env` changes or recording modifications. The plan reserves
paired deployment for separate user authorization. Frontend checks are left
for section 4; no frontend behavior changed in this section.

Console filtering does not disable syslog kernel-message collection. No CPU,
RAM, Wi-Fi stability, physical latency, sustained media or audible improvement
is established here. Hardware startup, listening, Talk, video, rotation and
recording/playback must be verified after deployment; the previously observed
intermittent camera failure remains unresolved.

Protocol references: [RTP header and counters](https://www.rfc-editor.org/rfc/rfc3550.html#section-5.1),
[PCMU profile](https://www.rfc-editor.org/rfc/rfc3551.html#section-4.5.14).
