# Manager rotation and original recording aspect — 2026-10-16

User requested a 90° counter-clockwise live view, manual manager rotation, and
recordings matching the streaming image without a square resolution.

## Evidence and changes

- Probed the current RTSP feed and three recent MP4 files: all encoded 640×480.
  No encoded square resolution was observed. The live player's `object-fit:
  cover` cropped the source to its container; the exact cause of the user's
  square playback observation is not established by the probes.
- Added Camera rotation below the physical live view: original, 90° clockwise,
  180°, and 90° counter-clockwise. Default is counter-clockwise (270° clockwise
  internally). Demo orientation is independent.
- Shared backend rotation persists atomically in ignored
  `recordings/.camera-view.json`, surviving Docker recreation. Recording status
  carries rotation for clients; the UI polls every ten seconds.
- Added GET/POST `/api/camera/view`, strict quarter-turn validation, and the
  existing same-origin control check. Active capture/finalization locks rotation
  in both API and UI. This retains the existing prototype login/API trust model.
- Live and playback use `contain`. Live quarter-turns swap element dimensions
  and resize with the player, including fullscreen, preserving the entire image.
- Both recorder modes preserve source H.264 slice bytes and 640×480 dimensions.
  Square pixels are explicit in H.264 metadata. MP4 display rotation records the
  selected orientation; 90° rotations display at 480×640. No video re-encoding,
  resizing or square cropping. Older files remain unchanged. External players
  must support MP4 display matrices to reproduce the orientation.
- FFmpeg capability detection uses the newer input display_rotation option or
  FFmpeg 5's output rotate metadata. Synthetic frame comparisons verified both
  installed versions; modern output metadata alone failed to write a matrix in
  the initial ignored local experiment, motivating compatibility handling.
- Updated README, architecture and recording guide. Camera source, hardware
  configuration and headset processes were not changed.

## Validation and deployment

- `python -m unittest discover -s tests -v`: 126 checks, five skips, successful.
- `npm test`: build/types and 24 source/compiled browser checks passed. Initial
  run found an older finalization mock missing the newly required rotation;
  corrected the mock and reran successfully.
- Browser coverage includes all rotations, two desktop viewports, fullscreen,
  persistence across reload, recording lock and unrotated demo switching.
- Real FFmpeg tests checked all four orientations against pixel-rotated decoded
  reference frames, unchanged encoded slice bytes, 640×480 storage, 1:1 sample
  aspect, 4:3 encoded display aspect, and four audio/video tracks. Ran on Windows
  FFmpeg and separately in the deployed Debian FFmpeg 5 image.
- Finalization lock regression passed separately after adding its assertions.
- `MULTISTREAM_INTEGRATION=1 python -m unittest tests.test_multistream_integration -v`:
  both isolated media checks passed, covering legacy playback, multistream
  reconnects/gaps, four tracks, copied H.264, decoding and mix clipping limits.
- Compose validation and whitespace checks passed (existing CRLF warnings).
- `deploy_pc.ps1 -Build`: rebuilt/recreated only the PC service; health and
  Windows HTTP checks passed after idle-recording preflight.
- Real Chromium received 640×480 live video with counter-clockwise CSS rotation.
  Inspected `.runtime/camera-rotation-live.png` and recorded frame: full image
  visible without square cropping; scene is gray with texture/noise, so this
  does not establish useful scene/image-quality acceptance.
- Created a 6.64-second hardware-path multistream acceptance sample:
  `20261016T040259Z_dac3003d.mp4`. API rotation change during capture returned
  409. Finalization completed without error; worker audio had 323 frames and
  operator input was absent (silence), as no Talk action was performed.
- ffprobe confirmed encoded 640×480, SAR 1:1, DAR 4:3 and MP4 matrix rotation
  90° counter-clockwise. Chromium playback reported 480×640, advanced time and
  `contain`; inspected `.runtime/camera-rotation-playback.png`.
- Initial playback automation used an incorrect button label and timed out
  after recording had finalized. Corrected the helper and verified the saved
  file with a separate playback-only run; no duplicate recording was needed.

## Runtime and limits

- Docker healthy, no active recording/finalization, last sample error null.
  Counter-clockwise selection was applied and verified. Further live interface
  rotation POSTs were observed during verification; preserved the manager's
  latest selection (original/0° at the inspected point).
- Headset API reported disconnected, although the independent microphone return
  delivered audio frames for the sample. Audible duplex was not tested and no
  Bluetooth recovery was attempted within this video-orientation change.
- No physical A/V synchronization, latency, prolonged operation or external
  player acceptance measurement. Raw screenshots/probes/helpers are in ignored
  `.runtime/`; the sample and orientation preference remain under `recordings/`.
