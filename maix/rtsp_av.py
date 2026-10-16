"""Publish MaixCAM camera video over RTSP."""

import sys
import threading


def main():
    from maix import app, camera, image, video
    sys.path.insert(0, "/root")
    from video_rtsp import VideoServer, rotate_nv21

    # Keep the camera-side CCW baseline. Capture the inverse dimensions so the
    # complete rotated image is the requested 768x432 (16:9), without resizing.
    cam = camera.Camera(432, 768, image.Format.FMT_YVU420SP)
    encoder = video.Encoder(width=768, height=432, format=image.Format.FMT_YVU420SP,
                            framerate=30, gop=30, bitrate=3000000)
    # 768 is already aligned to the encoder's 64-byte row requirement.
    server = VideoServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print("RTSP /live: full 432x768 capture rotated 90 CCW to 768x432", flush=True)
    try:
        while not app.need_exit():
            original = cam.read()
            pixels = rotate_nv21(original.to_bytes(), 432, 768)
            rotated = image.from_bytes(768, 432, image.Format.FMT_YVU420SP, pixels)
            frame = encoder.encode(rotated)
            if frame and frame.is_valid():
                server.publish(bytes(frame.to_bytes()))
    finally:
        server.shutdown()
        server.server_close()
        del encoder
        del cam


if __name__ == "__main__":
    main()
