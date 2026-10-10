# 2026-10-10 direct PC deployment

User requested direct deployment, then asked to retry camera SSH access.

Ran `./start_operator.ps1 -MaixIp 192.168.1.7 -Transport tcp -StreamMode video
-ReturnAudioPort 8004`. Native Windows operator started hidden, PID 16660,
HTTP UI returned 200. Camera TCP video packet preflight succeeded. `/maix01`
and `/headsetmic` RTSP DESCRIBE both returned 200; talkback status reported
available with no relay error. Saved TCP/video configuration was retained.

The existing camera RTP sender already delivered PCMU/8000/mono to UDP8004.
The PC receiver copies this to `/headsetmic` over RTSP/TCP. Camera processes,
profiles, sender deployment and boot scripts were not changed.

`ffmpeg -rtsp_transport tcp -i rtsp://127.0.0.1:8554/headsetmic -t 6
-af volumedetect -f null -` decoded 48,160 samples. Mean -76.3 dB and peak
-50.0 dB: nonzero but very quiet, not proof of intelligible worker speech.

Read-only real Chromium check `node scripts/check-deployed-return.mjs` passed:
H.264 decoded 11 frames, 466,446 received bytes; independent PCMU received
8,640 bytes. Both reported zero lost packets in this short sample. The audio
element was unmuted and playing after Enable audio. These are delivery checks,
not physical latency, audible speech or long-run packet-loss measurements.
Ignored evidence: `.runtime/deployed-return.png`. Navigation cleaned up WHEP
sessions. This check did not activate talkback or modify recordings.

Root SSH BatchMode access was rejected, including a retry after the user's
"try again" instruction. The local Windows SSH agent has a key but camera login
remains unavailable. Updating camera files and enabling/testing SCO duplex
requires usable camera SSH access. Default camera A2DP/pause behavior remains:
microphone return may be silent while talkback plays. No duplex claim is made.

Final runtime: native app PID16660 with MediaMTX, TCP video-only publisher and
independent UDP8004 PCMU receiver running. Talkback reports available. Docker
operator was not used; production camera services were not restarted. Recording
remains video-only. Logs/PID remain `.runtime/operator-native.*` and
`.runtime/headset-return.ffmpeg.log`. Stop through `./stop_operator.ps1` after
finalizing any active recording.
