import importlib.util
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from maix.video_rtsp import VideoServer, rotate_nv21, rtp_payloads, split_nals, crop_encoder_padding


class CameraRotationTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("numpy"), "camera NumPy runtime required")
    def test_full_y_and_chroma_planes_rotate_without_resampling(self):
        # A 4x2 NV21 image: preserve each luma value and both VU pairs.
        self.assertEqual(rotate_nv21(bytes(range(12)), 4, 2),
                         bytes((3, 7, 2, 6, 1, 5, 0, 4, 10, 11, 8, 9)))

    def test_fragmented_nal_reassembles_exactly_and_stays_bounded(self):
        nal = b'\x65' + bytes(range(256)) * 20
        packets = list(rtp_payloads(nal))
        self.assertTrue(all(len(packet) <= 1200 for packet in packets))
        self.assertEqual(packets[0][1] & 0x80, 0x80)
        self.assertEqual(packets[-1][1] & 0x40, 0x40)
        self.assertEqual(bytes(((packets[0][0] & 0xe0) | (packets[0][1] & 31),)) +
                         b''.join(packet[2:] for packet in packets), nal)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_rtsp_tcp_reader_decodes_rotated_dimensions_and_reconnects(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.h264'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=512x640:rate=15', '-t', '1', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-tune', 'zerolatency', '-g', '5',
                            '-x264-params', 'aud=1:repeat-headers=1', '-f', 'h264', str(source)],
                           check=True, capture_output=True, timeout=20)
            frames = []
            for nal in split_nals(source.read_bytes()):
                if nal[0] & 31 == 9:
                    frames.append([])
                frames[-1].append(nal)
            # Display cropping removes only hardware padding, preserving every
            # visible decoded pixel. Compare against the same 512-wide decode.
            cropped = Path(directory) / 'visible.h264'
            cropped.write_bytes(b''.join(b'\0\0\0\1' + (crop_encoder_padding(n) if n[0] & 31 == 7 else n)
                                         for n in split_nals(source.read_bytes())))
            def decode(path, filters):
                return subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), *filters,
                                       '-frames:v', '1', '-pix_fmt', 'yuv420p', '-f', 'rawvideo', '-'],
                                      check=True, capture_output=True, timeout=10).stdout
            self.assertEqual(decode(cropped, []), decode(source, ['-vf', 'crop=480:640:0:0']))
            server = VideoServer(('127.0.0.1', 0), trim_padding=True)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            stop = threading.Event()
            def publish():
                count = 0
                while not stop.is_set():
                    frame = frames[count % len(frames)]
                    server.publish(b''.join(b'\0\0\0\1' + nal for nal in frame))
                    count += 1
                    stop.wait(1 / 15)
            producer = threading.Thread(target=publish)
            producer.start()
            try:
                for _ in range(2):
                    result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'info', '-rtsp_transport',
                                             'tcp', '-i', f'rtsp://127.0.0.1:{server.server_address[1]}/live',
                                             '-frames:v', '8', '-f', 'null', '-'],
                                            capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                    self.assertIn(b'480x640', result.stderr)
            finally:
                stop.set()
                producer.join(2)
                server.shutdown()
                server.server_close()
