# Legacy recording outcomes — 2026-10-21

## Scope and result

User requested section 5, “Report legacy recording results honestly,” of
`harden-runtime-and-trim-obsolete-code`. Implemented tasks 5.1–5.2; OpenSpec
apply instructions confirmed progress from 12/22 to 14/22. Sections 6–8 and the
separate desktop-setup proposal remain pending. Implemented; redeployment
verification pending. This request did not authorize production deployment.

## Behavior and recovery

`RecordingManager` classifies legacy exits before clearing process handles,
using the same completion helper for spontaneous exit and explicit Stop.
Nonzero exit, forced termination and missing/empty output produce a retained
status error. Failed media moves to `<id>.failed.mp4`, outside the existing
successful-recording ID filter, with its `<id>.ffmpeg.log` retained and no
success JSON. The failure remains until a new capture starts successfully;
a failed spawn does not erase it. Error status itself is in memory; failed
filenames continue to be excluded after manager recreation.

A process surviving both stop and kill waits keeps its handle and capture lock
until exit is observed. Its media is hidden from listings while termination is
pending. Once it exits, the original interruption remains a failure even if
its final exit code is zero. Successful captures retain `<id>.mp4`, duration
and effective rotation metadata. Existing saved media is unchanged.

The UI gives a Stop response's error precedence over its saved-recording
notice. Existing polling also displays spontaneous failures. Recovery guidance
in `docs/multistream-recording.md` explains preserving failed media/logs and
verifying recovered copies. A killed MP4 may lack its index and be unrecoverable.
Automatic media repair is outside this change.

## Verification

- Final focused recording-manager run: 12 tests passed. Covers spontaneous and
  Stop exits 0/1/-9, forced kill returning zero, broken input, a second wait
  timeout, empty/missing media, retained failure across a rejected spawn and
  clearing on a successful new start. Temporary files and mocked processes
  verify filenames, metadata and exclusion after manager recreation.
- Existing multistream unit suite: all six tests passed, including failed mux
  staging retention and manager finalization/error handling.
- `npm test` in `frontend`: type check, build/package and all 42 source/compiled
  browser checks passed. Six new checks cover explicit nonzero Stop, forced
  termination and spontaneous failure. Explicit Stop checks hold the following
  status response pending to verify the immediate notice, rather than letting
  polling conceal an incorrect saved message.
- Initial full Python run: 206 tests, eight skips and one error in the existing
  rotation fixture, whose mocked `wait()` had no exit code. Updated that success
  fixture to return zero. Final full-suite rerun after all code/fixture changes:
  206 tests in 137.931 seconds, 198 passed, eight skipped, exit 0. Log:
  `.runtime/legacy-recording-python.log`.
- Compose configuration, strict OpenSpec validation and diff whitespace checks
  passed.

## Verification limits

No production process was restarted or deployed. Camera/headset settings,
recordings and unrelated existing worktree edits were preserved. Frontend
packaging refreshed ignored output. Browser APIs and legacy FFmpeg processes
are mocked in these regressions; they do not prove real media recovery or a
successful post-deployment recording cycle. Opt-in media integrations and
platform-dependent skips are recorded with the full-suite result below.

The eight skips in both full runs were:

1. `test_full_y_and_chroma_planes_rotate_without_resampling`: camera NumPy runtime.
2. `test_rotation_reuses_destination_for_changing_frames`: camera NumPy/OpenCV runtime.
3. `test_independent_pcmu_video_recording_and_talkback`: opt-in `HEADSET_INTEGRATION=1`.
4. `test_correlated_full_scale_voices_do_not_clip_mix`: opt-in `MULTISTREAM_INTEGRATION=1`.
5. `test_late_audio_gaps_two_sessions_and_video_copy`: opt-in `MULTISTREAM_INTEGRATION=1`.
6. `test_failed_preparation_retries_before_any_audio_service_starts`: POSIX boot shell.
7. `test_shell_runs_fallbacks_and_continues_when_tuning_fails`: POSIX boot shell.
8. `test_actual_udp_recording_whep_and_whip`: opt-in `UDP_INTEGRATION=1` and MediaMTX fixture.
