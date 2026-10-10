# RTSP transport diagnostic results — 2026-10-10

TCP/UDP selection and independent video/audio/combined modes are implemented.
The installed MaixCAM server delivered actual H.264 packets with explicit
TCP-interleaved transport. UDP combined operation was restored temporarily
during the investigation; the user subsequently chose **TCP video-only**.
WHEP viewing, WHIP talkback and
authenticated sequenced TB2 UDP packets remain the same architecture.

The latest operator runtime is native Windows after Docker Desktop localhost
access failed, including after restart. HTTP 200, camera TCP packets, H.264
publication and talkback API availability were checked after this workaround;
browser playback and audible talkback were not physically retested. The user
reports acceptable video and PC talkback latency. Earbuds → MaixCAM → PC audio
remains unimplemented end to end. These updates do not change the historical
latency samples below. See the [session log](sessions/2026-10-10-rtsp-latency.md)
and [current startup instructions](../README.md#run-the-configured-stack).

## Physical source-to-Edge video latency

FFmpeg captured the original stopwatch and delayed camera image in the same
desktop screenshot. Windows OCR did not reliably read the stopwatch, so clear
saved images were transcribed manually. Startup/reconnection, hand occlusion and
ambiguous hundredths were excluded. Each run captured 20 images at 5-second
intervals. Median and nearest-rank p95 use only accepted readings.

| Condition | Accepted / captured | Median | p95 | Endpoint delay growth |
|---|---:|---:|---:|---:|
| UDP combined, recovered baseline | 13 / 20 | 1,710 ms | 1,980 ms | +5.26 ms/s |
| UDP video only, rebuilt PC stack | 12 / 20 | 175 ms | 200 ms | −0.12 ms/s |
| TCP video only, same rebuilt stack | 7 / 20 | 230 ms | 240 ms | −0.13 ms/s |

UDP video exclusions: images 0–1 (startup/reconnection), 3–4 and 8–9 (ambiguous
digits), 14–15 (occlusion). TCP accepted images: 3, 4, 5, 8, 14, 17, 18; other
images show missing playback or ambiguous digits. Baseline accepted images:
0, 4, 5, 6, 7, 9, 10, 12, 14, 15, 16, 18, 19.

The hundredths display does not guarantee 10 ms measurement accuracy. Camera
exposure, frame cadence and display refresh matter. These are small pilot
samples, particularly TCP; p95 is provisional. Collect at least 20 clear samples
per condition and repeat with reversed order before choosing a default.
The video-only comparison used the same Docker image and unchanged buffering
and codec flags. Camera placement and AP were retained; Wi-Fi load was ambient,
not controlled or measured. The combined baseline preceded the image rebuild,
so the mode comparison is suggestive rather than a fully controlled A/B test.

The user's original 10,230 ms observation is recorded as a user-reported sample.
The user also observed intervals with much lower video and audio delay during
scenario changes, shortly before the final scenario. The user subsequently
matched this interval to 18:38–18:40, the TCP video-only run. The lower video
delay agrees with its physical measurements; the audio observation cannot be
attributed to that publisher because it excluded headset audio.
Restart-related buffer clearing and combined-stream timing must
be considered alongside transport choice. The final dashboard sequence was
UDP video only (approximately 18:35–18:37 local time), TCP video only
(18:38–18:40), then restored UDP combined. The video-only stages did not include
headset audio, so they cannot explain a confirmed simultaneous low audio delay.
The original 10,230 ms delay was not reproduced in these steady-state trials.
TCP did not reduce physical
video latency in this short comparison. Removing the audio input coincided with
much lower video delay; this warrants investigating input timing and combined
stream synchronization before changing architecture.

Evidence is retained locally under `.runtime/physical-udp-baseline`,
`.runtime/physical-udp-video`, `.runtime/physical-tcp-video`, and their
`*-summary/latency.json` files. Accepted CSVs retain readings and elapsed times.
The final restored-mode snapshots were excluded because the desktop/camera
layout changed. Edge playback was visually verified after restoration. An
additional headless receiver of the production stack failed the received-media
check; its empty result is not a successful browser measurement.

## Where delay grows

Sequential 30-second UDP traces used the same FFmpeg decoder settings:

| Observation point | Decoded frames | Arrival-minus-PTS endpoint drift |
|---|---:|---:|
| Direct camera `/live` | 823 | −0.91 ms/s |
| Combined MediaMTX `/maix01` | 859 | +4.80 ms/s |

These measure relative delay growth, **not absolute stage latency**. They
support investigating the PC combined path: growth is already present at relay
RTSP output, before browser playback. They do not separate FFmpeg ingestion,
interleaving and MediaMTX, or establish camera capture-to-packet delay.
Evidence: `.runtime/timing-camera-udp/timing.json` and
`.runtime/timing-relay-udp/timing.json`. Endpoint slopes are sensitive to short
bursts; longer repeated traces and physical direct/relay/player measurements
are needed for firm attribution.

## Independent streaming pilots

Trials requested 15 seconds per mode in UDP/TCP/TCP/UDP order, using an isolated
relay and matching camera microphone RTSP transport. Same AP, placement and
encoder defaults; no intentional packet impairment. Complete video/audio/
combined results exist for the first three batches. The fourth UDP video's
source stalled after approximately 106 publisher frames; exclude it from
equivalent video comparisons. Fourth UDP audio completed; combined failed the
camera packet check. The camera subsequently reported native capture/resource
errors during restart and required reboot. This failure does not establish a
TCP/UDP cause; earlier failed fixture/setup attempts are also excluded.

| Complete trial | Publisher missing RTP packets | Decoder corrupt-frame events | Publisher / decoder queue warnings | Audio PTS gaps >2 ms |
|---|---:|---:|---:|---:|
| UDP video | 0 | 1 | 0 / 0 | — |
| UDP audio | 0 | 0 | 0 / 0 | 0 |
| UDP combined | 8 | 3 | 3 / 2 | 7 |
| TCP video, batch 2 / 3 | 0 / 0 | 0 / 0 | 0 / 0 in both | — |
| TCP audio, batch 2 / 3 | 0 / 0 | 0 / 0 | 0 / 0 in both | 0 / 0 |
| TCP combined, batch 2 / 3 | 0 / 0 | 0 / 0 | 0 / 0 in both | 12 / 8 |

UDP combined decoder additionally reported 33 missing RTP packets. These are
reported counts, not loss rates. TCP retransmission can conceal RTP gaps;
zero RTP-gap warnings do not imply loss-free Wi-Fi. Queue warnings do not expose
queue occupancy. PTS gaps and concealment indicate continuity problems, not
verified audible dropouts without a controlled sound source.

The FFmpeg build reports these processing scopes (median / p95, ms):

| Trial | Video demux-to-mux | Audio encode-to-mux |
|---|---:|---:|
| UDP video | 0.075 / 0.216 | — |
| UDP audio | — | 0.061 / 0.205 |
| UDP combined | 38.985 / 46.603 | 0.063 / 0.328 |
| TCP video, batch 2 | 0.079 / 0.251 | — |
| TCP video, batch 3 | 0.086 / 0.298 | — |
| TCP audio, batch 2 | — | 0.059 / 0.231 |
| TCP audio, batch 3 | — | 0.092 / 0.370 |
| TCP combined, batch 2 | 45.827 / 66.712 | 0.120 / 0.884 |
| TCP combined, batch 3 | 46.429 / 65.704 | 0.106 / 0.948 |

These exclude prior camera/socket/probe buffering and are not end-to-end latency.

WHEP pilot stats: UDP combined lost 2 browser audio packets, concealed 58,680
samples and dropped 1 video frame with 1 freeze. TCP combined lost 0 browser
packets and dropped 0 video frames in both batches, but concealed 4,920 and 1,080
audio samples. TCP video-only reported 2 and 1 freezes. Thus TCP did not eliminate
every playback discontinuity. Combined video interval-average jitter residence
median/p95 was 23.7/429.3 ms for UDP and 72.3/127.1 and 64.0/103.2 ms for TCP.
Browser jitter residence describes only the receiver leg.

Raw logs, decoded continuity metrics, timestamps, commands, browser samples and
failure records are in `.runtime/transport-final-20261010-*` and
`.runtime/transport-comparison-summary.json`. Physical audio delay and A/V sync
remain unmeasured because a synchronized flash/click source is unavailable.

## Verification and next diagnostic

- Python suite: 63 tests run, 62 passed, one opt-in integration test skipped.
- Opt-in real-media integration separately passed for UDP and TCP: decoded WHEP
  video over UDP ICE, WHIP audio, authenticated TB2 datagrams and decoded MP4.
- Frontend build/browser suite: 18 passed. Compose configuration and Docker build
  passed; `git diff --check` passed.

Keep UDP as default. Next, collect longer physical direct-camera and relay-RTSP
player measurements with fixed decoder settings alongside Edge, then examine
combined FFmpeg input timestamps and interleaving if the relay delay persists.
Repeat comparable TCP/UDP trials after that diagnosis; do not infer a latency
fix from transport choice alone. See [the repeatable procedure](rtsp-transport.md).
