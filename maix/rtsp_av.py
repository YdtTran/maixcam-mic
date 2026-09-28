"""Publish MaixCAM camera video over RTSP."""

from maix import app, time, rtsp, camera, image


cam = camera.Camera(640, 480, image.Format.FMT_YVU420SP)

server = rtsp.Rtsp()
print("bind video:", server.bind_camera(cam))
print("start:", server.start())
print("RTSP URL:", server.get_url())

while not app.need_exit():
    time.sleep(1)

del server
del cam
