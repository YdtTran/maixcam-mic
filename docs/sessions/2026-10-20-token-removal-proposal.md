# Token removal proposal — 2026-10-20

## User decision

User prioritizes easy deployment on local Wi-Fi, requested an OpenSpec proposal to remove unnecessary security dependencies, and clarified: remove `.talkback_token` and its dependencies; retain the admin login because it does not interfere with deployment. The preceding interrupted implementation turn only inspected files and made no application edits.

## Planning result

Created [remove-local-network-token-auth](../../openspec/changes/remove-local-network-token-auth/proposal.md) with a proposal, `trusted-lan-device-control` delta spec, design and implementation tasks. No conditional artifact was skipped.

The plan removes runtime token arguments/reads, Bluetooth token headers/checks, packet HMAC signatures and deployment generation/check/upload/mount requirements. It uses a token-free TB3 marker with existing frame/session/timestamp validation and camera clock calibration. PC and camera must update together; no dual-mode switch or substitute secret is proposed. There is no third-party library to uninstall solely for token authentication.

Admin login, SSH credentials/host verification, fixed headset/Bluetooth pairing, existing operator Origin checking and loopback publication, recording safeguards, TCP/video, separate UDP8004 return, SCO ordering, rotation and multistream recording are retained. New Host/Origin hardening from the prior audit plan is deferred.

The older hardening and desktop-setup proposals contain conflicting token-preservation/adoption requirements. This new plan explicitly supersedes those requirements and includes a first apply task to reconcile their artifacts without marking unrelated work complete. This planning turn leaves those artifact sets unchanged.

Migration retains optional old tokens privately only for restoring a legacy release. New startup/deployment does not require valid old tokens. Rollback must restore the old container configuration/mounts as well as its image; replacing only the image under new Compose is insufficient. Obsolete active token files are removed only after the new compatible pair is verified, with recovery snapshots retained.

## Inspection and verification

Read the PC/camera token consumers, shared packet codec, Bluetooth handlers/client, startup wiring, Compose mount, script payload/preflight/rollback paths, relevant tests, current documentation and both pending proposals. `openspec list --specs` reported no main specs. Root/context resolved to this repository; configured schema is `spec-driven`.

- `openspec status --change remove-local-network-token-auth`: all four artifact groups complete.
- `openspec validate remove-local-network-token-auth --strict`: passed.
- Planning output paths checked against the resolved change directory.
- No runtime tests were rerun: application source is unchanged. Earlier audit results are documented separately, not presented as validation of an unimplemented token removal.

## Final runtime state and limits

No application/configuration edits, token-file deletion, build, camera SSH operation, deployment or restart. Existing live state was not queried. Token-free behavior, coordinated migration/rollback and audible speech remain implementation/acceptance work. The trusted-LAN design intentionally accepts unauthenticated camera control and talkback after implementation. Implementation awaits a new apply request.
