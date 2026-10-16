# Camera-side pixel rotation — 2026-10-16

User clarified that Original must already be 90° counter-clockwise and explicitly
selected **Rotate video pixels on MaixCAM**. Preserve what the camera captures,
as when rotating a phone. This supersedes the browser-only baseline in the
[earlier rotation session](2026-10-16-manager-rotation-recording.md).

## Final implementation

- Keep one original 640×480 NV21 camera capture. Rotate every luma pixel and
  every VU chroma pair 90° CCW, without resampling or changing the capture area.
  OpenCV's native plane rotation materializes contiguous arrays; NumPy's strided
  `tobytes` was too slow on this RISC-V camera.
- The installed Maix RTSP implementation cannot accept supplied frames: its
  `write()` raises Not Implemented. Added `maix/video_rtsp.py` to serve hardware
  encoded H.264 at the same TCP-interleaved RTSP `/live` endpoint. Single hardware
  encode; bounded two-frame reader queues; SPS/PPS, IDR gating, FU-A packets,
  RTCP reports, keepalive and reconnect support. It is TCP-only.
- Controlled saved-frame experiments showed copied 480-wide encoder input
  corrupts the picture, whereas aligned 512-wide input encodes correctly. Pad
  only the hardware input to 512×640, then set Main/Baseline SPS display bounds
  to exclude the 32 non-picture columns. No captured pixel is cropped. The
  resulting decoded source is exactly 480×640. Slice NALs are unchanged by the
  SPS adjustment.
- Added module to camera installation/backups. Both `/root/rtsp_av.py` and the
  boot app at `/maixapp/apps/maix_rtsp/main.py` contain the final program, importing
  `/root/video_rtsp.py`. Prior video backups are under
  `/root/workercam-pixel-rotation-backup-20261016T041646/`.
- Manager Original is now zero additional rotation; manual controls and MP4
  display rotation are relative to the already rotated camera stream. Reset
  saved manager preference to zero for the new baseline. PC copies the visible
  480×640 source into recordings; no square resize or PC video encoding.

## Failures and recovery

- Initial software rotation had correct raw pixels but green/striped encoded
  output. The copied-input alignment experiment isolated the repair above.
  Earlier green test files remain local; the accepted final sample is below.
- During investigation, SSH accepted TCP but sent no greeting on USB and Wi-Fi;
  the PC lost video. No causal link was proven. User power-cycled the camera
  and reported successful reconnection. Access then recovered. No repeated
  reset was attempted. Temporary probing used one video process at a time.
- An initial shell upload suffered CRLF handling; subsequent uploads used
  base64/Python writes. No credentials were printed.
- Initial playback automation chose an older green test file while the new file
  finalized. Corrected selection to the exact new recording id, then visually
  verified its playback separately.

## Verification

- Exact 4×2 luma/chroma rotation test passed on MaixCAM. Saved full-resolution
  original and rotated raw frames were inspected; all camera content is retained.
- Hardware encoder experiments compared original, 480-wide and padded frames.
  Padded output showed the correct scene. ffprobe after SPS adjustment reports
  480×640. Tests compare decoded adjusted SPS output byte-for-byte with the
  same decoded hardware-width fixture excluding only the padding.
- Python suite: 129 checks, six skips (including local NumPy absence); passed.
  Updated RTSP/SPS checks passed separately after the final alignment repair.
- Frontend build/types and 24 source/compiled browser checks passed.
- Real RTSP/TCP fixture tests verify fragmentation reassembly, visible dimensions,
  exact decoded pixels after padding removal, decoding and reconnects.
- Docker rebuilt/recreated healthy through `deploy_pc.ps1 -Build`. Camera's final
  video process was started directly without another reboot after the alignment
  repair; boot files also contain the final code. One production video process
  (PID1239 at inspection), connector, talkback receiver and microphone sender.
- Real Chromium live view: 480×640, `contain`, identity rotation matrix, Original
  selected. Clear lab scene visually verified in `.runtime/camera-pixel-rotation-live.png`.
- Final camera-path recording `20261016T043140Z_21df1dd2.mp4`: 480×640, SAR1:1,
  no display rotation side data at Original, 69 decoded frames in the short sample.
  Exact-file Chromium playback advanced time and displayed the clear scene at
  480×640; `.runtime/camera-pixel-final-playback.png` inspected. Finalization
  completed without error. Rotation API rejects changes during capture with409.
- Short final captures measured roughly12–13fps; an intermediate native-rotation
  trial measured about20fps. This is lower than the nominal30fps encoder setting.
  No physical latency measurement or long stability/boot acceptance was done.
- Headset API reported disconnected and `/headsetmic` unavailable after the
  restart. Final sample audio tracks contain silence; no Talk action or audible
  acceptance trial performed. Bluetooth code/settings were not changed.
- Raw captures, downloaded SDK evidence, probes and screenshots stay in ignored
  `.runtime/`; recordings and the saved manager preference stay untracked.
