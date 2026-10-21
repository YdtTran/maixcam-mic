# Spec Delta

## Purpose

Protect recordings across capture, completion, maintenance and download, and keep optional metadata failures from disabling the local operator.

## ADDED Requirements

### Requirement: Recording and maintenance are mutually exclusive
Stop and deployment operations SHALL acquire exclusive maintenance ownership before replacing services, rebooting the camera or restoring backups. Acquisition SHALL atomically refuse active capture or finalization. Recording starts and competing mutations SHALL be refused until the owner completes or explicitly recovers maintenance.

#### Scenario: Recording starts during a long build
- **WHEN** an update owns maintenance and a browser attempts to start recording before container replacement
- **THEN** the start is refused with an actionable maintenance response and no capture begins

#### Scenario: Capture wins the acquisition race
- **WHEN** recording starts immediately before maintenance acquisition
- **THEN** acquisition fails without rebooting the camera, stopping the operator or changing deployed settings

#### Scenario: Container recreation preserves exclusion
- **WHEN** maintenance replaces the operator container and the new operator begins accepting requests
- **THEN** recording starts remain blocked until the owning operation releases maintenance

#### Scenario: Failed deployment rolls back
- **WHEN** verification fails and the owner restores the prior camera payload or PC image
- **THEN** rollback retains the same maintenance ownership and cannot interrupt a newly started recording

#### Scenario: Deployment process crashes
- **WHEN** the owning deployment terminates unexpectedly
- **THEN** recording remains blocked with recovery instructions until an explicit, recording-safe recovery releases maintenance

#### Scenario: Read-only preflight
- **WHEN** a user runs dry-run or check-only deployment
- **THEN** it does not acquire persistent maintenance, change settings or restart services

### Requirement: Optional metadata failure is isolated
Invalid camera-view or per-recording metadata SHALL produce a diagnostic without preventing operator startup or listing other valid recordings. The service SHALL preserve the invalid file, use rotation zero when view metadata is invalid, and use unknown duration when a recording's optional metadata is invalid.

#### Scenario: Broken view document
- **WHEN** the saved view file is truncated, has the wrong JSON shape or contains an invalid rotation
- **THEN** the operator starts with rotation zero and reports the invalid file without deleting it

#### Scenario: Broken recording sidecar
- **WHEN** a nonempty saved recording has an array, null or malformed JSON in its metadata sidecar
- **THEN** the recording list remains available and includes that recording with unknown duration

### Requirement: Legacy completion reflects the process result
Legacy recording completion SHALL distinguish successful finalization from process failure or forced termination. Failed output SHALL be retained for recovery and SHALL NOT be advertised as a successful saved recording. The status API and UI SHALL expose the failure until a later recording starts.

#### Scenario: Nonzero finalization exit
- **WHEN** the legacy recorder exits unsuccessfully despite leaving nonempty output
- **THEN** status reports failure and the output is excluded from successful recordings

#### Scenario: Forced termination
- **WHEN** the legacy recorder exceeds its stop deadline and must be killed
- **THEN** the UI reports an interrupted recording with recovery guidance instead of a saved-recording message

### Requirement: Real recordings use browser downloads
Downloading a real saved recording SHALL stream the existing file through the browser download mechanism with its recording filename. The interface SHALL NOT read the complete file into an application-created Blob. Playback and byte-range seeking SHALL continue to work.

#### Scenario: Long recording download
- **WHEN** the user downloads a multi-hour real recording
- **THEN** the browser starts a file download without the application fetching and buffering the complete video first

#### Scenario: Playback remains seekable
- **WHEN** a player requests a byte range of a saved recording
- **THEN** the service returns the requested valid range with the appropriate partial-content response
