# MaixCAM RTSP operator

This project relays MaixCAM video and a selected Bluetooth headset microphone to a local web operator page. The PC side runs in one Docker container with MediaMTX, FFmpeg, recording, and the operator server. MaixCAM keeps its camera and Bluetooth programs on the physical device.

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
├── Dockerfile            PC server image
├── compose.yaml          PC server deployment
├── app.py                PC server supervisor
├── upload_maix.ps1       PuTTY upload script for camera programs and token
└── mediamtx.yml
```

## Run the PC server with Docker

Install Docker Desktop with Linux containers. The cloned project includes the talkback token used by the already configured MaixCAM. From the project root, run:

```powershell
docker compose up --build -d
```

Open `http://127.0.0.1:8000/operator_test.html` and click **Connect**. Docker publishes RTSP port 8554 to the laptop network so MaixCAM can send `/air6mic`; the page, WHEP port 8889, and WebRTC UDP port 8189 are available on the laptop's loopback interface. The container reads `.talkback_token` without copying it into the image and saves MP4 files in the host's `recordings/` folder. Set `MAIX_IP` before `docker compose up` if the camera IP differs from `10.127.15.230`.

The publisher takes video from `rtsp://<MaixIp>:8554/live` and headset microphone audio from MediaMTX's `/air6mic` path, then publishes the combined `/maix01` stream. The operator page derives its WHEP address from the browser host. The container restarts automatically if it exits; the supervisor also restarts FFmpeg when the input stream drops. Use `docker compose logs -f` to inspect it and `docker compose down` to stop it. Stop any earlier `python app.py` process before starting Docker because both use the same ports.

To run the PC side without Docker on Windows, keep `mediamtx.exe` beside `app.py`, install FFmpeg on `PATH`, and run `python app.py`. This is an alternative to Compose, not an additional service.

**Start Recording** saves MP4 files to `recordings/` under this project root, regardless of the terminal's current directory. Video is copied as H.264; audio is converted from Opus to AAC. Stop recording to finalize the file before playback. The UI reports a relative storage path such as `recordings/20260917T054224Z_be738304.mp4`. To choose another directory, pass `--recordings <relative-path>`; relative paths are resolved from the project root.

The publisher and recorder remove empty H.264 NAL units emitted by this MaixCAM. The Docker image includes FFmpeg and the same `app.py` supervisor. Run the tests with `python -m unittest discover -s tests -v`.

## MaixCAM program

`maix/rtsp_av.py` supplies 640 × 480 camera video to the PC publisher; it does not capture the built-in microphone. `maix/air6_mic_stream.py` captures the selected headset's microphone through BlueALSA and publishes it to `rtsp://10.127.9.237:8554/air6mic`. If the laptop IP changes, update `--target` in `maix/background_services.rc.local` and reinstall that boot script. The headset microphone must support the 8 kHz hands-free profile and stereo playback. While Hold to Talk is pressed, MaixCAM pauses headset mic capture, plays PC audio through its stereo profile, and publishes silence on `/air6mic` so the video stream stays live. Headset mic capture resumes on release.

For two-way voice, copy `maix/talkback_receiver.py`, `maix/soundpeats_auto.py`, `maix/bluetooth_control.py`, and `maix/air6_mic_stream.py` to the camera. `soundpeats_auto.py` runs the authenticated Bluetooth control service on TCP 8765. It does not connect to a headset at startup. In the operator page, put the headset in pairing mode, click **Scan**, choose it from the list, then click **Use device** to connect and route microphone and playback through BlueALSA. The active selection is kept in `/run/bluetooth_device` and clears on reboot, so each session requires an explicit choice. The list includes nearby devices reported during the scan and devices BlueZ already knows. Devices that are not discoverable cannot appear in a live scan. Until a device is selected, `/air6mic` carries silence. The receiver already starts from `/etc/rc.local`; do not start a second copy on UDP 9002. The boot script sets `HOME=/root` so ALSA can read `/root/.asoundrc`.

The PC operator reads the repository's `.talkback_token`, while the camera receiver and Bluetooth control service read `/root/.talkback_token`. They must contain the same value. The repository also includes `auto.key`; Docker does not use it. Hold **Hold to Talk** while speaking; release it to stop. If talkback is unavailable, check `GET /api/talkback/status`, the camera's UDP port 9002, and its receiver log. If device scanning fails, check TCP 8765 connectivity and `/root/soundpeats-auto.log` on the camera.

The operator server serves the page, recording API, talkback API, Bluetooth control API, and MP4 files. `app.py` runs that server as part of the host stack.

## Copy and run on MaixCAM (10.127.15.230)

For a new or reset MaixCAM, install PuTTY and put `plink` and `pscp` on `PATH`. From PowerShell on the laptop, upload the MaixCAM programs, app metadata, background startup template, and included token. The script uses the project root for source files even if launched from another directory. The MaixCAM root password is `root` on this device. An already configured camera needs no repeat upload.

```powershell
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

After boot, `rtsp://10.127.15.230:8554/live` should serve camera video, UDP 9002 should have one talkback receiver, and `/root/air6-mic-stream.log` should show the headset mic publisher retrying until the laptop relay starts. Do not launch duplicate copies in SSH terminals. If manual connection fails, put the headset in pairing mode and select it again. To disable RTSP auto-start, remove `/maixapp/auto_start.txt` and reboot. To restore the original background startup file, copy `/etc/rc.local.maixcam-original` back to `/etc/rc.local` and reboot. A firmware reflash changes the SSH host key, so verify the new fingerprint before using these commands.
