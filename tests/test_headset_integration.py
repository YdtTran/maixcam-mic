"""Opt-in synthetic integration on isolated ports, never restarts the live stack."""
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import app
from pc.headset_return import receiver_command
from pc.operator_server import RecordingManager, make_handler
from pc.talkback import TalkbackRelay
from pc.talkback_protocol import decode as decode_packet
from maix.talkback_receiver import TalkbackReceiver


def free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(os.environ.get("HEADSET_INTEGRATION") == "1", "set HEADSET_INTEGRATION=1 for isolated real media test")
class HeadsetIntegrationTests(unittest.TestCase):
    def test_independent_pcmu_video_recording_and_talkback(self):
        rtsp, web, ice = free_port(), free_port(), free_port(socket.SOCK_DGRAM)
        rtp = free_port(socket.SOCK_DGRAM)
        root = app.ROOT
        children = []
        with tempfile.TemporaryDirectory() as directory, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            directory = Path(directory)
            udp.bind(("127.0.0.1", 0))
            udp.settimeout(0.2)
            packets = []
            accepted = []
            closing = threading.Event()
            receiver = TalkbackReceiver(duplex=True)
            def collect():
                while not closing.is_set():
                    try:
                        packet = udp.recv(2048)
                        payload = decode_packet(packet)
                        if payload:
                            packets.append(payload)
                            if receiver.accept(packet):
                                accepted.append(payload)
                    except socket.timeout:
                        pass
            collector = threading.Thread(target=collect)
            collector.start()
            config = directory / "mediamtx.yml"
            config.write_text(f"rtspAddress: 127.0.0.1:{rtsp}\nrtspTransports: [tcp]\n"
                              f"webrtcAddress: 127.0.0.1:{web}\nwebrtcLocalUDPAddress: :{ice}\n"
                              "webrtcAdditionalHosts: [127.0.0.1]\nrtmp: false\nhls: false\nsrt: false\nmoq: false\n"
                              "paths:\n  maix01:\n  headsetmic:\n  talkback:\n    overridePublisher: false\n")
            def spawn(command):
                child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                children.append(child)
                return child
            relay = TalkbackRelay(udp.getsockname(), relay_http=f"http://127.0.0.1:{web}",
                                  relay_rtsp=f"rtsp://127.0.0.1:{rtsp}", transport="tcp")
            manager = RecordingManager(directory, source=f"rtsp://127.0.0.1:{rtsp}/maix01", transport="tcp", mode="video", recording_mode="legacy")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(manager, talkback=relay))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                spawn([str(app.media_executable()), str(config)])
                time.sleep(1)
                video = spawn(["ffmpeg", "-nostdin", "-v", "error", "-re", "-f", "lavfi", "-i",
                               "testsrc2=size=320x240:rate=15", "-an", "-c:v", "libx264", "-preset", "ultrafast",
                               "-tune", "zerolatency", "-profile:v", "baseline", "-g", "15", "-f", "rtsp",
                               "-rtsp_transport", "tcp", f"rtsp://127.0.0.1:{rtsp}/maix01"])
                sdp = directory / "mic.sdp"
                sdp.write_text(app.headset_sdp(rtp))
                spawn([arg.replace(":8554/", f":{rtsp}/") for arg in receiver_command(sdp)])
                microphone = spawn(["ffmpeg", "-nostdin", "-v", "error", "-re", "-f", "lavfi", "-i",
                                    "sine=frequency=660:sample_rate=8000", "-ac", "1", "-af", "asetnsamples=n=160:p=0",
                                    "-c:a", "pcm_mulaw", "-pkt_size", "172", "-f", "rtp", f"rtp://127.0.0.1:{rtp}?pkt_size=172"])
                time.sleep(2)
                manager.start()
                result = subprocess.run(["node", "scripts/media-integration.mjs"], cwd=root / "frontend",
                                        env={**os.environ, "OPERATOR_URL": f"http://127.0.0.1:{server.server_port}/operator_test.html",
                                             "WHEP_URL": f"http://127.0.0.1:{web}/maix01/whep", "ASSERT_RETURN_AUDIO": "1",
                                             "SCREENSHOT_PATH": str(root / ".runtime" / "headset-integration.png")},
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                manager.stop()
                recording = manager.recording_path(manager.list_recordings()[0]["id"])
                probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(recording)],
                                       capture_output=True, text=True, timeout=10)
                self.assertEqual([s["codec_type"] for s in json.loads(probe.stdout)["streams"]], ["video"])
                microphone.terminate()
                microphone.wait(timeout=5)
                time.sleep(2)
                self.assertIsNone(video.poll())
                decode = subprocess.run(["ffmpeg", "-v", "error", "-rtsp_transport", "tcp", "-i",
                                         f"rtsp://127.0.0.1:{rtsp}/maix01", "-frames:v", "1", "-f", "null", "-"],
                                        capture_output=True, timeout=10)
                self.assertEqual(decode.returncode, 0, decode.stderr)
                audio = [packet for packet in accepted if packet[0] == "pcm"]
                self.assertGreater(len(audio), 10, relay.error)
                self.assertTrue(all(len(packet[1]) == 320 for packet in audio))
                self.assertTrue(any(packet[0] == "stop" for packet in accepted))
                print(result.stdout.strip())
                print("Video decoded after RTP sender loss; recording contains video only; talkback UDP received")
            finally:
                if manager.status()["recording"]:
                    manager.stop()
                relay.close()
                closing.set()
                collector.join(timeout=2)
                server.shutdown()
                server.server_close()
                thread.join()
                for child in reversed(children):
                    app.stop_process(child)
