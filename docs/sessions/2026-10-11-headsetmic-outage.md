# Headset return outage — 2026-10-11

User supplied repeated MediaMTX `no stream is available on path 'headsetmic'`
messages around08:30:51 UTC after the SCO boot-order repair. Read-only checks:

- PC Docker remained healthy; microphone receiver repeatedly failed to publish
  and backed off to30 seconds. FFmpeg log reported output header initialization
  interrupted by SIGTERM, consistent with the supervisor's publication timeout.
- Camera and PC addresses remained10.127.15.230 and10.127.9.237. Camera sender
  PID617 and FFmpeg PID625 remained running, but capture repeatedly failed with
  BlueALSA PCM-not-found. Bluetooth reported paired/trusted/connected, while
  link inventory showed ACL only, without SCO. Connector log contained busy
  connect failures. No pause marker remained.
- Camera tcpdump captured five172-byte UDP packets to the configured PC8004;
  the sender still transmits silence during capture loss. An eight-second raw
  packet check in the Docker container observed zero incoming UDP8004 packets.
  At the snapshot, receiver was in backoff with no8004 socket open. This is a
  limited observation; it does not isolate Windows firewall, network or Docker
  forwarding as the cause. Windows showed Docker backend bound on8005 but not
 8004 at that snapshot.

No repairs, restarts, profile changes or source modifications performed in this
diagnostic follow-up. Audible audio and return publication are unavailable in
the evidence above; a healthy operator API is insufficient to claim media works.

## Authorized recovery attempt

User requested fixing the outage and updating logs. Verified no active recording.
Ran `stop_docker_pc.ps1`, then `deploy_pc.ps1`. Operator health and Windows HTTP
checks passed. At08:34:15 UTC `/headsetmic` published G.711, the real browser
connected to it, H.264 video republished, and Windows Docker UDP8004 listener
returned. This recovered the PC publication/forwarding failure without source
changes; the underlying Docker backend failure is not isolated.

Concurrent clean headset reconnect closed capture through pause/ack and
disconnected successfully, but connect failed with page-timeout. Subsequent
BlueALSA ObjectManager query exposed no PCM endpoints; BlueZ ConnectProfile for
the supported hands-free UUID failed with resource-busy. Headset remained
ACL-only, without SCO. User confirmed earbuds powered on nearby.

Attempted scoped hci0 reset after checking only the bound headset was present,
no active aplay existed, and capture pause was acknowledged. Connector was
temporarily suspended to avoid reconnect contention; the remote helper uses
finally to resume it and release the pause marker. The SSH operation timed out
at40 seconds with no returned command output, so completion of those steps is
unverified. Camera then failed ping/SSH over USB and Wi-Fi; PC camera API503 and
video connection timeouts corroborated loss of access. Do not attribute this
unreachability to a particular driver/controller fault without further evidence.
Requested a camera power-cycle from the user before continuing verification.
No source changes or recording deletion. PC container remains healthy; media
cannot be called recovered while the camera is unreachable.

## Camera returned and microphone delivery recovered

User confirmed a hard reboot after the unreachability report. Camera subsequently
responded on USB and Wi-Fi, with uptime under one minute; video republished at
08:38:12 UTC and microphone return at08:38:20. Initial Bluetooth state remained
ACL-only with an empty BlueALSA PCM inventory. A targeted hands-free
`ConnectProfile` request returned already-connected, while the existing connector
was also retrying. Immediately afterward eSCO state1 and capture PID747 were
present. The request's error means it cannot be credited as a successful repair
by itself; reconnection completed during those retries after the user's reboot.

Final inspection: connector PID617, duplex receiver PID618, microphone sender
PID619, one capture PID747 at8kHz mono/20ms periods/80ms buffer, controller up
with MTU120:4. Six-second PC RTSP decode of `/headsetmic` exited0 with48000 PCM
samples,34190 nonzero samples and peak780 (16-bit scale). These sample statistics
prove non-silent media delivery, not intelligibility or physical latency.
After08:38:30, the inspected PC log contained no new headset-return publication
loss. Browser had reconnected to return audio; Docker healthy and talkback status
available/error null. Asked user to confirm audible listening on the PC.

This session repaired runtime availability through the PC restart and subsequent
camera/headset recovery. No new application code fix was made. Exact causes of
the Docker UDP-forwarding loss and Bluetooth busy/profile failure remain
unproven. The earlier SCO boot-order fix remains installed. No recording-mode
change or saved-recording deletion. Hardware/media verification was used instead
of rerunning source unit tests for service restarts.
