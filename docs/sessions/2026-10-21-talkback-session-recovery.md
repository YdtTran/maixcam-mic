# Local access preservation and talkback session recovery

User selected only sections 1 and 2 of
`harden-runtime-and-trim-obsolete-code`. Source implementation is ready;
**implemented; redeployment verification pending**. No live services, camera
configuration, saved recordings or credentials were changed in this session.

## Changes and scope

- Verified the current control Origin comparison in `pc/operator_server.py`,
  loopback HTTP/RTSP/WebRTC publication in `compose.yaml`, default operator
  bind address, and prototype admin login in `frontend/src/data.ts`. These
  behaviors remain unchanged; further Host/Origin hardening remains deferred.
- `pc/talkback.py` now captures each worker's session identity and cancellation
  event. Failure and Stop share idempotent retirement: detach decoder, WHIP
  location, workers and queued audio under the state lock, then send an
  identity-bound stop, reap and delete outside that lock. Current-session Stop
  acknowledges an interruption; stale Stop and late cleanup leave a retry alone.
- Decoder spawn finishing after cancellation reaps its own process without
  publishing it as a replacement's decoder. EOF/read failure cannot keep the
  speaking slot reserved. Cleanup skips joining its current worker and keeps
  the existing process/join/HTTP deadlines. Failure diagnostics survive automatic
  retirement until a fresh offer or acknowledgement.
- Added six regressions covering failed spawn/retry, media EOF, real worker
  failure, spawn/Stop races, delayed old cleanup with a new session, and bounded
  cleanup outside the state lock. Updated private-worker callers in transport
  and queue tests. Documented retry behavior in `docs/headset-return-audio.md`.
- TB3 framing, freshness, calibration, audio pacing, the three-frame queue,
  SCO/A2DP selection, video and independent microphone return are preserved.
  Existing unrelated working-tree edits were retained. No dependencies added.

## Verification

- Focused talkback (21), UDP protocol/queue (9), Bluetooth control/clock (14),
  and RTSP transport (11) checks passed. The final worker-signature simplification
  was followed by another talkback/UDP/transport run, all passing.
- Full Python suite: 186 tests, eight skips, no failures on the final rerun.
  An initial run exposed a transport fixture using the old private `_decode`
  signature; that caller was updated before rerunning.
- `npm test` in `frontend`: build/type check and all 32 source/compiled browser
  tests passed, including prototype login and talkback release behavior.
- `docker compose config --quiet`, strict OpenSpec validation and whitespace
  checks for the changed code/docs passed.
- OpenSpec tasks 1.1 and 2.1–2.3 are checked: 4/22. Sections 3–8 remain pending.

The eight Python skips were:

1. `test_full_y_and_chroma_planes_rotate_without_resampling`: camera NumPy runtime.
2. `test_rotation_reuses_destination_for_changing_frames`: camera NumPy/OpenCV runtime.
3. `test_independent_pcmu_video_recording_and_talkback`: opt-in `HEADSET_INTEGRATION`.
4. `test_correlated_full_scale_voices_do_not_clip_mix`: opt-in `MULTISTREAM_INTEGRATION`.
5. `test_late_audio_gaps_two_sessions_and_video_copy`: opt-in `MULTISTREAM_INTEGRATION`.
6. `test_failed_preparation_retries_before_any_audio_service_starts`: POSIX boot shell.
7. `test_shell_runs_fallbacks_and_continues_when_tuning_fails`: POSIX boot shell.
8. `test_actual_udp_recording_whep_and_whip`: opt-in `UDP_INTEGRATION` with MediaMTX fixture.

Logs are ignored local artifacts at `.runtime/harden-sections-1-2-python.log`
and `.runtime/harden-sections-1-2-browser.log`.

## Operational limits

The proposal separates source apply from production deployment; this request
does not authorize deployment. The running PC still uses its previously
deployed image. Live interruption/retry, audible headset recovery and sustained
stability remain unverified. WHIP deletion is best effort on HTTP failure;
local ownership is still released. Cleanup retains bounded waits even if a
decoder cannot be killed. No physical latency or new hardware acceptance claim.
