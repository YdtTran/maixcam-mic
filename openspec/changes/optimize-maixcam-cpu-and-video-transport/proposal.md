# Proposal

## Why

Live hardware benchmarks on MaixCAM (`10.172.16.1`) at `768×432` isolated why the current runtime saturates the single-core 1 GHz RISC-V CPU (**99% busy, `0%–1% idle`, `10%–28% io` disk thrashing, `134 MB VSZ`**):
1. **OpenCV/NumPy RAM exhaustion + Python frame loop (`maix_rtsp/main.py` = 53%–81% CPU, 134 MB VSZ, 28% I/O wait):** Importing `cv2` and `numpy` for per-frame software `rotate_nv21` adds +37 MB of shared libraries/buffers (`97 MB → 134 MB VSZ`). Combined with the 33 MB `ffmpeg` audio process, this exceeds MaixCAM's 128 MB physical RAM, forcing Linux to thrash flash storage (`28% io` wait) on every frame while executing software rotation and Python RTP packetization.
2. **Native C++ `rtsp.Rtsp().bind_camera(cam)` at `768×432, 20 fps` uses only 9%–23% CPU (`58%–63% idle`, `0% io`, `97 MB VSZ`):** Live testing on the same camera confirmed that binding the `768×432` (`FMT_YVU420SP`) camera directly to MaixPy's hardware C++ RTSP server (`server.bind_camera(cam)`) streams H.264 to the existing PC container (`192.168.1.4`) over `/live` with **zero Python frame loop**, **zero flash I/O wait**, **37 MB less RAM**, and **~60% free CPU headroom** for future extensions (such as on-device NPU/AI tasks).
3. **Redundant 33 MB `ffmpeg` child process in `headset_mic_stream.py` (`25% VSZ`, `3% CPU`):** Spawning `ffmpeg` solely to convert 20 ms (320-byte) 8 kHz S16LE PCM frames into 160-byte G.711 µ-law payloads with a 12-byte RTP header wastes 25% of camera RAM when Python can send the exact same 172-byte RFC 3550 PCMU UDP datagrams in-process.
4. **Kernel printk log churn (`klogd` + `syslogd` = 6% CPU):** Verbose AIC8800 Wi-Fi/BT SDIO driver messages consume 6% CPU in syslog daemons.

## What Changes

- **Switch `maix/rtsp_av.py` default pipeline to hardware-bound C++ `rtsp.Rtsp().bind_camera(cam)` (`768×432`, `FMT_YVU420SP`, `20 fps`) with pluggable Python fallback (`CAMERA_PIPELINE=native-bind|python-rtsp`)**:
  - In default `native-bind` mode, `maix/rtsp_av.py` binds `camera.Camera(768, 432, image.Format.FMT_YVU420SP, fps=20)` directly to `rtsp.Rtsp()` on `rtsp://0.0.0.0:8554/live` without importing `cv2`, `numpy`, or `video_rtsp`, dropping video process usage to ~9%–23% CPU (`~60% idle`, `0% io`, `97 MB VSZ`) while keeping the exact same `/live` RTSP contract with the PC.
  - Retain `CAMERA_PIPELINE=python-rtsp` (with optimized zero-copy NAL scanning, pre-allocated rotation buffers, and blocking client queue waits in `maix/video_rtsp.py`) as an extensible fallback for future workflows that need custom per-frame Python/NPU inspection.
- **Extend PC orientation handling with a configurable baseline camera mounting offset (`CAMERA_BASE_ROTATION=0|90|180|270` in `app.py` / `pc/operator_server.py`)**:
  - Because the PC browser already renders quarter-turn video on an HTML5 `<canvas>` (`frontend/src/media.ts`) and the PC recorder (`pc/recording.py`, `pc/multistream_recorder.py`) writes zero-reencode MP4 rotation matrices, the PC handles all 0°/90°/180°/270° orientation (including an optional baseline sensor-mount offset) with zero CPU/RAM cost on the MaixCAM.
- **Replace the 33 MB `ffmpeg` subprocess in `maix/headset_mic_stream.py` (`--rtp-port 8004`) with an in-process RFC 3550 G.711 PCMU UDP sender**:
  - Encode 20 ms 8 kHz S16LE PCM frames to G.711 µ-law (`payload type 0`) and send 172-byte RTP/UDP packets directly via a Python UDP socket, preserving the exact wire protocol expected by the PC's UDP 8004 receiver while freeing 33 MB VSZ on MaixCAM. Retain `ffmpeg` only for explicit RTSP audio mode.
- **Quiet kernel driver log churn and disable Wi-Fi power-save in `maix/background_services.rc.local`**:
  - Set `dmesg -n 4` (or `/proc/sys/kernel/printk`) to stop `klogd`/`syslogd` from burning 6% CPU on AIC8800 SDIO debug logs, and disable `wlan0` power saving (`iw dev wlan0 set power_save off`).

## Capabilities

### New Capabilities
- `camera-media-efficiency`: Hardware-bound `768×432` C++ RTSP camera streaming with extensible Python fallback, PC-side zero-reencode orientation, in-process G.711 PCMU RTP/UDP headset return, and boot-time kernel/Wi-Fi tuning.

### Modified Capabilities

## Impact

- **Camera runtime (`maix/rtsp_av.py`, `maix/video_rtsp.py`, `maix/headset_mic_stream.py`, `maix/background_services.rc.local`)**: Frees ~70 MB of virtual memory (`37 MB` from removing `cv2`/`numpy` in `native-bind` mode + `33 MB` from removing `ffmpeg` in UDP 8004 mode), eliminates the 28% flash I/O thrashing, and increases MaixCAM idle CPU from ~1% to ~60%.
- **PC runtime (`app.py`, `pc/operator_server.py`, `compose.yaml`)**: Keeps the exact same RTSP `/live` pull, MediaMTX `/maix01` and `/headsetmic` paths, WHEP/WHIP endpoints, TB3 talkback (`UDP 9002`), and multistream MP4 recording pipeline.
- **Tests (`tests/test_camera_rotation.py`, `tests/test_headset_return.py`, `tests/test_video_orientation.py`)**: Unit tests for `native-bind` and `python-rtsp` pipeline modes, in-process G.711 PCMU RTP/UDP packetization, and PC orientation handling.
