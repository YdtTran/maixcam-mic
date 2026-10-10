"""Opt-in real network test against the isolated MediaMTX fixture in docs/udp-media.md."""
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

from pc.operator_server import RecordingManager, make_handler
from pc.talkback import TalkbackRelay
from pc.talkback_protocol import decode


@unittest.skipUnless(os.environ.get("UDP_INTEGRATION") == "1", "set UDP_INTEGRATION=1 with MediaMTX fixture running")
class UdpIntegrationTests(unittest.TestCase):
    def test_actual_udp_recording_whep_and_whip(self):
        root = Path(__file__).resolve().parents[1]
        transport = os.environ.get("RTSP_TRANSPORT", "udp")
        self.assertIn(transport, ("udp", "tcp"))
        token = b"i" * 16
        with tempfile.TemporaryDirectory() as directory, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.bind(("127.0.0.1", 0))
            udp.settimeout(0.1)
            packets = []
            closing = threading.Event()

            def collect():
                while not closing.is_set():
                    try:
                        packet, _ = udp.recvfrom(2048)
                        payload = decode(packet, token)
                        if payload:
                            packets.append(payload)
                    except socket.timeout:
                        pass

            collector = threading.Thread(target=collect)
            collector.start()
            relay = TalkbackRelay(token, udp.getsockname(), relay_http="http://127.0.0.1:18889",
                                  relay_rtsp="rtsp://127.0.0.1:18554", transport=transport)
            manager = RecordingManager(directory, source="rtsp://127.0.0.1:18554/maix01", transport=transport)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(manager, talkback=relay))
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            publisher = subprocess.Popen([
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-re",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15", "-re",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-profile:v", "baseline", "-g", "15", "-c:a", "libopus", "-ac", "1",
                "-frame_duration", "20", "-f", "rtsp", "-rtsp_transport", transport,
                "rtsp://127.0.0.1:18554/live",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                microphone = subprocess.Popen([
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi",
                    "-i", "sine=frequency=660:sample_rate=8000", "-ac", "1",
                    "-af", "asetnsamples=n=160:p=0", "-c:a", "pcm_mulaw", "-pkt_size", "172",
                    "-f", "rtsp", "-rtsp_transport", transport, "rtsp://127.0.0.1:18554/headsetmic",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1)
                command = [arg.replace(":8554/", ":18554/") for arg in app.publisher_command("127.0.0.1", transport=transport)]
                combined = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                time.sleep(2)
                manager.start()
                result = subprocess.run(["node", "scripts/media-integration.mjs"], cwd=root / "frontend",
                                        env={**os.environ, "OPERATOR_URL": f"http://127.0.0.1:{server.server_port}",
                                             "SCREENSHOT_PATH": str(Path(directory) / "udp-prototype.png")},
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                manager.stop()
                recordings = manager.list_recordings()
                self.assertEqual(len(recordings), 1)
                # Decode frames to prove UDP delivery, not merely SDP negotiation.
                probe = subprocess.run(["ffmpeg", "-v", "error", "-i", str(manager.recording_path(recordings[0]["id"])),
                                        "-t", "1", "-f", "null", "-"], capture_output=True, timeout=10)
                self.assertEqual(probe.returncode, 0, probe.stderr)
                audio = [packet for packet in packets if packet[0] == "pcm"]
                self.assertGreater(len(audio), 10, relay.error)
                self.assertTrue(all(len(packet[1]) == 320 for packet in audio))
                self.assertTrue(any(packet[0] == "stop" for packet in packets))
                print(result.stdout.strip())
                print(f"Received {len(audio)} authenticated 20ms UDP talkback frames; MP4 decoded successfully")
            finally:
                if manager.status()["recording"]:
                    manager.stop()
                relay.close()
                if "combined" in locals():
                    combined.terminate()
                    combined.wait(timeout=5)
                    combined.stderr.close()
                if "microphone" in locals():
                    microphone.terminate()
                    microphone.wait(timeout=5)
                publisher.terminate()
                publisher.wait(timeout=5)
                publisher.stderr.close()
                server.shutdown()
                server.server_close()
                server_thread.join()
                closing.set()
                collector.join()
