# Elevated live deployment and SSH verification — 2026-10-23

The user authorized real paired deployment and requested resolution of SSH
host-key setup, stating commands will run as administrator. Existing working-tree
changes, recordings, camera hardware MAC and fixed headset binding were retained.

## Login, deployment failure and repair

The agent terminal was not elevated. A real USB SSH login using the new automatic
camera credentials succeeded without a prompt. Camera SSID was `P526_5G`, matching
the PC; camera Wi-Fi MAC was `a8:b5:8e:22:37:54`, matching saved configuration.
No stale-key mismatch was observed in this Windows profile, and no known_hosts
entry was removed or replaced. Existing saved keys were accepted on the actual
USB and Wi-Fi paths; changed-key rejection remains enabled.

Launched the existing deployment through Windows UAC using a hidden elevated
PowerShell runner. First run exited 3 before runtime mutation: child Docker
reported `no configuration file provided: not found`. PowerShell had changed to
the project folder, but ProcessStartInfo inherited the elevated process's native
working directory. Fixed this once in `Invoke-NetworkProcess` by explicitly
setting WorkingDirectory to PowerShell's current filesystem location.

Four focused unittest checks passed: changed-directory child execution, argument/
stdin/exit/timeout handling, streamed output, and automatic camera credentials/
helper cleanup. No full application suite was rerun for this one-line helper fix.

## Successful elevated redeployment

Retried the real command through the elevated runner:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy.ps1 -WifiSsid 'P526_5G' -WifiInterfaceIndex 19 -UsbInterfaceIndex 18 -UsbPeerIP 10.172.16.1 -Force -Verbose
```

No Wi-Fi password was needed because the camera already used the required SSID.
The camera installer saved its current Wi-Fi profile before reboot. After reboot,
USB login passed again, `wpa_cli` reported `P526_5G`/COMPLETED at `192.168.1.7`, and
the `/etc` and `/boot` supplicant files had matching SHA256 hashes. The existing
headset binding and SCO profile were retained; microphone destination is PC
`192.168.1.4`. Setup printed and persisted the camera MAC and required SSID.

The firewall rule was verified as enabled, Inbound Allow, UDP 8004/8005, Profile
Any, RemoteAddress `192.168.1.7`. Both PC deployment stages and camera installation/
reboot passed. Final wrapper exit was 0 with both media decodes, TB3 compatibility,
Docker health and Windows HTTP checks passing. Maintenance was released.
Camera backup: `/root/workercam-backup-78f4204c383f4b1e9a86d644a0bebc5a`.
Local backup metadata: `.runtime/deploy-backups/78f4204c383f4b1e9a86d644a0bebc5a/`.
Raw successful transcript: `.runtime/live-admin-deploy.log`.

## Browser and media checks

- Real Chromium showed clear 768x432 live video at 0 and 90 degrees; the portrait
  screenshot was inspected. Rotation was restored to 0 afterwards.
- Talk start/stop signaling passed during a new seven-second multistream capture.
- Retained recording `20261023T020145Z_56211258.mp4`, 2,086,455 bytes: copied H.264
  at 768x432 with a 90-degree display matrix and three AAC tracks. Portrait
  playback, seeking to two seconds and return to clear live video passed.
- Native download matched the original recording SHA256
  `b3f65da631de5c2b1080d56fdd2f0d0fc2a2ccfeeeabcbcf62e52ede4b2f5b91`.
  Byte-range request returned HTTP 206 and the expected 20 bytes.
- Real browser continuity ran 60.164 seconds, decoded 1,201 additional frames
  (19.96 fps), reported zero lost packets and received increasing video/audio
  data at every five-second sample with audio unmuted/playing. No page errors.

Evidence is in `.runtime/ssh-admin-live-ui-result.json`,
`.runtime/ssh-admin-live-{0,90,recording}.png` and
`.runtime/ssh-admin-live-continuity.{json,png}`. Existing verification helpers
were copied to new evidence paths; historical outputs were retained.

## Headset and listening acceptance

After reboot, the headset was disconnected and return decode was silence. The
user powered it on. Automatic reconnect initially logged busy/unknown failures,
then the camera reported connected without a Bluetooth reset or new pairing.
A five-second return sample contained signal (mean -40.0 dBFS, peak -20.4 dBFS).
The SCO capture mixer was unmuted at 100 percent.

A twelve-second browser-path test tone was transmitted after reconnect. The user
confirmed **Tone only**: outbound sound was audible, microphone playback in their
browser was not. The first tone helper failed to activate Talk; a corrected
pointer-held helper waited for live video, then passed Talk start/stop. This was
a test-helper correction, not an application change.

The user spoke during a further sample; receiver output included peaks in the
-16 dBFS band, establishing signal delivery to the PC during that trial. Signal
  peaks alone do not identify intelligible speech; later user acceptance does.
A later background sample was mostly -62 to -71 dBFS, with a -53.5 dBFS interval;
that later quiet sample is not proof of absent speech during the earlier trial.
Asked the user to use Reconnect microphone and Enable audio in their existing
tab. The browser automation connector exposed no user browser surfaces, so the
actual tab state could not be inspected directly. At that stage, audible
microphone listening was still pending; the later acceptance below supersedes it.

Latest measured runtime: Docker healthy, headset connected, TB3 Talk available,
rotation 0, recording idle/not finalizing, no recording error/metadata warnings,
and maintenance null. No headset reset, audio gain change or extra pairing was
performed. Wi-Fi switching to a different SSID, prolonged stability, physical
latency and A/V synchronization remain untested. Known historical rollback
port-format defect was not exercised by the successful rollout.

## PC microphone diagnosis, repair and accepted duplex

On clarification, the user confirmed **Laptop listening works; Talk is silent**
even while holding Talk. The prior injected tone proved the outbound transport,
but did not exercise the actual PC microphone. A visible Chromium capture test
with real devices showed default `Microphone Array (Realtek(R) Audio)` returning
exact zeros for ten seconds. The separate SOUNDPEATS Air6 HS Bluetooth input
returned varying signal, including -21 dBFS RMS samples. The user explicitly
selected **SOUNDPEATS headset microphone** for Talk. Windows already designated
that headset as its communications input.

The first implementation requested `deviceId: { ideal: "communications" }`.
Automated tests passed after fixing a test-only init-script ordering error, and
the PC was rebuilt through UAC. The actual browser nevertheless selected silent
Realtek; this failed live result overrode the automated checks. A real-device
capture with `exact: "communications"` selected SOUNDPEATS and returned signal
around -22 to -30 dBFS RMS.

Final `frontend/src/media.ts` requests the communications input exactly. It
falls back to ordinary default capture only on an OverconstrainedError for
deviceId; permission and other capture errors retain normal failure handling.
No Windows default device, Bluetooth profile, microphone gain or headset bond
was changed. A regression in the existing source/compiled physical-action test
forces the communications device to be absent and verifies default fallback
still establishes and releases Talk. Root README explains the selected input.

Rebuilt/recreated only the PC container again through elevated `deploy_pc.ps1
-Build -Recreate`. Final exit 0; Docker healthy, Windows HTTP and host UDP
listeners verified, firewall scope retained, maintenance released. Camera was
not reinstalled during these two PC-only rebuilds. Final transcript:
`.runtime/live-admin-pc-redeploy.log`; earlier soft-preference rollout transcript:
`.runtime/live-admin-pc-soft-preference.log`.

A real-device browser Talk trial on the deployed build printed
`Communications - Headset (SOUNDPEATS Air6 HS) (Bluetooth)`. The user confirmed
**Yes, speech is audible now** at the EDIFIER earbuds. Together with their prior
laptop-listening confirmation, audible duplex is accepted for this rollout.
The helper's release-button assertion timed out; closing its browser released
its peer. The active input selection and the user's audible result are direct
evidence, not a claim that every helper assertion passed.

During diagnosis the status API briefly reported disconnected while direct HCI
and subsequent Bluetooth checks showed active ACL/eSCO links and connected
status. A clean reconnect was proposed but not executed before the user's
clarification; no radio reset or extra pairing was performed. Cause of that
transient status disagreement remains unproven.

Final checks found Docker healthy, headset connected, TB3 Talk available without
error, rotation/effective rotation 0, recording idle, no metadata warnings and
maintenance null. `/headsetmic` decoded after the final PC rebuild. Earlier
60-second continuity and recording/download results apply to the paired rollout;
they were not repeated after the microphone-only PC update.

Final frontend verification: `npm test` rebuilt/type-checked the interface and
all 44 source/compiled browser checks passed (46.4 seconds). The communications
selection/default-fallback regression passed in both builds. `git diff --check`
passed. No additional deployment is needed for the subsequent documentation and
test-only changes; the final capture implementation is already deployed.
