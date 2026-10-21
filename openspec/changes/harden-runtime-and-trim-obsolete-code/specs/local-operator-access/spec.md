# Spec Delta

## Purpose

Preserve current local exposure defaults. Additional Host/Origin hardening from the historical audit is deferred by `remove-local-network-token-auth`.

## ADDED Requirements

### Requirement: Preserve existing local boundary
The operator SHALL retain existing Origin checking, loopback publication and prototype login without adding new Host/Origin restrictions in this change.

#### Scenario: Existing operator use
- **WHEN** the operator is updated for runtime reliability
- **THEN** its existing local access behavior remains available
