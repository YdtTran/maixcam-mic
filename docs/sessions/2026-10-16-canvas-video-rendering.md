# Canvas presentation for quarter-turn video — 2026-10-16

## Request and evidence

User confirmed that Edge shows black video in both streaming and the exact file
`20261016T044816Z_74cc3723.mp4`. At 0/180 degrees video works; refreshing did not
resolve it. After deployment of the earlier filter workaround, user reported
that entering Recordings caused 90-degree video to go black again. The filter
workaround was therefore insufficient and has been removed.

The exact file contains clear decoded frames and plays in isolated Edge tests.
This supports bypassing the native rotated-video presentation path, but does
not isolate the cause in the user's existing Edge session. Do not represent
isolated screenshot/decoder success as user acceptance.

## Changes

- `frontend/src/media.ts`: added `paintVideoFrames`, which draws decoded source
  pixels to a canvas at source resolution, rotates live quarter turns, and uses
  video-frame callbacks rather than creating another stream or decoder. Redraws
  on loaded data/resize/seek and cancels callbacks/listeners on cleanup. Older
  browsers without video-frame callbacks use animation-frame scheduling.
- `frontend/src/main.tsx`: 90/270-degree live views paint onto canvas while the
  same underlying video continues decoding. Each worker/reconnect gets the
  correct source binding. Navigating away and back mounts a fresh painter.
- Portrait playback also paints its already-oriented decoded frames on canvas.
  Added accessible play/pause, seek, mute/volume and fullscreen controls, since
  the source video is transparent. Landscape playback retains native controls.
- `frontend/src/style.css`: canvas fits the full picture; source video remains
  available for decoding/audio. Removed the unsuccessful brightness filter.
- Added two pixel-level Playwright regressions. The live test supplies changing
  decoded frames, checks exact rotated colors, records/stops and navigates away
  and back twice. The playback test adds a 90-degree MP4 matrix to the existing
  synthetic demo asset and verifies decoded pixels, pause/seek/volume/fullscreen.
  No private recording fixture or extra media test dependency added.
- Updated the frontend guide. Existing unrelated edits preserved.

No camera, relay, Bluetooth, recorder or recording file modifications. This
does not enable rotation while capturing/finalizing. No video re-encoding.

## Verification, failures and deployment

- Build/type check passed. Four new source/compiled regression checks passed;
  final full browser suite: **30 passed**. Targeted diff whitespace check passed.
- During development, tests found a duplicate React sibling key in the new
  picture binding and a seek slider input issue; both corrected. Test mocks were
  updated to provide actual media frames and valid HTTP range responses. Early
  non-seekable MediaRecorder fixture was replaced with the existing finite MP4.
- `./deploy_pc.ps1 -Build`: recording-idle preflight passed, Docker rebuilt and
  recreated healthy, Windows operator HTTP verified.
- `.runtime/verify-canvas-rotation.mjs`: installed Edge against the deployed UI.
  Clear live canvas at 90 degrees, then successful new recording
  `20261016T050824Z_400501c5.mp4` (eight-second capture). Post-stop live remained
  clear. Playback checked the exact user file twice and this new recording once;
  sought to 1.5 seconds, exercised fullscreen and returned to live each time.
- All three return-to-live cycles produced a 432x768 canvas with nonzero camera
  pixels. Exact-file playback mean RGB was 117.66/255; new-file playback 127.37.
  Fullscreen playback and final live screenshots visually inspected; actual
  scene visible. Evidence remains in ignored `.runtime/canvas-*.png`.
- An earlier three-second diagnostic capture
  `20261016T050724Z_4f2bc14c` had only a 514-byte video staging file and failed
  MP4 muxing. Retained capture/logs for recovery/inspection. No video frames are
  available in that staging file. A relationship to startup/keyframe timing is
  plausible but not proven; do not describe this failed attempt as a successful
  recording. Longer retry finalized without error.
- The original user file's SHA-256 remains
  `20c4fb96d63ab1419966319752bf4e32da45cf78a02f5a45f6d7f609d84feb37`.
- Final API: recording false, finalizing false, rotation 90, error null. Camera
  processes unchanged. No physical latency or audio acceptance test.

User asked to hard-refresh Edge, open this exact recording, and return to the
90-degree live view. Acceptance in the affected Edge session is pending.

## Continuation: inspected and recovered the actual Edge session

User reported both views still black and emphasized recordings are dynamic files
under `./recordings/`. Clarified that no code targets the diagnostic filename:
the renderer applies to all quarter-turn live views and portrait recordings.

Applied the self-debug workflow: stopped speculative rendering changes and
checked the discrepancy between isolated tests and the actual user session.
The server HTML matched the current local build and contained the canvas player
and portrait controls. Recent request logs showed recording requests but no new
HTML page request from the user's session. This suggested an old loaded page;
it was a hypothesis until the actual window could be inspected.

Initial Windows Computer Use capture was stopped because it could not verify
the current browser URL. On the user's explicit continuation, requested the URL;
user confirmed `http://127.0.0.1:8000/operator_test.html`. Native Computer Use via
`node_repl` and `@oai/sky` then successfully inspected the actual existing Edge
window, rather than another isolated browser profile. Some input attempts were
rejected due to intervening user input; refreshed state before retrying.

Observed in the actual window:

- At 0 degrees, the original landscape video was visible. Selecting 90 before
  reload did not expose the canvas picture in the accessibility tree.
- Issued Ctrl+Shift+R in that Edge window at approximately 12:13:38 local.
  Server logged a new `GET /operator_test.html` returning 200. After reload,
  the 90-degree view exposed `Video picture` and visibly displayed the scene.
- Opened Recordings and selected the exact row for
  `20261016T044816Z_74cc3723.mp4`. The portrait scene was visible in the actual
  dialog, and successive observations showed different recorded frames.
- Closed the dialog and selected Live Workers. After normal WebRTC connection
  startup, the 90-degree canvas picture was visible again with Online/UDP state.
- Final API: recording false, finalizing false, rotation 90, error null.

The current player is now visually verified in the user's existing Edge session,
including the reported navigation trigger. The continued black-screen reports
were consistent with the older loaded page; why earlier requested refreshes did
not replace it was not established. The original native-video rendering failure
is still not isolated to a specific GPU/driver/browser defect. No additional
source edits, rebuilds, camera changes or MP4 changes in this continuation;
only session-memory documentation updated. User window left on clear live video
at 90 degrees, idle. This is agent-observed visual verification, not a separate
explicit user acceptance statement.
