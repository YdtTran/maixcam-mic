# 2026-10-10 independent headset return implementation

User asked to implement earbuds → MaixCAM → PC browser in stages, preserving
accepted TCP video-only and talkback, leaving recording video-only, with exact
hardware commands if access is unavailable.

Inspection found the camera sender already emits PCMU/8000/mono, RTP PT0,
160-sample packets, direct UDP 8004/RTCP8005. Camera capture uses SCO while
`bt_output` uses A2DP. Talkback intentionally pauses capture through a marker/
ack handshake: simultaneous speech was not implemented by that arrangement.

Changes: opt-in independent `--return-audio-port` receiver in app.py, PCMU copy
to MediaMTX `/headsetmic` over TCP; capped 2–30s restart backoff, startup grace,
publication health checks, current/previous FFmpeg logs and child cleanup.
Native start helper enables UDP8004 return by default, supports 0 to disable,
and checks matching runtime flags. Docker gets optional RETURN_AUDIO_PORT and
8004/8005 mappings. Video publisher and recorder commands stay unchanged.
Separate browser WHEP audio element, interaction to unmute, status, reconnect,
navigation cleanup; video remains muted to prevent duplicate combined audio.
Camera adds explicit SCO playback profile and duplex talkback flags, preserving
A2DP/pause defaults. Capture stderr is now visible, failures send silence with
3s retry. No token or device credentials were changed or displayed.

Validation: Python suite 74 tests, 72 passed and two opt-in integration skips;
frontend build and 20 source/compiled Playwright tests passed. An isolated
HEADSET_INTEGRATION=1 fixture passed real PCMU RTP→RTSP copy→Chromium WHEP audio,
H.264 WHEP video, WHIP and talkback UDP packets, video decode after sender loss,
and finalized video-only MP4 inspection. It uses synthetic media, not Bluetooth.
Evidence screenshot: ignored `.runtime/headset-integration.png`.

Failures resolved: first isolated fixture bound WebRTC UDP to loopback and ICE
failed; listening on all interfaces fixed actual media delivery. Two existing
UI tests assumed the final peer was video; separate microphone added another
peer, so tests now select video by transceiver type. All checks then passed.

Hardware access: SSH BatchMode to root@192.168.1.7 rejected authentication.
Actual profiles/PCM capabilities, installed versions, audible microphone,
SCO duplex, physical latency/delay/dropouts/echo/drift and Bluetooth recovery
remain pending. [Return guide](../headset-return-audio.md) has precise inventory,
local capture and SCO duplex trials, deployment/rollback and acceptance matrix.

Final runtime: production operator and camera services were not restarted or
reconfigured; only isolated synthetic processes were started and cleaned up.
A final HTTP check at 127.0.0.1:8000 refused the connection and no MediaMTX or
FFmpeg processes were present. Earlier session notes describe historical state,
not the current runtime. Built operator HTML was regenerated. Start the native
helper with the new options to activate the receiver. Do not interpret
this code completion as verified physical earbuds duplex or latency.
