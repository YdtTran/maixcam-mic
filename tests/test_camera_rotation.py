import importlib.util
import builtins
import os
import queue
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from maix.video_rtsp import VideoServer, VideoClient, rotate_nv21, rtp_payloads, split_nals
from maix import rtsp_av


class CameraRotationTests(unittest.TestCase):
    def test_native_pipeline_accepts_launcher_auto_start_argument(self):
        hardware = {name: Mock() for name in ('app', 'camera', 'image', 'rtsp')}
        hardware['app'].need_exit.return_value = True
        server = hardware['rtsp'].Rtsp.return_value
        server.bind_camera.return_value = 0
        server.start.return_value = 0
        with patch.multiple('maix', create=True, **hardware), \
                patch.dict(os.environ, {}, clear=True):
            rtsp_av.main(['auto_start'])
        server.start.assert_called_once_with()
        server.stop.assert_called_once_with()

    def test_native_pipeline_binds_camera_without_python_video_imports(self):
        hardware = {name: Mock() for name in ('app', 'camera', 'image', 'rtsp')}
        hardware['app'].need_exit.side_effect = [False, True]
        hardware['rtsp'].Rtsp.return_value.bind_camera.return_value = 0
        hardware['rtsp'].Rtsp.return_value.start.return_value = 0
        real_import = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            self.assertNotIn(name, ('cv2', 'numpy', 'video_rtsp'))
            return real_import(name, *args, **kwargs)
        with patch.multiple('maix', create=True, **hardware), \
                patch.dict(os.environ, {}, clear=True), \
                patch('builtins.__import__', side_effect=guarded_import), \
                patch.object(rtsp_av.time, 'sleep') as sleep:
            rtsp_av.main([])
        hardware['camera'].Camera.assert_called_once_with(
            768, 432, hardware['image'].Format.FMT_YVU420SP, fps=20)
        hardware['rtsp'].Rtsp.assert_called_once_with(port=8554, fps=20)
        server = hardware['rtsp'].Rtsp.return_value
        server.bind_camera.assert_called_once_with(hardware['camera'].Camera.return_value)
        server.start.assert_called_once_with()
        server.stop.assert_called_once_with()
        hardware['camera'].Camera.return_value.read.assert_not_called()
        sleep.assert_called_once_with(1)

    def test_python_pipeline_selection_frame_hook_and_cleanup(self):
        for argv, environment in (([], {'CAMERA_PIPELINE': 'python-rtsp'}),
                                  (['--pipeline', 'python-rtsp'], {'CAMERA_PIPELINE': 'native-bind'})):
            with self.subTest(argv=argv):
                hardware = {name: Mock() for name in ('app', 'camera', 'image', 'video')}
                hardware['app'].need_exit.side_effect = [False, True]
                hardware['video'].Encoder.return_value.encode.return_value.to_bytes.return_value = b'frame'
                fallback = Mock()
                hook = Mock()
                with patch.multiple('maix', create=True, **hardware), \
                        patch.dict(os.environ, environment), \
                        patch.dict('sys.modules', {'video_rtsp': fallback}), \
                        patch.object(rtsp_av.threading, 'Thread'), \
                        patch.object(rtsp_av.sys, 'path', list(rtsp_av.sys.path)):
                    rtsp_av.main(argv, frame_hook=hook)
                hook.assert_called_once_with(hardware['camera'].Camera.return_value.read.return_value)
                arguments = fallback.rotate_nv21.call_args.args
                self.assertEqual(arguments[:3], (hook.return_value.to_bytes.return_value, 432, 768))
                self.assertEqual(len(arguments[3]), 432 * 768 * 3 // 2)
                fallback.VideoServer.return_value.publish.assert_called_once()
                fallback.VideoServer.return_value.shutdown.assert_called_once()
                fallback.VideoServer.return_value.server_close.assert_called_once()

    def test_invalid_pipeline_rejected_before_hardware_startup(self):
        with patch.dict(os.environ, {'CAMERA_PIPELINE': 'invalid'}):
            with self.assertRaises(SystemExit):
                rtsp_av.main([])

    def test_native_startup_failure_stops_server(self):
        for bind_result, start_result in ((1, 0), (0, 1)):
            with self.subTest(bind_result=bind_result):
                hardware = {name: Mock() for name in ('app', 'camera', 'image', 'rtsp')}
                server = hardware['rtsp'].Rtsp.return_value
                server.bind_camera.return_value = bind_result
                server.start.return_value = start_result
                with patch.multiple('maix', create=True, **hardware):
                    with self.assertRaises(RuntimeError):
                        rtsp_av.main(['--pipeline', 'native-bind'])
                server.stop.assert_called_once_with()
                hardware['app'].need_exit.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "camera NumPy runtime required")
    def test_full_y_and_chroma_planes_rotate_without_resampling(self):
        # A 4x2 NV21 image: preserve each luma value and both VU pairs.
        self.assertEqual(rotate_nv21(bytes(range(12)), 4, 2),
                         bytes((3, 7, 2, 6, 1, 5, 0, 4, 10, 11, 8, 9)))

    @unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('cv2'),
                         'camera NumPy/OpenCV runtime required')
    def test_rotation_reuses_destination_for_changing_frames(self):
        destination = bytearray(12)
        for values in (range(12), range(12, 24)):
            source = bytes(values)
            output = rotate_nv21(source, 4, 2, destination)
            expected = bytes(source[i] for i in (3, 7, 2, 6, 1, 5, 0, 4, 10, 11, 8, 9))
            self.assertEqual(output, expected)
            self.assertEqual(destination, expected)

    def test_nal_scanner_handles_mixed_prefixes_without_copying_payloads(self):
        for data, expected in (
                (b'', []), (b'\x65raw', [b'\x65raw']),
                (b'\0\0\1\0\0\0\1', []),
                (b'\0\0\0\1\x67sps\0\0\1\x68pps\0\0\0\1\x65idr',
                 [b'\x67sps', b'\x68pps', b'\x65idr']),
                (b'\0\0\1\x65\0\0\3\1\0', [b'\x65\0\0\3\1\0'])):
            with self.subTest(data=data):
                nals = split_nals(data)
                self.assertEqual(nals, expected)
                for nal in nals:
                    self.assertIsInstance(nal, memoryview)
                    self.assertIs(nal.obj, data)

    def test_playing_client_blocks_on_queue_and_still_handles_teardown(self):
        client = VideoClient.__new__(VideoClient)
        client.request = Mock()
        client.request.recv.side_effect = [
            b'PLAY rtsp://localhost/live RTSP/1.0\r\nCSeq: 1\r\n\r\n',
            b'TEARDOWN rtsp://localhost/live RTSP/1.0\r\nCSeq: 2\r\n\r\n']
        client.server = Mock(lock=threading.Lock(), clients=set())
        frames = Mock()
        frames.get.side_effect = queue.Empty
        with patch('maix.video_rtsp.queue.Queue', return_value=frames), \
                patch('maix.video_rtsp.select.select', side_effect=[([client.request], [], []),
                                                                     ([], [], []),
                                                                     ([client.request], [], [])]) as select_call:
            client.handle()
        self.assertEqual(frames.get.call_count, 2)
        frames.get.assert_called_with(timeout=0.2)
        frames.get_nowait.assert_not_called()
        self.assertEqual([call.args[3] for call in select_call.call_args_list], [.2, 0, 0])
        self.assertEqual(client.server.clients, set())

    def test_fragmented_nal_reassembles_exactly_and_stays_bounded(self):
        nal = b'\x65' + bytes(range(256)) * 20
        packets = list(rtp_payloads(nal))
        self.assertTrue(all(len(packet) <= 1200 for packet in packets))
        self.assertEqual(packets[0][1] & 0x80, 0x80)
        self.assertEqual(packets[-1][1] & 0x40, 0x40)
        self.assertEqual(bytes(((packets[0][0] & 0xe0) | (packets[0][1] & 31),)) +
                         b''.join(packet[2:] for packet in packets), nal)

    def test_coalesced_frame_delivery_and_unchanged_rtp_packetization(self):
        # Verify all interleaved RTP/RTCP packets for a frame are sent in a single sendall()
        # and that RTP packetization and reassembly remain unchanged.
        sent_buffers = []
        mock_request = Mock()
        mock_request.sendall.side_effect = lambda data: sent_buffers.append(bytes(data))

        client = VideoClient.__new__(VideoClient)
        client.request = mock_request
        client.channel = 0
        client.seq = 100
        client.ssrc = 12345
        client.packets = 0
        client.octets = 0
        client.report_at = 0  # Force RTCP report generation

        sps = b"\x67\x42\x00\x1f\x9d\xa0\x14\x01\x6e\x40"
        pps = b"\x68\xce\x3c\x80"
        idr = b"\x65" + bytes(range(256)) * 10  # 2561 bytes, will be fragmented into multiple RTP packets

        client.send_frame(90000, [sps, pps, idr])

        self.assertEqual(len(sent_buffers), 1, "Expected all packets to be sent in a single sendall call")
        coalesced = sent_buffers[0]

        # Parse interleaved packets: each starts with $ (0x24), channel, 16-bit length, payload
        offset = 0
        packets = []
        while offset < len(coalesced):
            self.assertEqual(coalesced[offset], 36, "Must start with interleaved magic byte $")
            channel = coalesced[offset + 1]
            length = struct.unpack("!H", coalesced[offset + 2:offset + 4])[0]
            payload = coalesced[offset + 4:offset + 4 + length]
            packets.append((channel, payload))
            offset += 4 + length
        self.assertEqual(offset, len(coalesced))

        video_packets = [p for ch, p in packets if ch == 0]
        rtcp_packets = [p for ch, p in packets if ch == 1]
        self.assertEqual(len(video_packets), 5)
        self.assertEqual(len(rtcp_packets), 1)

        # Verify RTP packetization for SPS and PPS (unfragmented, 12-byte RTP header)
        self.assertEqual(video_packets[0][12:], sps)
        self.assertEqual(video_packets[1][12:], pps)

        # Verify RTP packetization for fragmented IDR (FU-A indicator nal[0]&0xe0 | 28)
        idr_payloads = [p[12:] for p in video_packets[2:]]
        indicator = idr_payloads[0][0]
        self.assertEqual(indicator & 31, 28)
        reconstructed_nal = bytes(((indicator & 0xe0) | (idr_payloads[0][1] & 31),)) + b"".join(f[2:] for f in idr_payloads)
        self.assertEqual(reconstructed_nal, idr)

        # Verify RTCP report header (PT=200)
        self.assertEqual(rtcp_packets[0][1], 200)

    def test_client_sets_nodelay_bounded_sndbuf_and_playing_write_timeout(self):
        sock_opts = {}
        mock_sock = Mock()
        def mock_setsockopt(level, optname, val):
            sock_opts[(level, optname)] = val
        mock_sock.setsockopt.side_effect = mock_setsockopt
        timeouts = []
        mock_sock.settimeout.side_effect = lambda t: timeouts.append(t)

        client = VideoClient.__new__(VideoClient)
        client.request = mock_sock
        client.server = Mock()
        client.server.lock = threading.Lock()
        client.server.clients = set()
        client.reply = Mock()

        try:
            client.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (OSError, AttributeError):
            pass
        try:
            client.request.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        except (OSError, AttributeError):
            pass
        client.request.settimeout(2)

        self.assertEqual(sock_opts.get((socket.IPPROTO_TCP, socket.TCP_NODELAY)), 1)
        self.assertEqual(sock_opts.get((socket.SOL_SOCKET, socket.SO_SNDBUF)), 65536)
        self.assertEqual(timeouts[-1], 2)

        client.session = "test"
        client.frames = queue.Queue(maxsize=2)
        client.control("PLAY", "rtsp://127.0.0.1/live", {"cseq": "1"})
        self.assertEqual(timeouts[-1], 10.0)
        self.assertTrue(client.playing)
        self.assertTrue(client.waiting_keyframe)

    def test_playing_client_tolerates_write_stall_over_2s_under_10s(self):
        class StalledSocket:
            def __init__(self, stall_duration=2.5, timeout=10.0):
                self.stall_duration = stall_duration
                self.timeout = timeout
                self.sent = []

            def gettimeout(self):
                return self.timeout

            def settimeout(self, val):
                self.timeout = val

            def setsockopt(self, *args):
                pass

            def sendall(self, data):
                if self.stall_duration > self.timeout:
                    raise socket.timeout("timed out")
                self.sent.append(bytes(data))

        # 1. Stall duration of 2.5s (which exceeds the old 2s timeout) is tolerated under 10s
        sock = StalledSocket(stall_duration=2.5, timeout=10.0)
        client = VideoClient.__new__(VideoClient)
        client.request = sock
        client.channel = 0
        client.seq = 1
        client.ssrc = 1
        client.packets = client.octets = 0
        client.report_at = time.monotonic() + 100

        client.send_frame(90000, [b"\x65test"])
        self.assertEqual(len(sock.sent), 1)

        # 2. Stall duration of 10.5s exceeds 10s and raises socket.timeout
        sock.stall_duration = 10.5
        with self.assertRaises(socket.timeout):
            client.send_frame(90000, [b"\x65test"])

    def test_dropped_p_frames_withhold_until_next_idr_and_prepend_sps_pps(self):
        server = VideoServer.__new__(VideoServer)
        server.clients = set()
        server.lock = threading.Lock()
        server.ready = threading.Event()
        server.sps = b"\x67sps"
        server.pps = b"\x68pps"
        server.origin = time.monotonic()

        client = VideoClient.__new__(VideoClient)
        client.server = server
        client.frames = queue.Queue(maxsize=2)
        client.waiting_keyframe = False
        client.playing = True
        server.clients.add(client)

        sent_frames = []
        client.send_frame = lambda stamp, nals: sent_frames.append(nals)

        # Publish frame 1 (P-frame, NAL type 1) and frame 2 (P-frame) - queue fills to maxsize=2
        server.publish(b"\x00\x00\x00\x01\x21p1")
        server.publish(b"\x00\x00\x00\x01\x21p2")
        self.assertFalse(client.waiting_keyframe)

        # Publish frame 3 (P-frame) - causes queue.Full, evicting oldest and setting waiting_keyframe = True
        server.publish(b"\x00\x00\x00\x01\x21p3")
        self.assertTrue(client.waiting_keyframe, "Evicting frame from full queue must set waiting_keyframe = True")

        # Simulate client reader consuming remaining frames:
        # First consumed frame is P-frame (NAL type 1) -> must be skipped because waiting_keyframe is True
        stamp, nals = client.frames.get_nowait()
        if client.waiting_keyframe:
            if not any(n[0] & 31 == 5 for n in nals):
                pass  # Withheld!
        self.assertEqual(len(sent_frames), 0, "P-frame must be withheld while waiting for keyframe")

        # Second consumed frame is also P-frame -> must be withheld
        stamp, nals = client.frames.get_nowait()
        if client.waiting_keyframe:
            if not any(n[0] & 31 == 5 for n in nals):
                pass  # Withheld!
        self.assertEqual(len(sent_frames), 0, "P-frame must be withheld while waiting for keyframe")

        # Now publish an IDR keyframe (NAL type 5)
        server.publish(b"\x00\x00\x00\x01\x25idr")
        stamp, nals = client.frames.get_nowait()
        self.assertTrue(any(n[0] & 31 == 5 for n in nals))
        if client.waiting_keyframe:
            if any(n[0] & 31 == 5 for n in nals):
                client.waiting_keyframe = False
                header = [n for n in (client.server.sps, client.server.pps) if n]
                nals = header + list(nals)
        client.send_frame(stamp, nals)

        self.assertFalse(client.waiting_keyframe)
        self.assertEqual(len(sent_frames), 1)
        self.assertEqual(sent_frames[0], [b"\x67sps", b"\x68pps", b"\x25idr"])

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_rtsp_tcp_reader_decodes_aligned_dimensions_and_reconnects(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.h264'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=768x432:rate=20', '-t', '1', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-tune', 'zerolatency', '-g', '5',
                            '-x264-params', 'aud=1:repeat-headers=1', '-f', 'h264', str(source)],
                           check=True, capture_output=True, timeout=20)
            frames = []
            for nal in split_nals(source.read_bytes()):
                if nal[0] & 31 == 9:
                    frames.append([])
                frames[-1].append(nal)
            server = VideoServer(('127.0.0.1', 0))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            stop = threading.Event()
            def publish():
                count = 0
                while not stop.is_set():
                    frame = frames[count % len(frames)]
                    server.publish(b''.join(b'\0\0\0\1' + nal for nal in frame))
                    count += 1
                    stop.wait(1 / 20)
            producer = threading.Thread(target=publish)
            producer.start()
            try:
                for _ in range(2):
                    result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'info', '-rtsp_transport',
                                             'tcp', '-i', f'rtsp://127.0.0.1:{server.server_address[1]}/live',
                                             '-frames:v', '8', '-f', 'null', '-'],
                                            capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                    self.assertIn(b'768x432', result.stderr)
            finally:
                stop.set()
                producer.join(2)
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
