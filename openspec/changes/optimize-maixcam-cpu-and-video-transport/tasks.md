# Tasks

## 1. Extensible hardware-bound C++ RTSP camera pipeline and Python fallback optimization

- [x] 1.1 Update `maix/rtsp_av.py` to default to `CAMERA_PIPELINE=native-bind` (`camera.Camera(768, 432, image.Format.FMT_YVU420SP, fps=20)` bound directly to `rtsp.Rtsp()` on `/live` without importing `cv2` or `numpy`) while preserving `CAMERA_PIPELINE=python-rtsp` (and an optional `frame_hook` extension point) for custom Python/NPU workflows; verify unit tests in `tests/test_camera_rotation.py` cover both `native-bind` and `python-rtsp` startup paths.
- [x] 1.2 Optimize `maix/video_rtsp.py` for the `python-rtsp` fallback path by replacing regex `re.split` in `split_nals()` with zero-copy `bytes.find` scanning, reusing pre-allocated destination buffers in `rotate_nv21()`, and replacing the 100 Hz `select.select(..., 0.01)` spin loop in `VideoClient.handle()` with blocking `self.frames.get(timeout=0.2)` queue waits; verify unit tests in `tests/test_camera_rotation.py` pass.

## 2. PC-side zero-reencode orientation with optional baseline camera offset

- [x] 2.1 Add `CAMERA_BASE_ROTATION` (`0`, `90`, `180`, `270`, default `0`) to `app.py` and `pc/operator_server.py` so the PC combines any physical camera mounting offset with the manager's selected rotation `(base_rotation + manager_rotation) % 360` for live `<canvas>` display and zero-reencode MP4 recording, and update `docs/rtsp-transport.md` and `docs/architecture.md`; verify `python -m unittest tests.test_video_orientation tests.test_app -v` passes.

## 3. In-process G.711 PCMU RTP/UDP headset return and boot-time kernel/Wi-Fi tuning

- [x] 3.1 Update `maix/headset_mic_stream.py` to implement an in-process RFC 3550 G.711 µ-law (`PCMU`, payload type `0`) UDP packet sender when `--rtp-port` is configured (eliminating the 33 MB `ffmpeg` child process in direct UDP 8004 mode while retaining `ffmpeg` for explicit RTSP audio mode); verify unit tests in `tests/test_headset_return.py` confirm exact 172-byte RTP/UDP headers, monotonic sequence/timestamp increments, µ-law encoding, and zero `ffmpeg` subprocess spawns in `--rtp-port` mode.
- [x] 3.2 Update `maix/background_services.rc.local` to cap kernel console printk verbosity (`dmesg -n 4` / `/proc/sys/kernel/printk`) and disable `wlan0` power save (`iw dev wlan0 set power_save off`) on a best-effort basis before starting background services, and document the in-process UDP sender and boot tuning in `docs/headset-return-audio.md`; verify `python -m unittest tests.test_headset_return tests.test_start_scripts -v` passes.

## 4. End-to-end automated regression check

- [x] 4.1 Run `python -m unittest discover -s tests -v`, `npm test --prefix frontend`, and `docker compose config --quiet`; verify all checks pass with zero regressions.

## Workflow follow-up

- When authorized by the user, deploy both PC and MaixCAM via `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts/deploy.ps1 -UsbInterfaceIndex 17 -UsbPeerIP 10.172.16.1 -Force`.
- Capture MaixCAM `top -b -n 2 -d 1` and verify `native-bind` video streaming (~55%–65% idle CPU, `0% io` wait, `97 MB VSZ`), absence of the `ffmpeg` child process under `headset_mic_stream.py`, sustained 60-second browser video continuity, working UDP 8004 headset return, TB3 talkback, 0°/90° rotation, and multistream recording/playback.
- Record live verification evidence in `docs/sessions/` and `AGENTS.md`, then archive the completed OpenSpec changes.
