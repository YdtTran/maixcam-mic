# Optional metadata isolation — 2026-10-21

## Request and scope

Implement only section 3, “Isolate malformed optional metadata,” of
`harden-runtime-and-trim-obsolete-code`. Tasks 3.1–3.3 are implemented;
OpenSpec progress is 7/22. The remaining sections and the separate desktop-setup
proposal are unchanged. This apply request does not authorize production deployment.

## Behavior and recovery

`RecordingManager` validates saved view documents before accessing rotation.
Malformed JSON, invalid encoding, wrong shapes, missing/invalid rotation and
read errors fall back to manager rotation zero. The configured camera baseline
offset remains independent. Original bytes are preserved during reads.

Recording sidecars must be objects with finite, nonnegative numeric durations;
booleans and numeric strings are rejected. Malformed, array, null, nonfinite,
overflowing and unreadable metadata leave nonempty recordings listed with
`duration_seconds: null`, rendered as Unknown. Missing sidecars also use unknown
duration. Existing valid numeric durations keep their integer-second behavior.

Status and camera-view responses expose `metadata_warnings` separately from
capture errors. A persistent UI message names each affected file and provides
recovery steps. Back up invalid view JSON before explicitly saving a rotation;
that normal atomic replacement clears only the view warning. Failed saves
propagate their error and preserve the warning and original view file. Back up
and repair sidecars, then refresh Recordings to clear their warnings. Media and
sidecar reads never rewrite or delete originals. See
[recovery guidance](../multistream-recording.md#optional-metadata-recovery).

## Verification

- `python -m unittest discover -s tests -v`: 189 tests run, no failures,
  eight skips (181 passed). After the final camera-view response field and
  preservation checks, focused operator tests passed 8/8 and orientation
  tests passed 4/4, including real FFmpeg rotation checks.
- `npm test` in `frontend`: build and all 34 source/compiled browser checks
  passed. New coverage shows warnings, usable recording controls, Unknown
  duration and warning clearing after valid rotation replacement.
- The first browser run caught a regression introduced while clearing warnings:
  waiting for a full refresh held rotation controls disabled behind a delayed
  Bluetooth poll. Removed that wait; the view-save response supplies warnings
  directly. Both delayed-poll regressions pass in the final run.
- `docker compose config --quiet`: passed.
- `openspec validate harden-runtime-and-trim-obsolete-code --strict`: passed.
- Scoped `git diff --check`: passed. Existing unrelated working-tree changes
  were preserved; no dependency or camera/media protocol changes were added.

The eight full-suite skips were:

1. `test_camera_rotation.CameraRotationTests.test_full_y_and_chroma_planes_rotate_without_resampling`
   (NumPy unavailable).
2. `test_camera_rotation.CameraRotationTests.test_rotation_reuses_destination_for_changing_frames`
   (NumPy/OpenCV unavailable).
3. `test_headset_integration.HeadsetIntegrationTests.test_independent_pcmu_video_recording_and_talkback`
   (`HEADSET_INTEGRATION` opt-in not enabled).
4. `test_multistream_integration.MultistreamIntegrationTests.test_correlated_full_scale_voices_do_not_clip_mix`
   (`MULTISTREAM_INTEGRATION` opt-in not enabled).
5. `test_multistream_integration.MultistreamIntegrationTests.test_late_audio_gaps_two_sessions_and_video_copy`
   (same opt-in).
6. `test_sco_startup.ScoStartupTests.test_failed_preparation_retries_before_any_audio_service_starts`
   (POSIX boot shell unavailable on Windows).
7. `test_start_scripts.BootTuningTests.test_shell_runs_fallbacks_and_continues_when_tuning_fails`
   (POSIX boot shell unavailable on Windows).
8. `test_udp_integration.UdpIntegrationTests.test_actual_udp_recording_whep_and_whip`
   (`UDP_INTEGRATION` fixture opt-in not enabled).

## Runtime and limits

No production services restarted, no device deployment, and no actual customer
recordings/settings changed. Synthetic fixtures used temporary directories and
browser mocks. Isolated opt-in media integrations and live picture/listening/
Talk/recording acceptance were not run for this metadata-only scope.
Implemented; redeployment verification pending. Overall change completion and
section 8 remain pending; automated diagnostics do not establish live acceptance.
