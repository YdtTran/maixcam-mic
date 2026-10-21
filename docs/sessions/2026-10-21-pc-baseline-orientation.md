# PC baseline camera orientation — 2026-10-21

## Request and scope

User requested section 2, “PC-side zero-reencode orientation with optional
baseline camera offset,” of `optimize-maixcam-cpu-and-video-transport`.
Implemented task 2.1 only. Existing uncommitted changes were preserved.
Sections 3 and 4 remain unchecked; the regression runs below support this
section and do not complete the remaining implementation or live acceptance.

## Changes

- Both `app.py` and `python -m pc.operator_server` accept
  `--camera-base-rotation`, defaulting to process `CAMERA_BASE_ROTATION` or `0`.
  Only integer quarter turns 0/90/180/270 are accepted; invalid environment
  defaults also fail before startup.
- Compose passes `CAMERA_BASE_ROTATION` from PC `.env`; `.env.example` documents
  the default. Direct Python entry points do not load `.env`.
- `RecordingManager` computes `(base_rotation + manager_rotation) % 360` in
  counter-clockwise degrees. The API retains `rotation` as the manager selection
  and adds `effective_rotation` to view and recording status responses.
- The browser retains the manager selector and uses the effective angle for its
  existing canvas quarter-turn display (CSS for 0/180), including refresh,
  start/stop and rotation-save responses. Older responses without the new field
  fall back to their original rotation.
- Legacy and multistream recorders receive the effective angle for their
  existing MP4 display matrix handling. H.264 remains copied; legacy sidecar
  metadata now records the effective angle, matching multistream metadata.
- `.camera-view.json` keeps only the manager selection, avoiding double offsets
  after restart. Existing recordings are unchanged. Capture/finalization locks
  continue to prevent manager rotation changes.
- Updated `docs/architecture.md` and `docs/rtsp-transport.md`, including the
  pending runtime status and the older diagram's camera-rotation limitation.

## Verification

- `python -m unittest tests.test_video_orientation tests.test_app tests.test_operator_server -v`:
  24 tests passed, including all 16 baseline/selection combinations, validation,
  persistence, recording locks and effective angles in both recorder paths.
- Real FFmpeg orientation test passed for all four angles: source 768x432
  dimensions and H.264 slice bytes retained, decoded display matches expected
  pixel rotation, four MP4 tracks retained.
- `npm test --prefix frontend`: build/type check passed, all 32 browser checks
  passed across source and compiled interfaces. New test covers a 270-degree
  baseline, wraparound, canvas activation, recording and reload persistence.
- `python -m unittest discover -s tests -v`: 170 tests ran successfully, seven
  skipped (camera NumPy/OpenCV, opt-in isolated media integration, POSIX boot
  shell). Output: ignored `.runtime/section-two-python-tests.log`.
- `docker compose config --quiet`: passed.
- `openspec validate optimize-maixcam-cpu-and-video-transport`: passed.
- `git diff --check`: passed (existing Git line-ending warnings only).
- Apply instructions confirmed task 2.1 complete and progress 3/6.

An edit helper initially used the Windows default text encoding when reading
frontend tests and failed before changing that file. Retried with explicit
UTF-8; the resulting frontend build and checks passed.

## Runtime state and limits

Implemented; redeployment verification pending. The change plan reserves paired
live deployment for separate authorization. No services restarted, camera files
installed, local `.env` changed or saved recordings modified by this work.
Browser checks use mocked camera APIs, while FFmpeg checks use generated media.
Actual mounting orientation, sustained native video, headset listening, audible
Talk and new physical recording/playback remain unverified after deployment.
MP4 rotation needs a player that honors its display matrix. The previously
observed intermittent camera failure is unresolved by this section.
