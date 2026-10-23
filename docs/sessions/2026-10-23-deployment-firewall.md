# Deployment firewall setup — 2026-10-23

The user requested deployment-managed Windows Firewall access for camera
microphone UDP traffic, administrator requirements and documentation of the
reported `/headsetmic` failure. The incident used camera 10.32.21.107; the user
emphasized that camera addresses change. Their report attributes the outage to
Windows Firewall; final audible recovery was not independently verified.

## Changes

- `scripts/NetworkDeployment.psm1` creates or updates rules with display name
  `MaixCAM headset UDP from camera`: inbound Allow, UDP 8004/8005, enabled on all
  profiles, restricted to one validated camera IPv4 address. Existing rules with
  that exact display name are updated, including a manually created incident rule.
- `scripts/deploy.ps1` refreshes the source to the discovered camera Wi-Fi IP
  after dry-run exit and before service changes, even without a rebuild.
- `deploy_pc.ps1` uses the camera IP from the resolved Compose command, respecting
  Compose configuration precedence. Preflight exits before firewall mutations.
- `scripts/deploy.ps1`, `deploy_pc.ps1`, `deploy_maix.ps1` and `run_all.ps1` now
  declare `#Requires -RunAsAdministrator`. Users open elevated PowerShell themselves.
- Root README and deployment guide explain elevation, the microphone timeout
  cycle, the supplied manual command, updates to existing rules and changing IPs.

## Verification

`python -m unittest tests.test_start_scripts tests.test_network_deployment -v`
ran 45 tests: 43 passed, one skipped (POSIX boot shell), one initial failure in
the new firewall mock. The mock incorrectly emitted null into a strict-mode
pipeline; its update mock also redeclared PowerShell's common ErrorAction
parameter. Both fixture issues were corrected.

Reran the corrected firewall test and the strengthened repeated-deployment test:

```text
python -m unittest tests.test_network_deployment.NetworkDeploymentTests.test_firewall_creates_then_updates_camera_scope_without_duplicates tests.test_network_deployment.NetworkDeploymentTests.test_deployment_is_idempotent_and_force_redeploys -v
Ran 2 tests — OK
```

Across those checks, all 44 applicable tests passed; one POSIX test was skipped.
Coverage includes rule creation, replacing a stale source IP, repeated runs
without duplicate creation, invalid addresses, firewall errors preventing service
mutation, elevation declarations and read-only dry run/preflight. Tests run
isolated script copies without the elevation directive and mock external
operations; source scripts retain the directive. `git diff --check` passed.

## Limits and runtime state

No deployment, real firewall mutation, camera change, service restart or audible
check was performed. Implemented; redeployment verification pending. Existing
live runtime and configuration were left unchanged.

The rule refreshes at deployment time; it does not follow DHCP changes between
runs. Rerun discovery after an address change. Firewall updates persist even if
a later deployment stage fails; runtime rollback does not restore firewall scope.
These symptoms can also have non-firewall causes. Automated mocks do not prove
that Windows policy permits the rule or that physical headset audio recovers.
