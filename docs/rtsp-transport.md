# Configurable RTSP transport and measurement

## Current operation (2026-10-10)

The accepted mode is **TCP video-only**, with acceptable video and PC talkback
latency reported by the user. Earbuds → MaixCAM → PC microphone audio remains
unimplemented end to end. Preserve the working video/talkback paths.

The operator now runs natively on Windows because Docker's host-network page
worked inside the container but Windows could not reach localhost 8000/8889,
including after Desktop restart and container recreation. Stop the operator
container before a native startup:

```powershell
.\start_operator.ps1
```

The helper stops the Docker operator if running, reads `.env` camera/transport/
mode settings and verifies Windows HTTP access. It reuses a matching native
stack. Its PID/logs are in `.runtime/operator-native.*`. Direct `python app.py`
does not load Compose's `.env`; pass explicit TCP/video flags for a manual run.
Keep `.env` set to TCP/video for any later Docker retest, and stop recording,
then run `.\stop_operator.ps1` before starting the operator container. Open
http://127.0.0.1:8000/operator_test.html. See the [README](../README.md#run-the-configured-stack)
and [session evidence](sessions/2026-10-10-rtsp-latency.md).

## Transport controls and experimental modes

The default remains UDP and combined video/audio. `RTSP_TRANSPORT=tcp|udp` (or
`app.py --rtsp-transport`) selects camera ingestion, PC headset RTSP ingestion,
combined publication, recording ingestion, and the local talkback decoder.
MediaMTX accepts both transports. WHEP/WHIP and browser ICE remain UDP; the
authenticated, sequenced TB2 talkback datagrams on camera port 9002 are unchanged.
No input buffering, codec, queue size or camera encoder defaults were tuned by
this change.

Before a TCP video or combined startup, the supervisor receives actual H.264
packets using explicit TCP. A failed check aborts before stopping the existing
stack. It does not silently claim TCP capability or silently change the selected
transport. Audio-only mode does not open the camera video source.

```powershell
python -m pc.check_camera_udp --transport tcp --maix-ip 192.168.1.7
python app.py --rtsp-transport tcp --stream-mode combined
python app.py --rtsp-transport udp --stream-mode combined
```

`--stream-mode video|audio|combined` (environment: `STREAM_MODE`) opens only the
requested inputs, maps the corresponding streams, and retains `/maix01` and
the existing browser endpoint. Recording maps match that mode too.

## Headset publication and Docker

The MaixCAM headset publisher must also use the requested upstream transport:

```sh
python3 /root/headset_mic_stream.py --target <PC-LAN-IP> --rtsp-transport tcp
```

Stop the previous microphone publisher before starting another capture process.
Do not change the fixed Bluetooth device or run two SCO capture processes at once.
Back up the installed file before deploying the updated publisher. This task's
measurements used a separate temporary device file and restored the original
direct RTP/UDP microphone command afterward.

Direct `--rtp-port` / `--headset-rtp-port` audio remains UDP. Combining it with
TCP audio mode is rejected rather than labeling a mixed test as fully TCP.
For the host-network Compose override, set `HEADSET_RTP_PORT=` in `.env` for
RTSP audio and `RTSP_TRANSPORT=tcp`; its default remains direct UDP port 8004.
An explicitly selected UDP/direct-RTP experiment uses `RTSP_TRANSPORT=udp`,
`HEADSET_RTP_PORT=8004` and the matching device `--rtp-port 8004` command.
These are historical experiment settings; do not restore them as routine cleanup
or replace the accepted TCP/video mode without a deliberate test plan.
The base Compose configuration uses RTSP microphone publication by default.

```powershell
docker compose config --quiet
docker compose -f compose.yaml -f compose.host.yaml config --quiet
```

`pc/run_publisher.ps1 -Transport tcp` also checks camera TCP capability first.
For a standalone `pc.operator_server`, supply `--rtsp-transport tcp` to select
the recorder and talkback decoder transport.

## Repeatable trials

The harness starts an isolated MediaMTX instance, uses the actual PC publisher
command, and decodes its output. It does not stop the production PC supervisor.
It reserves TCP 18554, UDP 19002/19003, WHEP HTTP 18889 and WebRTC UDP 18189.
The RTSP listener accepts camera microphone publication over the LAN; scope
firewall access to the test camera. Browser measurement uses local Chromium.
Use a new output directory for every invocation; results and raw logs belong
under ignored `.runtime/`.

```powershell
python -m pc.measure_transport --modes video --seconds 30 --repeats 2 --browser --debug-ts --conditions "Same AP/band, camera placement, encoder settings and background traffic" --output .runtime/video-comparison
```

For audio and combined tests, a matching MaixCAM microphone publisher must be
running. The isolated relay has a `/headsetmic` path:

```sh
python3 /root/headset_mic_stream.py --target <PC-LAN-IP> --rtsp-port 18554 --rtsp-transport tcp
```

```powershell
python -m pc.measure_transport --transports tcp --modes audio combined --audio-url rtsp://127.0.0.1:18554/headsetmic --seconds 30 --repeats 1 --browser --debug-ts --conditions "Record AP/band, placement, traffic and matching TCP microphone publisher" --output .runtime/tcp-audio-combined
```

Repeat with the microphone publisher and harness both set to UDP, then reverse
the order (UDP/TCP/TCP/UDP). Keep placement, encoder parameters, trial duration,
source stimulus and background load unchanged. Do not run extra camera readers
or unrelated builds during a measured trial. The harness reverses transport
order on alternating repeats, but it does not remotely reconfigure the camera
microphone; the operator must match its upstream transport for each audio batch.

Evidence includes:

- Separate publisher/decoder logs and explicit received-packet capability checks.
- Reported missing RTP packet counts, corrupt-frame/decode error events,
  reorder/queue warnings, non-monotonic timestamps, and optional demux/mux traces.
  With `--debug-ts`, supported FFmpeg builds also report processing latency
  (median/p95, separated by track). The scope labels are retained: video copy
  reports demux-to-mux; Opus audio can report only encode-to-mux. These exclude
  earlier stages, including camera delay, socket buffering and initial probing.
- Decoded frame counts, video PTS intervals, audio PTS gaps and zero-checksum
  audio frames. A PTS gap is a continuity diagnostic; silence alone does not
  identify an audible dropout or prove the headset captured real sound.
- Browser packet loss, decoded/dropped frames, freezes, concealed audio samples,
  and median/p95 of one-second interval-average jitter-buffer residence times.
  Those statistics describe the browser leg, not upstream Wi-Fi loss.
- Startup time to relay stream readiness and first A/V PTS offset. Neither is
  physical end-to-end latency or physical A/V synchronization.

Missing-packet warnings are observed counts, not a loss percentage. TCP can
retransmit packets without an RTP gap; absence of those warnings is not proof
that Wi-Fi had no loss. FFmpeg warnings do not expose queue occupancy, and
multiple decoder errors can refer to the same damaged frame.

## Physical stopwatch measurements and delay isolation

The available setup films the PC stopwatch and displays its delayed image in
Edge. Both readings must come from one desktop capture. The Windows OCR adapter
was tried, but did not reliably recognize these digits; use saved captures and
manual transcription rather than guessed OCR readings.

```powershell
python -m pc.measure_video_latency --transport udp --stage browser-video --reference-roi 2330,1370,620,120 --feed-roi 2390,130,240,65 --samples 20 --interval 5 --capture-only --output .runtime/stopwatch-udp
```

These ROIs match the tested 3000x1920 desktop layout only. Recalibrate them if
windows move. Keep the original stopwatch and camera image visible, prevent
sleep, and avoid covering the camera. Let playback stabilize before sampling.
Read each saved reference/feed pair; enter clear `HH:MM:SS.hh` values in
`readings.csv` and remove unreadable or startup/reconnection rows. Keep an
exclusion record with image numbers; target at least 20 **accepted** samples
per mode and transport, collecting additional captures when needed.

```powershell
python -m pc.measure_video_latency --transport udp --stage browser-video --manual-csv .runtime/stopwatch-udp/readings.csv --output .runtime/stopwatch-udp-summary
```

Repeat identically with TCP, then reverse transport order. The result includes
median, nearest-rank p95, accepted readings and endpoint drift in ms/s. Hundredths
display precision is not measurement accuracy: screen refresh, exposure and
frame cadence add uncertainty. The short current pilot has fewer than 20 clear
samples per condition, so its p95 is provisional. OCR mode is available by
omitting `--capture-only`, but rejects unreadable/ambiguous values.

Arrival-versus-PTS tracing can compare delay growth at the camera and relay:

```powershell
python -m pc.measure_timing --url rtsp://192.168.1.7:8554/live --transport udp --seconds 60 --output .runtime/timing-camera
python -m pc.measure_timing --url rtsp://127.0.0.1:8554/maix01 --transport udp --seconds 60 --output .runtime/timing-relay
```

Run these sequentially. They measure relative timing drift, **not absolute
latency**; RTP timestamps do not provide a verified capture wall clock.
For absolute stage isolation, use the same physical timer with a documented
direct-camera player, relay RTSP player, then Edge. Do not add their separately
measured latencies together or treat FFmpeg processing traces as total latency.

Measure a visible timer/flash and audible click at the source with an independent
reference recording. Collect at least 20 repeated events per transport/mode and
report video delay, audio delay and signed audio-versus-video offset in ms.
Use the same camera placement and source stimulus for TCP and UDP.

Compare these observation points in sequence:

1. Direct camera video and direct headset audio at the PC: source encoding,
   capture and camera-to-PC transport.
2. Video-only and audio-only publisher output: FFmpeg ingestion and processing.
3. Combined publisher output: additional synchronization/interleaving delay.
4. MediaMTX RTSP output versus browser presentation: relay and WebRTC/player delay.

The earliest stage with the extra delay is the place to investigate. Keep
startup/keyframe waiting separate from steady-state delay. Camera RTP PTS and
browser `currentTime` are not wall-clock capture timestamps. A direct camera
decode also includes the chosen PC decoder's latency, so document the reference
player and its settings. Clock-based cross-device measurements require verified
clock synchronization; an independent reference recording avoids that assumption.

Measured event samples can be summarized using `--event-samples samples.json`:

```json
{
  "udp/video/end_to_end_ms": [210, 220, 215],
  "tcp/video/end_to_end_ms": [230, 225, 240],
  "tcp/combined/physical_av_offset_ms": [15, 10, 20]
}
```

These numbers are illustrative. Never substitute browser jitter-buffer averages,
stream readiness, or first PTS differences for source-to-screen latency. Until
physical event samples exist, the harness writes latency/sync as null.

Current measured results and limits are in [the measurement report](rtsp-measurements.md).
