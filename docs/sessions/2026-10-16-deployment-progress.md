# Visible PC deployment progress — 2026-10-16

User reports deployment blocked at `deploy_pc.ps1` on another machine. Requested
the last terminal output asynchronously; the remote failure is not yet proven.
Do not claim the remote laptop is repaired without its output or a successful run.

Source inspection found an independent observability bug: `Invoke-ProjectScript`
captured the complete PC subprocess output and printed it only after exit. A
first Docker build downloading images/dependencies could look completely stuck.

- Added opt-in streaming to `Invoke-NetworkProcess`, concurrently draining stdout
  and stderr while preserving captured output, deadlines and failure propagation.
  SSH/credential commands retain their existing buffered behavior.
- PC subprocess invocation now streams build/preflight/start output once as it
  arrives. `deploy_pc.ps1` labels Docker engine, configuration, recording checks,
  build/health and Windows HTTP stages, and explains first-build downloads.
- A delayed child regression asserts stdout arrives before the child completes,
  and stderr is displayed. Added timeout/exit-code checks for streamed execution.
- Focused deployment suites: 22 tests passed. Real Windows PowerShell
  `deploy_pc.ps1 -CheckOnly` passed against local Docker. No service, camera,
  network configuration or recording was restarted/changed for this repair.

User also asks whether multiple servers can read video. Source confirms the
camera RTSP server has separate client sessions and bounded per-client queues.
However, microphone return targets one PC_IP, talkback has no cross-server
ownership coordination, and same-host containers need non-conflicting published
ports/project names. Running full camera deployment from a second laptop changes
the microphone destination; multi-reader video alone does not cause a Docker
deployment block.
