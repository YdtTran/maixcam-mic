# Recording maintenance exclusion — 2026-10-21

User requested only section 4 of `harden-runtime-and-trim-obsolete-code`.
Tasks 4.1–4.5 are implemented; tracked progress is 12/22. Implemented;
redeployment verification pending. The apply plan requires separate live
deployment authorization, so this session did not restart Docker or contact
the camera. Existing source/configuration work and the desktop-setup proposal
were preserved.

## Changes and recovery

`RecordingManager` acquires/releases maintenance under its existing recorder
lock. Capture and asynchronous finalization refuse acquisition. A matching
owner may retry; foreign owners cannot release the persisted
`recordings/.maintenance.json` marker. Starts check it on each request, including
after manager/container recreation. Invalid or unreadable markers fail closed.
The status/UI shows maintenance separately from capture/metadata failures;
listing and saved-file playback remain available.

Windows entry points share an exclusive `.runtime/mutation.lock` file handle.
Nested processes inherit the operation owner and verify the still-held lock
and matching marker. The outer caller retains ownership through camera/PC
mutation, verification, UDP recovery and rollback. Failed/crashed operations
retain the marker. Read-only preflight never acquires either lock or changes
configuration. Missing `.env` initialization acquires maintenance without
starting the service and releases its marker after copying the template.

Stopped/nonexistent operators require Docker/native-listener checks before a
host marker is created. Running unresponsive operators block mutation. A first
upgrade stops the old operator after verifying idle, then starts a freshly built
maintenance-aware operator before camera mutation. That initial legacy
idle-check-to-stop interval is not atomic; avoid starting recordings during
the one-time bootstrap. Unsupported replacements are stopped before camera
mutation.

Rollback restores the inspected previous PC configuration **stopped**, retaining
the owner and reporting exit 6 until camera recovery can be checked explicitly.
This prevents an older image from admitting recording while camera recovery is
still running. Saved recordings and optional private rollback material remain.
The combined wrapper prints deployment success only after maintenance release;
a failed release reports failure and preserves recovery state.

The reusable API, nested helper contract, limitations and exact owner-specific
`scripts/recover_maintenance.ps1 -Owner ...` command are documented in
[scripts/README.md](../../scripts/README.md#recording-safe-maintenance-and-crash-recovery).
README troubleshooting links there. The future desktop wizard should reuse
this contract; its planning artifacts are unchanged.

## Verification and corrections

- `python -m unittest discover -s tests -v`: 199 tests ran successfully,
  eight skipped. Log: `.runtime/maintenance-python.log`.
- After final combined-wrapper release/error handling changes,
  `python -m unittest tests.test_network_deployment tests.test_start_scripts -v`:
  40 tests ran successfully, one POSIX-shell skip. Log:
  `.runtime/maintenance-windows-verified.log`.
- Additional focused checks passed for missing `.env` read-only initialization,
  unsupported replacement shutdown and stopped-image rollback. These cover
  assertions added after the full-suite snapshot; the full suite was not rerun
  merely to update its count.
- `npm test` in `frontend`: type check, build/package and all 36 source/compiled
  browser checks passed. Log: `.runtime/maintenance-browser-verified.log`.
- `docker compose config --quiet`, strict OpenSpec validation and
  `git diff --check` passed. The apply instructions confirmed each section-4
  checkbox and progress advanced from 7/22 to 12/22.

New checks cover concurrent capture/acquisition with exactly one winner,
finalization exclusion, owner validation, corrupt markers, manager recreation,
real HTTP 409 responses, and a real Windows-helper-to-isolated-backend request
between preflight and mutation. A two-process Windows test proves host locking,
child ownership reuse, stale-marker rejection and explicit owner recovery.
Script fixtures cover idle/unavailable/stopped operators, upgrade ordering,
unsupported replacements, audio recovery, stopped-image rollback and release
failure without a success announcement.

Initial checks exposed a real PowerShell native-argument quoting defect in the
maintenance JSON body. Replaced embedded JSON text with Python `json.dumps`;
the real Windows/helper/backend integration now passes. Initial browser checks
also found a wrong test button name and an assertion shorter than the existing
10-second polling interval; corrected the test to use Record and explicit
Refresh. One early existing disconnected-peer browser check failed; it passed
in the final complete 36-check run. No media behavior was changed for that.

The eight full-suite skips were:

1. `test_full_y_and_chroma_planes_rotate_without_resampling`: camera NumPy runtime.
2. `test_rotation_reuses_destination_for_changing_frames`: camera NumPy/OpenCV runtime.
3. `test_independent_pcmu_video_recording_and_talkback`: opt-in `HEADSET_INTEGRATION=1`.
4. `test_correlated_full_scale_voices_do_not_clip_mix`: opt-in `MULTISTREAM_INTEGRATION=1`.
5. `test_late_audio_gaps_two_sessions_and_video_copy`: opt-in `MULTISTREAM_INTEGRATION=1`.
6. `test_failed_preparation_retries_before_any_audio_service_starts`: POSIX boot shell.
7. `test_shell_runs_fallbacks_and_continues_when_tuning_fails`: POSIX boot shell.
8. `test_actual_udp_recording_whep_and_whip`: opt-in `UDP_INTEGRATION=1` and MediaMTX fixture.

## Limits and final state

No live installation, physical picture/listening/Talk/rotation/recording cycle,
audible acceptance, another-laptop bootstrap or physical crash/rollback trial
was performed. Tests use temporary files and isolated loopback HTTP ports;
Docker/SSH mutations are mocked. Frontend packaging refreshed ignored output.
The production camera, container, settings and recordings were unchanged.
Maintenance coordinates one checkout on one Windows host; another operator PC
must remain stopped during migration. Source completion does not establish
operational completion. Remaining OpenSpec sections 5–8 stay pending.
