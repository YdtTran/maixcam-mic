# MaixCAM RTSP operator

This project relays MaixCAM video and SOUNDPEATS Air6 HS microphone audio to a local web operator page. The PC can record the relay as MP4 and send microphone talkback audio to the earbuds through MaixCAM.

## Directory layout

```text
maix-cam-server/
├── maix/                 MaixCAM programs
│   ├── rtsp_av.py         Camera video RTSP publisher
│   ├── soundpeats_auto.py
│   ├── air6_mic_stream.py  Air6 HS mic publisher to laptop MediaMTX
│   ├── talkback_receiver.py
│   ├── rtsp_app.yaml       Maix app metadata for RTSP auto-start
│   └── background_services.rc.local
├── pc/                   Windows operator and relay scripts
│   ├── operator_server.py
│   ├── operator_test.html
│   ├── run_publisher.ps1
│   └── talkback.py
├── recordings/           MP4 files and recording metadata
├── tests/
├── app.py                One-command Windows host entry point
├── upload_maix.ps1       PuTTY upload script for camera programs and token
├── mediamtx.exe
└── mediamtx.yml
```

After the MaixCAM setup below, run one command **from the project root on the Windows laptop**:

```powershell
python app.py
```

`app.py` stops previous copies of this project's MediaMTX relay, publisher, and operator server, then starts the included `mediamtx.exe`, a new FFmpeg publisher, and the operator server; Ctrl+C stops them. It leaves unrelated processes alone. Keep `mediamtx.exe`, `mediamtx.yml`, and the `pc/` files beside `app.py`. FFmpeg must be installed and available on `PATH` for publishing and recording. The default camera IP is `10.127.15.230`; use `python app.py --maix-ip <camera-ip>` if it changes. Startup waits up to 30 seconds for the MaixCAM Air6 HS microphone publisher, and the host restarts its FFmpeg publisher if the input stream drops.

Open `http://127.0.0.1:8000/operator_test.html` on the laptop and click **Connect**. The publisher takes video from `rtsp://<MaixIp>:8554/live` and Air6 HS microphone audio from MediaMTX's `/air6mic` path, then publishes the combined `/maix01` stream. The operator page derives its WHEP address from the browser host. The operator server binds to `127.0.0.1` by default so the browser can use its microphone; `--bind-host` selects another interface if needed.

**Start Recording** saves MP4 files to `recordings/` under this project root, regardless of the terminal's current directory. Video is copied as H.264; audio is converted from Opus to AAC. Stop recording to finalize the file before playback. The UI reports a relative storage path such as `recordings/20260917T054224Z_be738304.mp4`. To choose another directory, pass `--recordings <relative-path>`; relative paths are resolved from the project root.

The publisher and recorder remove empty H.264 NAL units emitted by this MaixCAM. Start the host with `app.py` to keep that filtering in place. FFmpeg and ffprobe 9.0.1 were used to validate the stream. Run the tests with `python -m unittest discover -s tests -v`.

## MaixCAM program

`maix/rtsp_av.py` supplies 640 × 480 camera video to the PC publisher; it does not capture the built-in microphone. `maix/air6_mic_stream.py` captures the earbuds' microphone through BlueALSA and publishes it to `rtsp://10.127.9.237:8554/air6mic`. If the laptop IP changes, update `--target` in `maix/background_services.rc.local` and reinstall that boot script. The headset microphone uses the 8 kHz hands-free profile. While Hold to Talk is pressed, MaixCAM pauses headset mic capture, plays PC audio through the Air6 HS stereo profile, and publishes silence on `/air6mic` so the video stream stays live. Earbud mic capture resumes on release.

For two-way voice, copy `maix/talkback_receiver.py`, `maix/soundpeats_auto.py`, and `maix/air6_mic_stream.py` to the camera. The configured MAC `28:52:E0:16:73:CE` is the SOUNDPEATS Air6 HS. `soundpeats_auto.py` enables its hands-free profile for mic capture and routes playback through its stereo profile. Put them in pairing mode for the first connection. The receiver already starts from `/etc/rc.local`; do not start a second copy on UDP 9002. The boot script sets `HOME=/root` so ALSA can read `/root/.asoundrc`.

The PC operator reads `.talkback_token` from the project root, while the camera receiver reads `/root/.talkback_token`. These files must contain the same secret and must not be committed. Hold **Hold to Talk** while speaking; release it to stop. If talkback is unavailable, check `GET /api/talkback/status`, the camera's UDP port 9002, and its receiver log.

The operator server serves only the page, recording API, talkback API, and MP4 files. `app.py` runs that server as part of the host stack.

## Copy and run on MaixCAM (10.127.15.230)

Install PuTTY and put `plink` and `pscp` on `PATH`. From PowerShell on the laptop, create the shared token if needed, then upload the MaixCAM programs, app metadata, background startup template, and token. The script uses the project root for source files even if launched from another directory. The MaixCAM root password is `root` on this device. If `.talkback_token` already exists and matches the camera, keep it instead of generating a new one.

```powershell
if (-not (Test-Path .talkback_token)) { python -c "import secrets; print(secrets.token_hex(16))" | Set-Content .talkback_token }
./upload_maix.ps1 -MaixHost 10.127.15.230 -Password root -HostKey 'SHA256:MMjQMht0IcoEBBkw5OVPuwa2wrbSHpiEYHn27tdGcmY'
```

PuTTY batch mode needs a trusted host key. The `-HostKey` value above pins the fingerprint reported by your MaixCAM; check it again if the device's SSH key changes. You can use `-KeyPath` instead of `-Password` if SSH key authentication is configured. The script validates all files before upload and checks each remote command. It uploads files only; restart the MaixCAM programs after updating them. If Windows blocks the script as unsigned, run `Set-ExecutionPolicy -Scope Process Bypass` in that terminal first.

Use the Maix [app auto-start mechanism](https://en.wiki.sipeed.com/maixpy/doc/en/basic/auto_start.html) for RTSP. The built-in `rtsp_stream` app fails on this device because it tries to open a touchscreen, so install the supplied touchscreen-free app. These commands do not edit `/etc/init.d`:

```powershell
plink -batch -hostkey 'SHA256:MMjQMht0IcoEBBkw5OVPuwa2wrbSHpiEYHn27tdGcmY' -pw root root@10.127.15.230 'mkdir -p /maixapp/apps/maix_rtsp && cp /root/rtsp_av.py /maixapp/apps/maix_rtsp/main.py && cp /root/rtsp_app.yaml /maixapp/apps/maix_rtsp/app.yaml && python3 /maixapp/apps/gen_app_info.py /maixapp/apps && printf maix_rtsp > /maixapp/auto_start.txt'
```

For Bluetooth and talkback, back up the current `/etc/rc.local`, then copy the supplied template. It starts only background audio processes; the camera stays under the app launcher:

```powershell
plink -batch -hostkey 'SHA256:MMjQMht0IcoEBBkw5OVPuwa2wrbSHpiEYHn27tdGcmY' -pw root root@10.127.15.230 'cp -p /etc/rc.local /etc/rc.local.maixcam-original && cp /root/background_services.rc.local /etc/rc.local && sh -n /etc/rc.local && reboot'
```

After boot, `rtsp://10.127.15.230:8554/live` should serve camera video, UDP 9002 should have one talkback receiver, and `/root/air6-mic-stream.log` should show the Air6 HS mic publisher retrying until the laptop relay starts. Do not launch duplicate copies in SSH terminals. The Bluetooth helper retries pairing; put the earbuds in pairing mode if `/root/soundpeats-auto.log` says the device is unavailable. To disable RTSP auto-start, remove `/maixapp/auto_start.txt` and reboot. To restore the original background startup file, copy `/etc/rc.local.maixcam-original` back to `/etc/rc.local` and reboot. A firmware reflash changes the SSH host key, so verify the new fingerprint before using these commands.
