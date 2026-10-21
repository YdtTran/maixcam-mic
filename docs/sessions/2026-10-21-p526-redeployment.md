# P526_5G redeployment and duplex acceptance

User requested paired redeployment on `P526_5G` and reported only PC-to-camera
audio working. User supplied Wi-Fi credentials; credentials are excluded from
this note. Final user report: **"both working now"**.

## Network recovery and deployment

Laptop was already on P526_5G at 192.168.1.4. Camera USB SSH remained reachable
at 10.172.16.1, but wlan0 was scanning without an address; its microphone sender
still targeted the prior laptop address 10.127.9.237. Docker Desktop was stopped.
Started Docker Desktop. The operator repeatedly failed its old-camera startup
probe before constructing RecordingManager; inspected its processes (only app
and camera ffprobe, no recorder), then stopped that failed startup. The normal
recording preflight had refused because its HTTP endpoint was unavailable.

Acquired owner-bound project maintenance while the operator was stopped. Saved
private prior Wi-Fi configurations under /root, configured P526_5G, verified
association/address, and persisted /etc/wpa_supplicant.conf to /boot so the
camera reboot retains it. Configuration and connection assertions ran in the
temporary recovery script. No Bluetooth bond or headset selection changed.

Within the same host lock/maintenance owner, ran:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\scripts\deploy.ps1 -UsbInterfaceIndex 17 -UsbPeerIP 10.172.16.1 -WifiInterfaceIndex 18 -Force
```

Camera installed/rebooted, PC Docker rebuilt/recreated healthy, and combined
media verification passed. Wi-Fi settings survived reboot. Final camera address
192.168.1.7 and microphone target 192.168.1.4 agree with ignored .env. Outer
maintenance released after success; no marker remains. Raw deployment output:
`.runtime/p526-redeployment.log`; temporary recovery script:
`.runtime/redeploy-p526.ps1` (contains no Wi-Fi password).

## Audio findings and live checks

Initially after reboot, headset was disconnected: connector logged page timeouts,
capture logged missing BlueALSA PCM, and the sender supplied fallback silence.
Deployment decoding proves packet delivery even in this condition; it does not
establish microphone capture. Asked user to power the headset and disconnect
other hosts. It subsequently connected normally; no Bluetooth reset, pairing,
audio-service restart or source repair was required. User confirmed both audio
directions working.

A subsequent 10-second return decode produced 80,000 samples, 61,479 nonzero,
with nonzero samples in every one-second window. Levels were quiet (-61.9 to
-69.6 dBFS RMS); these levels are not an intelligibility or physical-latency
measurement. Report: `.runtime/p526-return-levels.json`.

Real Chromium login/video/listening continuity passed for 60.191 seconds:
1,205 additional decoded 768x432 frames (20.02 fps), increasing video/audio at
every five-second sample, zero reported packet loss, unmuted playing audio,
and no page errors. Evidence: `.runtime/p526-live-continuity.*`.

Final Docker healthy; headset connected; TB3 Talk available without error;
recording idle, rotation/effective rotation zero, no metadata warnings and
maintenance null. Recordings and recovery snapshots retained. No new recording
or rotation trial, full automated suite rerun, or long-duration/physical timing
trial in this network-only follow-up. Audible acceptance is the user's report.

## Earlier hardening rollout in the same conversation

The preceding paired rollout succeeded before the user requested stopping.
Sections 1–5 were checked (14/22); sections 6–8 remained unchecked. During that
rollout, a talkback unit fixture allowed its cleanup thread's HTTP DELETE to
escape its mock and exceed the two-second join. Extended the HTTP mock over
the cleanup lifetime in tests/test_talkback.py; no application logic changed.
All 21 talkback checks and final full Python run passed (206 run, 198 passed,
eight skipped); all 42 source/compiled browser checks and Compose validation
passed. Skips match the legacy-recording session: two camera NumPy/OpenCV
checks, headset integration, two multistream integrations, two POSIX-shell
checks, and UDP integration.

That first build selected a newer Python base and encountered very slow Debian
downloads. Cancelled only its build subprocess. Automatic rollback hit the
previously known invalid port-IP serialization error and retained maintenance
with the operator stopped. Camera had not changed. Verified camera health,
used exact-owner maintenance recovery, and retried using the locally tagged
Python digest from the preceding successful build:
`sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89`.
The official Dockerfile then reused its FFmpeg cache. This cached base was also
used for the P526 rollout; no dependency update was attempted. The rollback
serialization defect remains unresolved; retain snapshots for manual recovery.

Earlier real checks verified maintenance refused recording with HTTP 409,
clear 0/90-degree live video, TB3 Talk start/stop, a new seven-second multistream
recording, portrait playback and return to live. Retained recording:
`20261021T055118Z_cdc87b31.mp4`, 2,451,320 bytes, 768x432 H.264 with 90-degree
display matrix and three AAC tracks. Earlier 60.185-second continuity decoded
1,203 additional frames (~19.99 fps), zero reported loss. Evidence:
`.runtime/hardening-redeploy-*`, `.runtime/hardening-redeployment*`, and
`.runtime/hardening-live-*`. No OpenSpec sections were completed or archived
by these deployment requests. Existing unrelated worktree changes preserved.
