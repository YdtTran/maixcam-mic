What this repo does: WorkerCam sends MaixCAM video and headset sound to a local browser, sends speech back to the headset, and saves recordings on a Windows PC. PowerShell installs the camera payload and runs the PC stack in Docker. Assumed load: one camera, one operator PC and one person, possibly using multiple tabs and long recordings.

Audit date: 2026-10-20. This is a source audit with isolated reproductions, not a live-device acceptance test. Application code and live services were not changed. Existing untracked `.agents/` and OpenSpec work were preserved.

**Must fix**

1. **The HTTP guard trusts a website name supplied by the requester** (`pc/operator_server.py:268`, `pc/operator_server.py:301`).
   - **What this is:** The local server serves recordings and controls the camera. Its control guard compares Origin with Host, two request headers.
   - **Problem:** An isolated request with `Host: attacker.invalid` and `Origin: http://attacker.invalid` changed rotation and returned 200; reads have no Host guard. This leaves the application boundary open to foreign authorities, including a DNS-rebinding setup where a website name resolves to the local PC.
   - **Fix:** Allow only supported local Host/port values on every route and validate supplied control Origin against that fixed set. Keep Origin-free local deployment clients working.
   - **If we skip it:** The server continues trusting a foreign website identity. Browser/network exploitability varies; a full browser exploit was not attempted, and the prototype login is already explicitly documented as not securing APIs.

2. **Recording protection ends before deployment starts changing things** (`deploy_pc.ps1:49`, `stop_docker_pc.ps1:28`, `scripts/deploy.ps1:243`, `scripts/deploy.ps1:311`).
   - **What this is:** Deployment and stop scripts ask whether recording is active before changing camera or PC services.
   - **Problem:** A user can start recording after that check, while a build is running, before camera reboot or container replacement. Rollback runs Compose replacement directly; it also leaves a window for new capture.
   - **Fix:** Acquire maintenance atomically with recording start, refuse new captures until the operation ends, preserve the guard across container recreation, and use it for rollback and every mutating entry point.
   - **If we skip it:** An update can interrupt a recording despite the advertised safety check. The code ordering proves the gap; no production recording was interrupted to demonstrate it.

3. **Failed talkback keeps the speaking slot forever** (`pc/talkback.py:62`, `pc/talkback.py:89`, `pc/talkback.py:127`).
   - **What this is:** A relay session reserves the worker's headset while the browser sends speech.
   - **Problem:** Decoder failure cancels forwarding and sends a stop packet but leaves `location` set. An isolated failed decoder spawn followed by another offer returned `talkback is already active`; a lost browser may never send the Stop needed to clear it.
   - **Fix:** Release the failed session's resource and ownership automatically, keeping cleanup tied to its own identity so late workers cannot stop a replacement session.
   - **If we skip it:** A lost tab or decoder failure can leave Talk unusable until explicit cleanup or a service restart.

4. **Small metadata errors can disable the whole operator or recording list** (`pc/operator_server.py:51`, `pc/operator_server.py:205`).
   - **What this is:** JSON sidecars store camera rotation and recording duration.
   - **Problem:** A view file containing `{` raises `JSONDecodeError` during manager construction, before the HTTP server starts. A recording sidecar containing `[]` raises uncaught `AttributeError` and aborts listing; both were reproduced with temporary files.
   - **Fix:** Validate document shape and values, preserve bad files, fall back to rotation zero or unknown duration, and report which optional metadata needs attention.
   - **If we skip it:** One malformed settings file can cause restart loops; one malformed sidecar can make otherwise valid recordings inaccessible through the list.

5. **Legacy recording reports success after FFmpeg fails** (`pc/operator_server.py:73`, `pc/operator_server.py:156`).
   - **What this is:** Explicit legacy mode saves directly to MP4 and stops FFmpeg before listing the result.
   - **Problem:** Stop ignores a nonzero process exit, and a forced kill still leads to success metadata whenever nonempty bytes exist. An isolated process exiting 1 left a bogus nonempty MP4 listed as saved with no status error.
   - **Fix:** Capture the exit/forced-stop result before clearing the handle, retain failed files for recovery, exclude them from successful listings and display failure. Apply the same handling to unexpected exits.
   - **If we skip it:** Users selecting the supported fallback can believe a broken or incomplete video was safely saved. Default multistream finalization already handles mux failure more carefully.

**Should fix**

6. **Downloads wait for a second complete copy of the video** (`frontend/src/main.tsx:1099`).
   - **What this is:** The Download action fetches the full recording, creates a Blob, then clicks a generated link.
   - **Problem:** A multi-hour recording must finish the application's full fetch before a browser download begins, requiring temporary backing storage for the whole file. The code reads the entire response even though the real same-origin file URL is already downloadable.
   - **Fix:** Use a normal download link for real recordings and retain only any demo-specific handling that is needed. Preserve file-range playback.
   - **If we skip it:** Long recordings take unnecessary time and temporary storage to download. Browser memory/storage placement was not benchmarked, so this is not a claim that every byte stays in RAM.

7. **The camera still carries an unused padding pipeline, and its integration test exercises the retired format** (`maix/video_rtsp.py:34`, `maix/video_rtsp.py:45`, `tests/test_camera_rotation.py:31`).
   - **What this is:** Padding and SPS rewriting supported the old 480x640 picture; SPS is the encoded video's size metadata.
   - **Problem:** Whole-tree searches found no caller of `pad_nv21`. Cropping and `trim_padding=True` are used only by the old fixture, while production encodes aligned 768x432 without either operation.
   - **Fix:** Delete the retired helpers/option and make the decode/reconnect fixture use 768x432. Keep exact pixel rotation and packet-fragmentation checks.
   - **If we skip it:** Maintainers keep risky bit-level parsing that current production does not need, while the integration fixture keeps proving a superseded layout.

8. **The initial-setup guide sends installers to the wrong SSH tools** (`docs/docker-run-guide.md:12`, `docs/docker-run-guide.md:36`).
   - **What this is:** The README sends installers to this guide for first-time preparation and recovery.
   - **Problem:** It requires PuTTY `plink`/`pscp` and a PuTTY private key, but current deployment invokes Windows `ssh.exe`/`scp.exe` and passes the key to OpenSSH. An installer following the old prerequisites can still lack the required tools or supply an incompatible key.
   - **Fix:** Replace those instructions with the existing README's OpenSSH workflow and verified host-key requirements. Coordinate the same correction already requested by the pending desktop-setup plan.
   - **If we skip it:** Initial setup and recovery can fail before any camera software is installed.

**Checks and scope**

- `python -m unittest discover -s tests -v`: 141 tests ran, 135 passed and six skipped; exit 0. Skips cover opt-in media integrations and platform/tool-dependent checks.
- `npm test` in `frontend/`: type check, build/package and all 30 source/compiled Playwright checks passed. This refreshed ignored build/test outputs only.
- `docker compose config --quiet`: passed; no image was built or service changed.
- Temporary-file/isolated-loopback probes reproduced findings 1, 3, 4 and 5 without production credentials or media. Finding 2 is a demonstrated source ordering gap, not a live destructive trial. Findings 6-8 follow traced callers/configuration, not performance measurements.
- Read README/build/deploy config and entry points; traced app supervision, operator routes, both recording implementations, browser media/control/persistence, camera RTSP and SCO return/talkback startup. Read relevant failure and integration tests and searched hidden project references while excluding dependencies/build outputs/runtime data.
- The generic browser repository and large React component are not themselves reported as defects. Their working persistence and media cleanup do not justify a broad rewrite. TCP video, SCO calibration, authenticated packets and independent return are deliberate working choices.

Verdict: Keep the working pipeline. Repair maintenance exclusion, the local HTTP boundary, session cleanup and failure reporting before expanding setup features.

Lean: -80 lines, -0 dependencies possible, approximately, from the retired camera path and real-download buffering. This is gross removable production code, not a promise that the complete safety repair has a negative net diff.

Not checked: Live camera/headset behavior, audible duplex, physical latency or synchronization, long-duration disk/load trials, a full browser DNS-rebinding exploit, first-install/rollback on another laptop, external dependency vulnerability databases, every historical session/measurement utility, or the six skipped tests. No source fixes or runtime deployment were performed.
