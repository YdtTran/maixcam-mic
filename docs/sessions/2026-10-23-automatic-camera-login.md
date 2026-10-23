# Automatic camera login — 2026-10-23

The user guarantees the standard factory camera SSH username/password and asks
that deployment stop requesting or repeatedly verifying those credentials.
Wi-Fi SSID/password requirements from the preceding change remain in effect.

## Changes

- The shared `New-SshContext` supplies the guaranteed camera password whenever
  no explicit key or password is supplied. SSH and SCP already use the root user.
  All deployment entry points inherit the default through this shared helper.
- Authentication uses the existing encrypted temporary askpass helper, with
  password authentication preferred. No camera password prompt, saved-credential
  setup or manual login is required. Temporary helper files are removed on exit.
- Automatic deployment no longer loads `.runtime/deploy-credential.xml` by
  default, so stale passwords cannot override the guaranteed default. Existing
  explicit key, password and credential-file overrides remain supported.
- OpenSSH uses `StrictHostKeyChecking=accept-new` to enroll a new camera key
  without a prompt. Changed saved keys are still rejected; Wi-Fi SSH retains
  the verified USB host identity. First-use trust is automatic on the USB
  discovery connection rather than requiring a manual fingerprint comparison.
- Root README, deployment guide and installer guide now describe automatic
  camera access. Wi-Fi password prompts are clearly separate.

## Verification and limits

A focused PowerShell check verified the default encrypted credential's username
and password, forced askpass, preferred password authentication, automatic
first-key enrollment, helper cleanup and preservation of an explicit key
override. Its first run exposed a test-only PowerShell quoting error; the fixed
test passed. Deployment fixtures now contain a deliberately invalid stale
credential file to verify it is ignored by default.

Final verification:

```text
python -m unittest tests.test_start_scripts tests.test_network_deployment -v
Ran 52 tests in 91.903s — OK (51 passed, one POSIX boot-shell test skipped)
```

PowerShell syntax parsing for the changed script/module and `git diff --check`
also passed.

No actual SSH login, host-key enrollment, camera update, firewall mutation or
service restart was performed. Implemented; redeployment verification pending.
Default camera credentials are an explicit user guarantee, not a live login
result from this session. Failed SSH authentication still causes setup to fail.
Changed saved host keys still need investigation before deployment can proceed.

Reference: [OpenSSH host-key policy](https://man.openbsd.org/ssh_config#StrictHostKeyChecking).
