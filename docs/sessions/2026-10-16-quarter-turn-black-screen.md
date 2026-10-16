# Quarter-turn black-screen investigation — 2026-10-16

User reports black 90-degree recording playback and video disappearing after
recording finishes. Clarified that Edge is affected, Ctrl+F5 does not resolve it,
and 0/180 degrees still work. Treat this report as unresolved; automated success
does not establish that the user's session works.

## Evidence

- Compared recent files `20261016T044758Z_e2615e92` (0 degrees) and
  `20261016T044816Z_74cc3723` (90 degrees), including JSON and FFmpeg logs.
- ffprobe on the 90-degree file: H.264 Main, stored 768x432, SAR 1:1,
  display matrix 90 degrees, 115 video frames; video starts at 0.966 seconds.
- FFmpeg decoded a clear full portrait frame, visually inspected. Its grayscale
  mean at two seconds is 117.5/255. No extended black segment was reported by
  blackdetect; null-output frame-rate conversion logged duplicate DTS warnings.
- Direct browser playback of both exact files succeeded in isolated Chromium.
  Canvas readback had nonzero picture means; video dimensions were 768x432 and
  432x768 respectively, playback advancing past two seconds without media errors.
- Opened each exact file through the deployed app's Recordings page and dialog
  in both Chromium and installed Edge. Also repeated with separate headed test
  browser windows positioned offscreen. All showed advancing frames; screenshots
  of portrait playback were visually inspected and contain the actual scene.
- Created one short real recording through the app at 90 degrees:
  `20261016T045115Z_58d39f11.mp4`, duration 3.94 seconds. Video dimensions and
  rendered bounds remained nonzero before/during/after capture and after returning
  from recordings to live. Video frames advanced throughout. Recording playback
  passed and the saved file has clear decoded frames.
- Python Playwright is unavailable locally; used the repository's installed Node
  Playwright packages. CUA inventory had no connected apps or browsers, so the
  user's existing Edge session could not be inspected.

## State and next evidence

No source changes, camera changes or service restarts in this investigation.
Docker healthy; recording/finalizing false, error null, rotation 90 at final
check. Existing recordings retained, including the new diagnostic sample.
Scripts, frame snapshots and browser captures remain ignored under `.runtime/`:
`check-recording*.mjs`, `check-record-cycle.mjs`, `record-cycle-*.png` and
`20261016T044816Z_74cc3723-*-ui.png`.

The exact failing filename or the failing browser session is needed to distinguish
a specific asset failure from a session/rendering issue. A GPU/overlay issue is
only a hypothesis; isolated Edge playback succeeded and no workaround has been
applied or represented as a fix. No audio acceptance or physical latency tests.

## Follow-up: exact file confirmed and rendering workaround deployed

User explicitly identified `20261016T044816Z_74cc3723.mp4` and confirmed both
live streaming and recording playback are black at 90 degrees in their Edge
session. The exact file was already included in successful decode/playback
checks above. The earlier request for a filename is now resolved.

Applied a limited compatibility workaround in `frontend/src/style.css`:
`filter: brightness(1.00001)` on 90/270-degree live video and the recording
player. The slight non-identity color filter requests compositing of the video
rather than relying on a direct rotated video overlay. Its maximum gain is
below one 8-bit color step. Live 0/180-degree rendering remains unfiltered.
Native playback controls and media transport are preserved; there is no video
re-encoding or recording-file mutation. This targets a suspected display path;
the exact failure in the user's session remains unproven and requires their
acceptance check. Successful automated frame readback/screenshots do not prove
that a separate session's hardware overlay works.

Validation and runtime:

- `npm test`: build/type checks and all 26 source/compiled browser checks passed.
- `git diff --check -- frontend/src/style.css`: passed.
- `./deploy_pc.ps1 -Build`: preflight idle, PC rebuilt/recreated healthy and
  Windows HTTP verification passed. Camera not changed or restarted.
- `.runtime/verify-rotation-filter.mjs`: installed Edge against the deployed UI
  passed six live selections (90/0/90/180/270/90), with advancing frames and
  nonzero player bounds at every step. Expected filter active at quarter turns.
- Opened the exact user file through its recording row: 432x768 display,
  playback past two seconds, 23 video frames, canvas mean RGB 117.19/255,
  no media error. Filter present. Closed playback and returned to live at 90;
  frames advanced again. Screenshots in `.runtime/rotation-filter-*.png`.
- Original file retained; SHA-256
  `20c4fb96d63ab1419966319752bf4e32da45cf78a02f5a45f6d7f609d84feb37`.
- User asked to hard-refresh Edge and verify live plus this exact recording.
  Do not mark the black-screen report resolved until their check succeeds.
- Final API after the automated check: recording false, error null, rotation 0;
  selection changed after the test ended and was left as observed.
