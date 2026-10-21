# Spec Delta

## Purpose

Ensures continuous, recoverable H.264 RTSP/TCP video streaming and UDP8004 headset return audio across MaixCAM 2.4 GHz Wi-Fi/Bluetooth eSCO coexistence stalls, PC publisher startup/reconnection, and deployment verification.

## ADDED Requirements

### Requirement: Bounded RTSP/TCP frame delivery and keyframe-aligned recovery
The camera RTSP/TCP server SHALL bound per-client socket buffering, deliver interleaved RTP frames as complete frame payloads without premature write-timeout disconnects during transient wireless stalls, and resynchronize slow clients on the next H.264 IDR keyframe whenever queued frames are dropped.

#### Scenario: Transient wireless stall under 10 seconds does not sever the RTSP session
- **WHEN** a connected RTSP/TCP reader experiences transient network backpressure that delays socket drain for more than 2 seconds but less than 10 seconds
- **THEN** the camera server keeps the RTSP/TCP session open, drops stale unsent frames from the bounded per-client queue instead of accumulating an unbounded kernel backlog, and resumes delivery when the socket becomes writable

#### Scenario: Dropped queued frame forces IDR keyframe resynchronization
- **WHEN** a new encoded video frame arrives while a connected RTSP/TCP client's frame queue is full and an unsent frame is evicted
- **THEN** the server withholds subsequent non-keyframe slices from that client until the next H.264 IDR keyframe (`nal_unit_type == 5`) arrives and prepends current SPS and PPS parameter sets before sending the keyframe

#### Scenario: Persistent client stall exceeding the write timeout closes the session cleanly
- **WHEN** a connected RTSP/TCP client fails to accept socket writes for more than the 10-second write timeout
- **THEN** the server closes that client's RTSP connection and removes the client from the active broadcast set without stopping camera capture or affecting other readers

### Requirement: Tolerant PC video publisher startup supervision
The PC stream supervisor SHALL allow an newly spawned RTSP video publisher sufficient startup grace time to complete TCP connection, IDR keyframe wait, input stream probing, and local relay publication before treating the relay path as lost.

#### Scenario: Publisher taking between 10 and 18 seconds to probe over Wi-Fi completes startup
- **WHEN** the PC video publisher is started or restarted and requires between 10 and 18 seconds to receive an initial IDR keyframe and publish `/maix01` to the local relay
- **THEN** the supervisor does not terminate the publisher during that startup window and `/maix01` becomes available without a forced reconnect loop

#### Scenario: Publisher that exits early or fails to publish after the startup grace window is restarted
- **WHEN** the PC video publisher process exits unexpectedly or `/maix01` remains unavailable after the 20-second startup grace window and retry cooldown have elapsed
- **THEN** the supervisor terminates any lingering publisher process and spawns a fresh replacement publisher

### Requirement: Verified host UDP return-audio port bindings and launcher-safe camera recovery
PC deployment and combined deployment verification SHALL confirm that Windows host UDP listeners for independent headset return audio (`8004` and `8005`) are present after starting the container, and camera video recovery SHALL preserve single-instance `launcher_daemon` ownership of the hardware ISP/VI pipeline.

#### Scenario: Missing Windows UDP 8004 listener after container start triggers single-project recreate
- **WHEN** the PC service container reports healthy in video mode with independent return audio on UDP port 8004, but the Windows host lacks an active UDP listener on port 8004 or 8005
- **THEN** deployment recreates only this project's PC container while recording is idle and verifies both UDP 8004 and 8005 listeners before reporting success

#### Scenario: Sustained live continuity verification required for operational completion
- **WHEN** paired or PC/camera deployment verification runs against the live system
- **THEN** operational acceptance requires continuous decoded browser video frame progression across a sustained observation window alongside independent headset return audio, TB3 talkback availability, and single-instance camera processes
