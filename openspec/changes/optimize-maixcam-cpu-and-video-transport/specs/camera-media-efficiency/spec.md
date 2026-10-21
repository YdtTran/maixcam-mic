# Spec Delta

## Purpose

Reduces MaixCAM CPU, RAM, and flash I/O pressure while preserving full compatibility with the existing RTSP/MediaMTX/WebRTC/multistream-recording architecture by defaulting to hardware-bound C++ `768×432` RTSP streaming (`rtsp.Rtsp().bind_camera`) with an extensible Python fallback, PC-side zero-reencode orientation, in-process G.711 PCMU RTP/UDP headset return, and boot-time kernel/Wi-Fi tuning.

## ADDED Requirements

### Requirement: Hardware-bound C++ RTSP streaming with extensible Python pipeline fallback
The camera video publisher SHALL default to MaixPy's hardware-bound C++ RTSP server (`rtsp.Rtsp().bind_camera`) at `768×432` (`FMT_YVU420SP`, `20 fps` default) on `rtsp://0.0.0.0:8554/live` without loading OpenCV or NumPy, and SHALL support an opt-in Python pipeline mode (`CAMERA_PIPELINE=python-rtsp`) for workflows requiring custom per-frame Python/NPU processing.

#### Scenario: Default native-bind pipeline streams 768x432 H.264 without OpenCV or Python frame loops
- **WHEN** `maix/rtsp_av.py` starts with default settings (`CAMERA_PIPELINE=native-bind`)
- **THEN** it initializes `camera.Camera(768, 432, image.Format.FMT_YVU420SP, fps=20)`, binds it directly to `rtsp.Rtsp()`, starts serving `rtsp://0.0.0.0:8554/live`, and sleeps in the main loop without importing `cv2` or `numpy`

#### Scenario: Extensible python-rtsp pipeline remains selectable for custom frame processing
- **WHEN** `maix/rtsp_av.py` starts with `CAMERA_PIPELINE=python-rtsp` (or `--pipeline python-rtsp`)
- **THEN** it runs the Python `VideoServer` frame loop with zero-copy NAL scanning, pre-allocated rotation buffers, and blocking client queue waits

### Requirement: PC-side zero-reencode orientation with optional baseline camera offset
The PC operator server and recorders SHALL apply the manager's selected quarter-turn rotation (`0°`, `90°`, `180°`, `270°`) combined with any configured physical sensor mounting offset (`CAMERA_BASE_ROTATION=0|90|180|270`, default `0`) using the browser HTML5 `<canvas>` live renderer and MP4 display rotation matrix without re-encoding video on either the camera or the PC.

#### Scenario: Combined baseline and manager rotation preserves zero-reencode live and recorded display
- **WHEN** the camera streams unrotated `768×432` H.264 in `native-bind` mode and a manager rotation (or `CAMERA_BASE_ROTATION`) is active
- **THEN** the browser renders the oriented live stream on `<canvas>` and the recorder writes the effective rotation angle `(base_rotation + manager_rotation) % 360` into the MP4 display matrix without re-encoding H.264 slices

### Requirement: In-process G.711 PCMU RTP/UDP headset return streaming
When configured to send headset microphone audio to a direct UDP RTP port, the camera audio publisher SHALL encode 8 kHz signed 16-bit mono PCM frames into G.711 µ-law (RTP payload type 0) and transmit 172-byte RFC 3550 RTP/UDP datagrams directly in-process without spawning an external FFmpeg child process.

#### Scenario: Direct UDP headset return transmits RFC 3550 PCMU packets without FFmpeg
- **WHEN** the camera headset microphone publisher runs with `--rtp-port 8004`
- **THEN** it encodes each 20 ms (320-byte) S16LE capture frame (or silence during talkback pause) into a 12-byte RTP header plus 160-byte G.711 µ-law payload and sends the 172-byte UDP datagram directly to the target PC without starting `ffmpeg`

#### Scenario: RTSP audio mode retains FFmpeg publisher compatibility
- **WHEN** the camera headset microphone publisher runs without `--rtp-port` in explicit RTSP mode
- **THEN** it continues using the FFmpeg RTSP publisher command for `/headsetmic`

### Requirement: Boot-time kernel printk and Wi-Fi power-save tuning
The camera boot script SHALL quiet verbose kernel console logging and disable wireless power saving before starting background audio services so driver debug logs and 802.11 sleep intervals do not degrade streaming continuity.

#### Scenario: Camera boot quiets kernel printk churn and disables Wi-Fi power save
- **WHEN** `background_services.rc.local` starts on MaixCAM
- **THEN** it caps kernel console printk verbosity (`dmesg -n 4` / `/proc/sys/kernel/printk`) and disables `wlan0` power saving (`iw dev wlan0 set power_save off`) on a best-effort basis before launching background services
