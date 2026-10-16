# README standard SCO pipeline — 2026-10-11

User requested README.md use SCO duplex as the default pipeline after the
boot-order repair. Updated both camera installation and combined deployment
examples to explicitly include `-AudioProfile sco`. Documented simultaneous
listening/talkback, keeping SCO selected when changing device settings, checks
after reboot, worker audio during Talk in multistream recording, and explicit
`-AudioProfile a2dp` fallback.

Documentation only: script compatibility defaults remain A2DP when the profile
argument is omitted. Existing deployed SCO setup, Docker, transport, token and
recording mode unchanged. Reviewed all README profile references and both
deployment examples against the existing script parameters; whitespace check
passed. No runtime deployment or code tests needed for this prose change.

## Default aligned after return-audio recovery

User reiterated that the recovered SCO setup is the default and requested the
README update. Changed `AudioProfile` defaults in both `deploy_maix.ps1` and
`run_all.ps1` to `sco`, superseding the compatibility-default statement above.
Explicit `-AudioProfile a2dp` remains supported. Aligned installer/SCO guides.

README now states the full default pipeline: Docker PC, TCP video, independent
UDP8004 microphone return and SCO duplex. Legacy recording stays default;
multistream remains optional. Added missing-headsetmic recovery: finish
recordings, safe PC stop/start, keep earbuds on, and power-cycle an unreachable
camera. Documented that API health and Bluetooth connected status do not prove
audible audio, and the underlying forwarding/profile failures remain unproven.

Focused deployment suite:10 tests passed, including default camera environment
`AUDIO_PROFILE=sco` and explicit A2DP fallback. An initial test edit misplaced
an existing assertion and failed with NameError; moved it back to its original
test and reran successfully. Scoped whitespace check passed. No live services
restarted or configuration/token/recording files changed during this update.
