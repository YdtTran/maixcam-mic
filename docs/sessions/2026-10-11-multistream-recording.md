# PC multistream recording extension — 2026-10-11

## Request and scope

User requested PC-only MP4 recording with copied H.264 video, mixed default AAC,
separate worker AAC and operator AAC. Audio must support late publication,
disconnects, silence and repeated talkback sessions without stopping video.
User required inspecting the repository and explaining architecture/risks before
implementing the smallest testable version. Preserve accepted TCP/video monitoring
and existing camera/Bluetooth transports.

Work took place on `experiment/sco-duplex`, initially clean. The user subsequently
requested committing these changes. No camera changes, audio-route changes, process restarts or deployment
were performed. Synthetic fixtures used isolated ports and their children were
stopped. Existing live runtime remains under its prior configuration.

## Inspection and decision

`RecordingManager` previously consumed only `/maix01`, with recording tracks
selected by live `stream-mode`. Independent receiver publishes `/headsetmic`;
WHIP publishes `/talkback`, read by a separate talkback decoder. MediaMTX has
publisher paths for all three streams. Operator talkback is session-scoped.

An absent-input probe and an isolated MediaMTX test showed FFmpeg exits opening
a missing audio path. Optional stream mapping does not create an input or add
one later. Communicated the coordinator architecture and timing/disk/finalization
tradeoffs before implementation.

Added an opt-in `multistream` recorder in `pc/multistream_recording.py`: independent
H.264-copy Matroska staging; two reconnecting RTSP/TCP decoders; 48 kHz mono s16le
PCM; bounded queues and monotonic 20 ms silence-filled timeline; offline AAC
mix/encode/remux after capture. Fixed normalized half-gain mix plus a 0.95 limiter
with latency compensation. Video remains copied during capture and final mux.

Video reception wallclock timestamps use a fixed epoch-to-monotonic bridge.
Audio follows decoded PCM arrival; independent RTP origins are not compared.
Queue drift is bounded through dropping/silence, not adaptive resampling. A PC
wallclock step over 250 ms stops capture and attempts safe finalization. Video
loss ends capture and finalizes; audio loss leaves capture running with silence.
This establishes file-timeline behavior, not physical capture-time alignment.

Integrated `--recording-mode legacy|multistream` into `app.py` and standalone
operator, defaulting to legacy. Native helper accepts `-RecordingMode`; rejects
mismatching active mode. Stop finalizes asynchronously, protects new starts and
native shutdown, reports errors, atomically publishes MP4, preserves staging on
failure. UI reports finalizing and completion. Packaged `pc/operator_test.html`
regenerated. Added logs, manifest, recording metadata and recovery instructions.

## Validation and failures resolved

- `python -m unittest discover -s tests -v`: 109 discovered, 105 passed,
  four opt-in integration tests skipped. Six new unit tests cover absent/stale
  audio, partial PCM, retries, drift/queue bounds, sample timeline, scheduler
  stalls, wallclock steps, mux failure staging and finalization protection.
- `$env:MULTISTREAM_INTEGRATION='1'; python -m unittest discover -s tests -p
  test_multistream_integration.py -v`: two real media tests passed, 16.5 seconds.
  Checked missing RTSP input fails, legacy video-only output, recording before
  audio, two source publication sessions, worker/operator reconnects, silent
  gaps, separate tone content, four codec tracks, default disposition and names,
  48 kHz/sample duration, monotonic video PTS, copied H.264 encoded slices, full
  file decoding, video-loss automatic finalization and correlated full-scale
  mixed-track clipping protection.
- Initial whole-packet copy check failed because RTSP inserts SPS/PPS into keyframe
  packets. Replaced it with encoded slice NAL byte comparisons against the source
  fixture; all recorded video slices match. No video encoder is used by recorder.
- An exploratory wallclock capture using `-t` with absolute `-copyts` input
  produced an empty Matroska file. A gracefully stopped probe with fixed negative
  epoch output offset produced relative video timestamps. Implementation uses
  graceful stop for live capture, then relative-duration offline mux.
- `npm test` in `frontend`: build/type checks and all 22 source/compiled browser
  tests passed. New finalization test originally found a completion notification
  defect: notice expired before the next poll. Fixed by tracking previous
  finalization state independently of transient notice text. Screenshot saved
  in ignored `frontend/test-results/multistream-finalizing.png`.
- `git diff --check`: passed, with existing Git LF/CRLF conversion notices.

## Limits and next physical acceptance

No physical flash/click trial, long hardware drift measurement or VLC selection
test was performed. FFmpeg decodes all four generated tracks and ffprobe verifies
their metadata; this is not a claim of VLC UI acceptance or physical A/V sync.
Reception alignment is affected by network/probing/decoder/keyframe delays and
timestamp quantization. B-frame video has not been validated. Short missed
talkback beginnings may not be recoverable during decoder retry/probing.

PCM staging uses approximately 691 MB/hour plus video; finalization adds AAC CPU
work and additional disk space. Disk exhaustion and forced termination can lose
the staged tail. No automatic video-capture restart within a recording; it ends
the recording. Interrupted application recordings need explicit recovery rather
than append. Hardware acceptance should measure signed audio-minus-video offset
for each side, at start/end and after reconnects, with a synchronized physical
flash/click stimulus. See [procedure and recovery](../multistream-recording.md).

Final runtime: existing live operator/camera left running as previously configured;
extension implemented and validated on fixtures, opt-in, not deployed.
