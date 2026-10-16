# SCO and multimedia default pipeline — 2026-10-11

User requested SCO and multimedia as the default pipeline and reported SCO is
currently in use. Multimedia is interpreted as the existing multistream recorder.

## Changes

- Retained SCO defaults in deploy_maix.ps1 and run_all.ps1; camera boot template
  now also defaults to SCO if AUDIO_PROFILE is absent.
- Set Compose, app.py, operator server CLI and RecordingManager defaults to
  multistream. Updated .env.example and the ignored local .env accordingly.
- Recordings save copied H.264 video and three AAC tracks: mixed conversation,
  worker microphone and operator microphone. Legacy video-only recording and
  A2DP remain explicit fallbacks.
- Aligned README, installer and recording guides; updated tests to choose legacy
  explicitly where they exercise legacy commands or isolated video fixtures.
- Preserved live TCP/video monitoring and separate UDP8004 headset return.

## Validation and runtime

`python -m unittest discover -s tests -q`: 123 tests ran, OK, five skipped
(environment-dependent media integration and POSIX checks). First run found an
older audio-only parser test relying on the legacy default; it now selects
legacy explicitly. Added coverage for default multistream and audio-only rejection.

`docker compose config --quiet` passed. Resolved Compose command selects
`--recording-mode multistream`; transport/mode resolve to tcp/video.
`git diff --check` passed with existing line-ending warnings.

No camera deployment, PC restart, or live recording was performed. Current SCO
use is the user's report; it was not rechecked on hardware. New PC defaults and
local configuration activate with `./deploy_pc.ps1 -Build`, after recording and
finalization are complete. Physical A/V sync, long hardware drift and VLC
acceptance remain pending as documented in the recording guide.
