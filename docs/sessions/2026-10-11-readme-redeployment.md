# README redeployment — 2026-10-11

User requested redeployment of both MaixCAM and PC using README.md, with failures
reported and no fixes attempted.

PC deployment preflight (`deploy_pc.ps1 -CheckOnly`) passed. Ran the README's
combined `run_all.ps1 -DeployMaix -Build` workflow using USB camera address
10.172.16.1, current PC Wi-Fi address 10.127.9.237, the established headset
binding, existing pinned SSH credentials and the default A2DP profile. Preserved
the existing pairing token and `.env` camera address 10.127.15.230, TCP/video.

Camera prerequisites, upload and installation passed. Backup:
`/root/workercam-backup-f35db9cb76a540559a42d9c4d5488b1c`. Reboot requested;
camera video port returned within the script deadline.

Docker image build and container recreation passed. Container
`maix-cam-server-server-1` is healthy. Windows operator HTTP check passed and
the browser was opened at http://127.0.0.1:8000. Post-deployment logs confirmed
camera TCP-interleaved packets, online H.264 `/maix01` and G.711 `/headsetmic`.
No deployment failure occurred and no implementation fixes were made.

Logs also contained a missing favicon response and a closed RTSP connection;
these were left unchanged. Audible headset listening/talkback, browser media
playback and physical latency were not tested in this redeployment.

## Follow-up: use SCO duplex

User requested SCO duplex. Ran the same combined deployment with
`-AudioProfile sco`. Installation/reboot and camera video-port checks passed;
Docker build, health check and Windows HTTP verification passed, and the browser
was opened. Camera backup:
`/root/workercam-backup-a28e01057bb449dba17468d1e1ec6c58`.

Read-only inspection confirmed `AUDIO_PROFILE=sco`, SCO MTU `120:4`, and both
managed ALSA directions using SCO at 8000 Hz mono. The installed boot template
selects receiver `--duplex --playback-profile sco`. Docker remains healthy.
The extra process inventory failed because BusyBox `ps` does not support `-ww`;
stopped further checks without retry or fixes under the user's instruction.
Live process arguments and audible simultaneous speech remain unverified.

## Recheck after user reboot

User reported a further camera reboot and requested another check. At camera
08:03:29 UTC, uptime was approximately one minute. BusyBox-compatible process
inspection succeeded: one connector PID584 with SCO/MTU/recovery options, one
receiver PID585 with `--duplex --playback-profile sco`, one microphone sender
PID586 targeting 10.127.9.237:8004, and one arecord PID642 using SCO, 8 kHz mono,
20 ms periods and 80 ms buffer. Controller showed connected eSCO state1, MTU
120:4; both ALSA directions retained SCO. PC Bluetooth API reported connected
and talkback API available without error. Docker was healthy. PC logs showed
H.264 republished at 08:02:27 and headset G.711 return at 08:02:37 following
reboot interruptions. Persistent camera logs contain PCM-not-found and playback
interruption errors; their individual times are unavailable, so they cannot
all be attributed to this boot. No fixes/restarts performed. Audible duplex
and browser playback still require confirmation.

## User reports silent PC-to-headset talkback

User clarified the failing direction is PC microphone to headset, and reported
the latest commit previously worked. Read-only inspection found browser offers
accepted at 08:09:31 and 08:09:37 UTC, with Opus published and read by the PC
relay. Status API remained available with no reported error. Camera receiver
PID585 still used duplex/SCO and eSCO remained connected in state1. Receiver
log tail contained additional `aplay ... Interrupted system call` lines compared
with the earlier check; older PCM-not-found errors remain without timestamps.
This proves signaling succeeded but does not prove audible delivery or isolate
the fault. No playback process was present during the idle inspection, which is
normal after Talk release. `bluealsa-cli` was unavailable. No code/runtime fixes
or restarts were performed under the user's continuing no-fix instruction.

## Authorized talkback recovery

User then authorized attempting a fix, with checkpoint/return to multistream
recording as an alternative. Used the fix-code workflow without changing source.
An initial 15-second synthetic WHIP tone connected successfully but the user
reported no sound. A camera snapshot showed aplay present initially and absent
later during that check. Direct USB authenticated tone sent 750 frames; the user
asked to inspect the earbuds connection rather than confirming its audibility.

Read-only earbuds inspection at 08:14:36 UTC confirmed EDIFIER X2 Plus paired,
bonded, trusted, unblocked and connected; eSCO state1, MTU120:4; SCO playback and
capture mixer both unmuted at 100%. No second audio owner was present.

Ran the existing isolated clean-reconnect helper through SSH: pause/ack closed
capture, confirmed only ACL remained, disconnected/reconnected the selected
headset, then resumed the existing microphone sender. Both Bluetooth operations
succeeded. Connector PID584, duplex receiver PID585 and sender PID586 remained;
new capture PID1668 reopened with the existing 20ms/80ms settings. Video and PC
operator were not restarted.

Retested through synthetic WHIP for 20 seconds: peer connected and API error
null. **User confirmed a steady audible tone in the headset.** This establishes
audible PC-to-headset delivery after reconnect; exact cause of the prior silent
link is unproven. No source change, checkpoint commit, branch switch or recording
mode change was needed. Normal PC microphone speech and prolonged SCO stability
remain separate acceptance checks.
