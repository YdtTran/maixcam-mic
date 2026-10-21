# Spec Delta

## Purpose

Allow local operators to retry talkback after browser loss or audio failure without restarting the PC service or allowing old sessions to affect new speech.

## ADDED Requirements

### Requirement: Failed talkback releases ownership
When talkback decoding fails or its media source disappears, the service SHALL cancel forwarding, reap its decoder and release its relay session within a bounded interval. A later valid offer SHALL be accepted without requiring Stop from the original browser. Failure details SHALL remain visible until a new session starts or an explicit current-session stop acknowledges them.

#### Scenario: Decoder cannot start
- **WHEN** a negotiated session cannot launch its audio decoder
- **THEN** its relay resource and active ownership are released, an interruption is reported, and the next offer can proceed

#### Scenario: Browser vanishes without Stop
- **WHEN** the browser closes or loses connectivity and its talkback media disappears without a Stop request
- **THEN** the service releases that session after its bounded media-loss detection and cleanup interval

### Requirement: Cleanup is owned by its original session
Cleanup and stop actions SHALL affect only the session that initiated them. A late worker or browser stop from an earlier session SHALL NOT clear a newer session, stop its forwarding or send a TB3 stop packet naming that newer session.

#### Scenario: Late cleanup races with retry
- **WHEN** a failed session's worker completes cleanup after a new session is admitted
- **THEN** the new session keeps its decoder, relay resource and forwarding state

#### Scenario: Stale browser stop
- **WHEN** a browser sends Stop for an already retired session
- **THEN** the current session remains active and its diagnostics are unchanged

### Requirement: Recovery preserves the accepted media contract
Talkback recovery SHALL retain camera-clock calibration, sequenced TB3 datagrams with freshness and framing checks, bounded audio queues and the selected SCO or A2DP behavior. It SHALL NOT restart video, re-pair the headset or alter independent microphone return.

#### Scenario: Retry after interruption
- **WHEN** a fresh offer succeeds after interruption
- **THEN** it uses a new session identity and calibrated packet timestamps while video and independent microphone return remain running
