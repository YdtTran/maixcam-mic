# Windows redeployment README for nontechnical users — 2026-10-17

## Request and changes

The user requested a README that lets nontechnical Windows users redeploy the
system themselves, using PowerShell execution-policy bypass in the commands.

Rewrote the root README around the existing automatic USB-first deployment
script. Included prerequisites, opening PowerShell from File Explorer, initial
camera trust/password setup, laptop migration, ordinary/forced/dry-run
deployment, success messages, manual picture/audio/recording checks, daily
startup, safe shutdown and troubleshooting. Every script invocation includes
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File`.

The guide distinguishes redeployment of a prepared camera from initial device
provisioning, preserves the matching token and recordings, and links technical
details instead of requiring users to edit addresses or select audio profiles.

## Verification and runtime

- Compared instructions against `scripts/deploy.ps1`, `scripts/README.md`,
  `run_all.ps1` and `deploy_pc.ps1`.
- Checked all local README link targets exist.
- Parsed all ten PowerShell example blocks with the PowerShell syntax parser;
  no parse errors. Verified bypass on all seven script command lines.
- `git diff --check` passed; Git reported line-ending normalization notices.
- An independent reader review identified the need to explain joining new
  Wi-Fi before deployment. Added that clarification to the prerequisites.
- Documentation only. No deployment commands executed, services restarted,
  camera settings changed or secrets read. Hardware acceptance was not repeated.

## Limits

Windows script bypass applies to the launched process and does not override
organization-enforced policy. Camera provisioning, trusted identity and login
details must already be available. Saved password credentials are specific to
the Windows account and PC; the README explains recreating them on a new laptop.
