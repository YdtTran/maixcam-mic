# Spec Delta

## Purpose

Allow a prepared WorkerCam camera and local operator PC to provide talkback and device control on a trusted LAN without distributing or synchronizing a shared application token.

## ADDED Requirements

### Requirement: Device services start without token files
The PC operator, camera Bluetooth control and camera talkback services SHALL start without reading a shared application token. Missing, malformed or mismatched legacy token files SHALL NOT disable those services or prevent normal startup.

#### Scenario: New PC installation
- **WHEN** a configured PC has no `.talkback_token` file and its camera runs the compatible release
- **THEN** Bluetooth control and talkback are configured and can operate without generating or copying a token

#### Scenario: Old token content is unusable
- **WHEN** either device contains an invalid or mismatched legacy token file
- **THEN** the new services ignore that file and do not request token repair

### Requirement: Token-free Bluetooth control
Camera status, clock calibration, scan and selection requests SHALL operate without a shared-token HTTP header. Device binding, supported-action checks and request-body validation SHALL continue to apply.

#### Scenario: Clock and status without credentials
- **WHEN** the local PC requests camera clock or Bluetooth status without `X-Control-Token`
- **THEN** the camera returns the normal response without a token authorization failure

#### Scenario: Selection still respects fixed earbuds
- **WHEN** a token-free request attempts to select a headset other than the configured fixed device
- **THEN** the camera rejects it and retains the existing headset binding

### Requirement: Token-free versioned talkback
Talkback SHALL use a distinct TB3 datagram version without an authentication signature. Sender and receiver SHALL retain the PCM16 mono 8 kHz payload, bounded frame size, session identity, sequence number, stop semantics and calibrated timestamp behavior. Older TB1/TB2 packets SHALL be rejected as incompatible.

#### Scenario: Normal speech and release
- **WHEN** a compatible PC sends valid TB3 PCM frames followed by a valid stop packet
- **THEN** the camera plays speech and ends that session through its existing audio lifecycle without a token

#### Scenario: Older sender remains active
- **WHEN** the new receiver receives TB1 or authenticated TB2 packets
- **THEN** it rejects them without interpreting signature bytes as PCM or starting playback

### Requirement: Audio reliability validation remains active
The receiver SHALL reject malformed, oversized, odd-length PCM, stale, duplicate, retired-session and invalid stop packets using the existing applicable rules. Clock calibration, bounded queues and reorder/drop timing SHALL remain in effect without authenticating packet contents.

#### Scenario: Stale or malformed speech
- **WHEN** a datagram is beyond the existing two-second freshness window, has invalid framing or exceeds the frame limit
- **THEN** the receiver rejects it without launching or disrupting playback

#### Scenario: Late stop from an earlier session
- **WHEN** a retired session's stop or audio packet arrives during a newer session
- **THEN** the current session remains unaffected according to existing session rules

### Requirement: Deployment has no active token prerequisite
Deployment SHALL NOT create, validate, synchronize, upload or mount an application pairing token for the new release. Supported startup/deployment commands SHALL NOT require token arguments. The new release SHALL NOT add a replacement key, authentication mode switch or third-party dependency for this purpose.

#### Scenario: Token-free Compose deployment
- **WHEN** a prepared system runs the documented deployment workflow with no local token file
- **THEN** Compose configuration and deployment pass their normal non-token checks without creating a token or token bind mount

#### Scenario: Old CLI parameters are removed
- **WHEN** current help and customer instructions describe startup and deployment
- **THEN** they contain no required token-generation, copying or token-argument step

### Requirement: Coordinated migration and recovery
An upgrade SHALL treat PC sender, camera receiver, Bluetooth client and camera API as one compatible release. It SHALL finish active recordings before disruption, retain recoverable prior configuration and report failed verification honestly. Rollback to a token-based release SHALL restore its matching configuration and token material when available; lack of recoverable legacy material SHALL be reported explicitly.

#### Scenario: Upgrade from the token-based release
- **WHEN** both devices are updated from a working TB2 installation
- **THEN** verification checks the new protocol on both sides and usable media/control rather than claiming success from HTTP availability alone

#### Scenario: Migration fails after one side changes
- **WHEN** the new release cannot complete coordinated activation or media verification
- **THEN** the workflow restores the prior compatible pair where recoverable and distinguishes incomplete recovery from verified recovery

#### Scenario: Existing token supports rollback only
- **WHEN** the old installation has token material needed for its recovery snapshot
- **THEN** migration retains it privately for old-release rollback without requiring it for new-release startup or copying it into the new active payload

### Requirement: Existing user access and media remain stable
The release SHALL retain the admin/admin prototype login, SSH access checks, PC loopback publication, existing operator Origin check, fixed headset pairing, TCP/video monitoring, independent UDP8004 return, SCO startup order, manager rotation and multistream recording. It SHALL NOT implement additional Host/Origin hardening as part of token removal.

#### Scenario: Daily operator use after migration
- **WHEN** the user opens the upgraded operator page and signs in using the existing login
- **THEN** live video, listening, talkback, rotation and recording remain available through the existing workflows
