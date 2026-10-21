# Hardening sections 6–8: downloads, obsolete padding and final checks

User requested continuing `harden-runtime-and-trim-obsolete-code` from 14/22
tasks. Implemented sections 6–7 and completed section 8's automated checks and
scope review. All 22 implementation tasks are checked. Implemented;
redeployment verification pending for these changes. No archival performed.

## Changes and scope

- `frontend/src/main.tsx`: real downloads click an anchor pointing directly at
  the validated same-origin recording file URL, with the recording filename.
  Only demo downloads retain fetch/Blob handling. The backend and range route
  need no changes. Updated the frontend guide.
- `frontend/tests/ui.spec.ts`: both browser builds download exact fixture bytes
  from a real `RecordingManager`/HTTP backend on an ephemeral loopback port.
  The fixture uses a temporary recording directory and the existing embedded
  MP4; only frontend assets are proxied from the test web server. Application
  file fetch and Blob creation throw in this test. It checks the filename,
  complete bytes, explicit/suffix ranges, an unsatisfiable range and playback
  seeking. The existing demo download test remains intact.
- `maix/video_rtsp.py`: fresh whole-tree caller search confirmed padding had no
  production caller and SPS cropping was used only by the retired fixture.
  Removed `pad_nv21`, `crop_encoder_padding` and `trim_padding`. Historical
  planning/session mentions remain. No references remain in production or tests.
- `tests/test_camera_rotation.py`: aligned 768x432/20fps fixture replaces the
  old 512x640 padding fixture. Actual FFmpeg RTSP/TCP decoding passes twice
  after reconnecting. Full Y/chroma rotation and packet reassembly checks remain.
  `maix/rtsp_av.py` still rotates the complete 432x768 frame to 768x432 in the
  explicit Python fallback; the default native-bound path remains 768x432/20fps.
- Installer OpenSSH requirements/private-key wording was already corrected by
  earlier work in the dirty tree. Verified script options and local links;
  added the README OpenSSH link, clarified verified `known_hosts` enrollment
  and `.ppk` export, and added per-run PowerShell bypass to the camera example.
  The separate desktop-setup proposal remains unchanged.

The first new browser probe attempted to redirect native downloads through
Playwright request interception; Chromium canceled that download. Replaced the
test transport with a real same-origin backend serving frontend assets, then
rebuilt the compiled UI. Both focused tests and the final full browser run pass.

## Verification

- `python -m unittest discover -s tests -v`: **206 run, 198 passed, eight
  skipped**, exit 0, 157.273 seconds. Log:
  `.runtime/hardening-remaining-python-tests.log`.
- `npm test` in `frontend`: type check/build/package and **44 browser checks
  passed**, across source/compiled interfaces. Log:
  `.runtime/hardening-remaining-browser-tests.log`.
- `docker compose config --quiet`: passed, without changing services.
- `MULTISTREAM_INTEGRATION=1 HEADSET_INTEGRATION=1 python -m unittest
  tests.test_multistream_integration tests.test_headset_integration -v`
  (environment flags set in the command's PowerShell process): **three passed**.
  Validates late/gapped audio, two sessions, four tracks, copied H.264,
  full-scale mixed voices, real Chromium WHEP video/PCMU return, WHIP/TB3
  signaling and video after microphone loss. Uses isolated fixtures/ports.
  Log: `.runtime/hardening-remaining-media-tests.log`.
- Existing `maix-cam-server:local` in a disposable `docker run --rm --network
  none`, with the checkout mounted read-only: **three boot/tuning checks passed**,
  including the two POSIX-only skips below. No production container was changed.
- `uv run --no-project --with numpy --with opencv-python-headless python -m
  unittest` with the two exact camera test names below: **two passed**. Packages
  were temporary test dependencies; project manifests/lockfiles are unchanged.
- Focused camera checks: 15 run, 13 passed, two dependency skips subsequently
  passed as above. Two actual FFmpeg decode/reconnect cycles passed.
- Installer cited script parameters/local links, `git diff --check`, and
  `openspec validate harden-runtime-and-trim-obsolete-code --strict`: passed.

Every skip in the full Python run:

| Test | Reason in default run | Follow-up |
| --- | --- | --- |
| `CameraRotationTests.test_full_y_and_chroma_planes_rotate_without_resampling` | NumPy unavailable | Passed with temporary NumPy/OpenCV |
| `CameraRotationTests.test_rotation_reuses_destination_for_changing_frames` | NumPy/OpenCV unavailable | Passed with temporary NumPy/OpenCV |
| `HeadsetIntegrationTests.test_independent_pcmu_video_recording_and_talkback` | Opt-in unset | Passed with `HEADSET_INTEGRATION=1` |
| `MultistreamIntegrationTests.test_correlated_full_scale_voices_do_not_clip_mix` | Opt-in unset | Passed with `MULTISTREAM_INTEGRATION=1` |
| `MultistreamIntegrationTests.test_late_audio_gaps_two_sessions_and_video_copy` | Opt-in unset | Passed with `MULTISTREAM_INTEGRATION=1` |
| `ScoStartupTests.test_failed_preparation_retries_before_any_audio_service_starts` | POSIX shell unavailable on Windows | Passed in isolated Linux container |
| `BootTuningTests.test_shell_runs_fallbacks_and_continues_when_tuning_fails` | POSIX shell unavailable on Windows | Passed in isolated Linux container |
| `UdpIntegrationTests.test_actual_udp_recording_whep_and_whip` | `UDP_INTEGRATION=1` and separate fixture required | Not run; required independent headset/multistream integrations passed |

## Final review and runtime limits

Reviewed the final hardening implementation and connected callers/tests against
all three delta specs and the eight audit findings. Existing Origin checks,
loopback publication and prototype login remain; extra Host/Origin hardening is
explicitly deferred by the later token-removal decision. Maintenance uses the
recording lock and persisted owner marker, all five entry points share the host
lock, and failed/old-image recovery retains exclusion. Talkback cleanup detaches
the original session before blocking cleanup and preserves retry diagnostics;
late cleanup and Stop remain identity-bound. Metadata errors preserve files and
warn separately; failed legacy output stays outside successful listings.

No new project dependency, unrelated rewrite or user-data migration was added.
Preserved pre-existing token-removal, efficiency, continuity and deployment
edits in the dirty tree. The earlier TB2-to-TB3 changes implement the separate
accepted token-removal decision; this continuation leaves TB3 framing,
freshness, clock calibration, session checks, bounded queues and SCO preparation
unchanged. Tests support those boundaries; they do not prove hardware operation.

No deployment, camera command, production recording edit or `.env` change was
performed. Production remains at the previously recorded P526 deployment; this
session does not reverify its live health. The known rollback snapshot
port-format defect remains outside these tasks. Before rollout/recovery, read
the [latest paired deployment evidence](2026-10-21-p526-redeployment.md).
Live picture/listening/Talk/rotation/recording and audible acceptance require
separate deployment verification. No long-duration, physical latency or A/V
synchronization claim follows from these checks.
