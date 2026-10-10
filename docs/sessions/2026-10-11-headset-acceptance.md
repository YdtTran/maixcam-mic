# 2026-10-11 headset return acceptance and commit

After direct deployment, the user reported "the latency is great" and asked to
commit the implementation before moving on. This is qualitative user feedback;
no new numeric latency measurement, intelligible-speech test or SCO duplex
verification was performed in this turn.

Commit scope: independent PCMU RTP receiver and supervision, separate browser
WHEP audio playback/status/reconnect, native startup integration, optional camera
SCO duplex settings, regression and real-media checks, generated operator HTML,
deployment/acceptance documentation. Runtime logs, recordings, credentials and
tokens remain excluded. Existing validation: 72 Python tests passed with two
opt-in skips, 20 Playwright tests passed, synthetic real-media integration passed,
and deployed Chromium video/audio delivery check passed.

No services or media settings were changed for the commit. Preserve accepted
TCP video-only publishing/recording and independent UDP8004 return. Camera SSH
authentication and physical SCO duplex validation remain pending.
