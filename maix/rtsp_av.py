"""Publish MaixCAM camera video over RTSP."""

import argparse
import os
import sys
import threading
import time


def main(argv=None, frame_hook=None):
    """Run video; an optional Python-mode hook returns the image to encode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('launch_mode', nargs='?', choices=('auto_start',), help=argparse.SUPPRESS)
    parser.add_argument('--pipeline', choices=('native-bind', 'python-rtsp'),
                        default=os.environ.get('CAMERA_PIPELINE', 'native-bind'))
    args = parser.parse_args(argv)
    if args.pipeline not in ('native-bind', 'python-rtsp'):
        parser.error('invalid CAMERA_PIPELINE')
    from maix import app, camera, image
    if args.pipeline == 'native-bind':
        from maix import rtsp
        cam = camera.Camera(768, 432, image.Format.FMT_YVU420SP, fps=20)
        server = rtsp.Rtsp(port=8554, fps=20)
        try:
            if server.bind_camera(cam) != 0:
                raise RuntimeError('RTSP camera binding failed')
            if server.start() != 0:
                raise RuntimeError('RTSP server startup failed')
            print('RTSP /live: native-bound 768x432 at 20 fps', flush=True)
            while not app.need_exit():
                time.sleep(1)
        finally:
            server.stop()
            del server
            del cam
        return

    from maix import video
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
    rotation_buffer = bytearray(432 * 768 * 3 // 2)
    print("RTSP /live: full 432x768 capture rotated 90 CCW to 768x432", flush=True)
    try:
        while not app.need_exit():
            original = cam.read()
            if frame_hook is not None:
                original = frame_hook(original)
            pixels = rotate_nv21(original.to_bytes(), 432, 768, rotation_buffer)
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
