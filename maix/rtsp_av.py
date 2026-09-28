"""Publish MaixCAM camera video and microphone audio over RTSP."""

from maix import app, time, rtsp, camera, image, audio


cam = camera.Camera(640, 480, image.Format.FMT_YVU420SP)

mic = audio.Recorder(
    sample_rate=48000,
    format=audio.Format.FMT_S16_LE,
    channel=1,
)
mic.volume(100)

server = rtsp.Rtsp()
print("bind video:", server.bind_camera(cam))
print("bind audio:", server.bind_audio_recorder(mic))
print("start:", server.start())
print("RTSP URL:", server.get_url())

while not app.need_exit():
    time.sleep(1)

del server
del mic
del cam
