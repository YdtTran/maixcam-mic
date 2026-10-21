# Camera pipeline efficiency: section 1, 2026-10-21

## Request and scope

The user corrected the selected change to
`optimize-maixcam-cpu-and-video-transport` and requested only section 1
(tasks 1.1 and 1.2). Preserve the extensive pre-existing working-tree edits.
Tasks 2–4 and the separately gated deployment follow-up remain outside this run.

## Implementation

- `maix/rtsp_av.py` defaults to hardware-bound native RTSP on port 8554, using
  a 768x432 NV21 camera and server at 20fps. It checks bind/start errors,
  sleeps instead of reading frames in Python, and stops the server on exit.
  Native startup imports neither `video_rtsp`, OpenCV nor NumPy.
- `CAMERA_PIPELINE=python-rtsp` in the process environment or
  `--pipeline python-rtsp` selects the existing 432x768-to-768x432 CCW fallback.
  The CLI takes precedence. Its optional `frame_hook(image)` returns the image
  for rotation/encoding. It allocates one rotation destination for the loop.
- `maix/video_rtsp.py` scans Annex B prefixes with `bytes.find` and returns
  memoryviews. SPS/PPS are copied separately to avoid retaining full frames.
  Legacy SPS cropping still accepts those views. OpenCV writes Y and VU planes
  into the reusable destination; the encoder receives one contiguous bytes copy.
  Playing clients use `frames.get(timeout=0.2)` and nonblocking socket readiness
  checks; control-only clients wait up to 0.2 seconds for socket activity.
- Added startup/error cleanup, pipeline selection/hook, buffer reuse, NAL view,
  and queue-wait/control handling tests in `tests/test_camera_rotation.py`.

Vendor RTSP constructor, bind/start/stop return values checked against
[MaixPy API](https://wiki.sipeed.com/maixpy/api/maix/rtsp.html).

## Verification

- `python -m unittest tests.test_camera_rotation tests.test_rtsp_transport tests.test_app -v`:
  39 tests, successful, two environment skips for missing NumPy/OpenCV.
  Includes real local FFmpeg RTSP decode and reconnect checks.
- `openspec validate optimize-maixcam-cpu-and-video-transport --strict`: passed.
- Scoped `git diff --check`: passed.
- Attempted test-only NumPy/OpenCV installation under ignored
  `.runtime/camera-rotation-test-deps`; the OpenCV download stalled without
  transferring payload and was cancelled. Pixel rotation and destination reuse
  checks remain environment-skipped; no project dependency was added.

OpenSpec apply instructions confirmed tasks 1.1 and 1.2 checked, with progress
2/6. The four remaining tasks are intentionally pending under the user's scope.

The initial fallback startup test used a mock that did not return encoded bytes;
corrected that fixture and reran successfully.

## Runtime state and limits

No services restarted, camera files installed, or recordings changed. This is
implemented; redeployment verification pending. Native mode intentionally omits
the previous camera-side pixel rotation; the PC mounting-offset work in task 2
is not included. CPU/RAM savings, actual native `/live` continuity, physical
orientation, audio, Talk and recording acceptance have not been measured in
this run. Existing live state and the earlier intermittent camera failure remain
unverified. Frontend/full-suite/Compose checks in task 4 were not performed.
