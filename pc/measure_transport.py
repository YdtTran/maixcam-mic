"""Isolated, sequential TCP/UDP trials; runtime evidence is never committed.

Uses the existing publisher command unchanged except transport, mode and relay URL.
Physical event measurements must be supplied separately; PTS is not wall-clock time.
"""
import argparse
import json
import math
import os
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import app
from pc.check_camera_udp import check_camera


def distribution(values):
    values = sorted(values)
    return {"samples": len(values), "median": statistics.median(values) if values else None,
            "p95": values[max(0, math.ceil(len(values) * .95) - 1)] if values else None}


def summarize_log(text):
    video_pts = [float(value) for value in re.findall(r"\[Parsed_showinfo[^\n]*?pts_time:([\d.-]+)", text)]
    audio = [(float(pts), int(samples)) for pts, samples in re.findall(
        r"\[Parsed_ashowinfo[^\n]*?pts_time:([\d.-]+)[^\n]*?nb_samples:(\d+)", text)]
    # Decode output is explicitly resampled to 48 kHz for consistent gap accounting.
    audio_gaps = [max(0, (b[0] - a[0] - a[1] / 48000) * 1000) for a, b in zip(audio, audio[1:])]
    return {
        "reported_missing_rtp_packets": sum(map(int, re.findall(r"RTP: missed (\d+) packets", text))),
        "rtp_gap_events": len(re.findall(r"RTP: missed", text)),
        "decode_error_events": len(re.findall(
            r"(?im)^.*(?:corrupt decoded frame|error while decoding|concealing \d+|Invalid NAL unit).*$", text)),
        "reported_corrupt_frame_events": len(re.findall(r"(?i)corrupt decoded frame", text)),
        "queue_warning_events": len(re.findall(
            r"(?im)^.*(?:queue.*blocking|queue.*overflow|buffer.*overrun|max delay reached).*$", text)),
        "non_monotonic_timestamp_events": len(re.findall(r"(?i)non.monoton", text)),
        "ffmpeg_reported_processing_ms": {kind: distribution([float(value) for value in re.findall(
            rf"\[{letter}ost[^\n]*?latency\(total:([\d.]+)ms", text)])
            for kind, letter in (("video", "v"), ("audio", "a"))},
        "ffmpeg_latency_scopes": {kind: sorted(set(re.findall(
            rf"\[{letter}ost[^\n]*?latency\(total:[\d.]+ms, ([a-z-]+):", text)))
            for kind, letter in (("video", "v"), ("audio", "a"))},
        "decoded_video_frames": len(video_pts), "decoded_audio_frames": len(audio),
        "zero_checksum_audio_frames": len(re.findall(r"\[Parsed_ashowinfo[^\n]*?checksum:00000000", text)),
        "audio_pts_gap_ms": distribution([gap for gap in audio_gaps if gap > 2]),
        "audio_pts_gap_events_over_2ms": sum(gap > 2 for gap in audio_gaps),
        "video_pts_interval_ms": distribution([(b - a) * 1000 for a, b in zip(video_pts, video_pts[1:])]),
        "av_first_pts_offset_ms": (video_pts[0] - audio[0][0]) * 1000 if video_pts and audio else None,
        "physical_av_sync_ms": None, "end_to_end_latency_ms": distribution([]),
    }


def decode_command(url, transport, mode, seconds):
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info", "-nostats",
               "-rtsp_transport", transport, "-timeout", "5000000", "-i", url, "-t", str(seconds)]
    if mode != "audio":
        command += ["-map", "0:v:0", "-vf", "showinfo"]
    if mode != "video":
        command += ["-map", "0:a:0", "-af", "aresample=48000,ashowinfo"]
    return command + ["-f", "null", "-"]


def run_trial(args, transport, mode, index, directory):
    prefix = directory / f"{index:02d}-{transport}-{mode}"
    result = {"transport": transport, "mode": mode, "started_utc": datetime.now(timezone.utc).isoformat(),
              "conditions": args.conditions, "duration_requested_seconds": args.seconds}
    # This also records failures rather than interpreting a TCP connect as media support.
    if mode != "audio":
        result["camera_capability"] = check_camera(args.maix_ip, transport=transport)
        if not result["camera_capability"]["verified"]:
            result["status"] = "camera_media_unavailable"
            return result
    if mode != "video":
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            audio_probe = subprocess.run(["ffprobe", "-v", "error", "-rtsp_transport", transport,
                "-timeout", "1000000", "-show_entries", "stream=codec_type", "-of", "json", args.audio_url],
                capture_output=True, text=True, timeout=5)
            if audio_probe.returncode == 0 and '"audio"' in audio_probe.stdout:
                break
            time.sleep(.5)
        else:
            result["status"] = "audio_source_unavailable"
            result["error"] = audio_probe.stderr.strip()
            return result
    command = app.publisher_command(args.maix_ip, transport=transport, mode=mode)
    if args.debug_ts:
        command[command.index("-loglevel") + 1] = "verbose"
        command.insert(1, "-debug_ts")
    command = [arg.replace("rtsp://127.0.0.1:8554/headsetmic", args.audio_url)
               .replace("rtsp://127.0.0.1:8554/maix01", "rtsp://127.0.0.1:18554/maix01") for arg in command]
    result["publisher_command"] = command
    with prefix.with_suffix(".publisher.log").open("wb") as log:
        publisher = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        started = time.monotonic()
        try:
            # Readiness delay is startup, not steady-state source-to-screen latency.
            deadline = started + 15
            while time.monotonic() < deadline and publisher.poll() is None:
                probe = subprocess.run(["ffprobe", "-v", "error", "-rtsp_transport", transport,
                                        "-timeout", "1000000", "-show_entries", "stream=codec_type",
                                        "-of", "json", "rtsp://127.0.0.1:18554/maix01"],
                                       capture_output=True, text=True, timeout=5)
                expected = {"video", "audio"} if mode == "combined" else {mode}
                if probe.returncode == 0:
                    types = {stream.get("codec_type") for stream in json.loads(probe.stdout).get("streams", [])}
                    if expected <= types:
                        break
                time.sleep(.2)
            else:
                result["status"] = "publisher_unavailable"
                return result
            result["startup_to_relay_ready_seconds"] = time.monotonic() - started
            browser = None
            if args.browser:
                browser_log = prefix.with_suffix(".browser.json").open("wb")
                browser = subprocess.Popen(["node", "scripts/measure-webrtc.mjs"], cwd=app.ROOT / "frontend",
                    stdout=browser_log, stderr=subprocess.STDOUT, env={**os.environ,
                    "WHEP_URL": "http://127.0.0.1:18889/maix01/whep", "STREAM_MODE": mode,
                    "MEASURE_SECONDS": str(args.seconds)})
            try:
                decoder_log = prefix.with_suffix(".decoder.log")
                with decoder_log.open("wb") as output:
                    decoder_started = time.monotonic()
                    try:
                        decoded = subprocess.run(decode_command("rtsp://127.0.0.1:18554/maix01", transport,
                                                mode, args.seconds), stdout=subprocess.DEVNULL, stderr=output,
                                                timeout=args.seconds + 15)
                        result["decoder_exit_code"] = decoded.returncode
                    except subprocess.TimeoutExpired:
                        result["decoder_exit_code"] = None
                        result["decoder_timed_out"] = True
                    result["decoder_wall_seconds"] = time.monotonic() - decoder_started
                result["decoder"] = summarize_log(decoder_log.read_text(errors="replace"))
                result["status"] = "measured" if result["decoder_exit_code"] == 0 else "decode_failed"
            finally:
                if browser:
                    try:
                        browser.wait(timeout=25)
                    except subprocess.TimeoutExpired:
                        app.stop_process(browser)
                    browser_log.close()
                    result["browser_exit_code"] = browser.returncode
                    if browser.returncode:
                        result["status"] = "browser_media_failed"
                    result["browser_evidence"] = str(prefix.with_suffix(".browser.json"))
        finally:
            app.stop_process(publisher)
            log.flush()
            result["publisher"] = summarize_log(prefix.with_suffix(".publisher.log").read_text(errors="replace"))
            prefix.with_suffix(".result.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maix-ip", default=os.environ.get("MAIX_IP", "192.168.1.7"))
    parser.add_argument("--audio-url", default="rtsp://127.0.0.1:8554/headsetmic")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--modes", nargs="+", choices=("video", "audio", "combined"), default=["video", "audio", "combined"])
    parser.add_argument("--transports", nargs="+", choices=("tcp", "udp"), default=["udp", "tcp"])
    parser.add_argument("--conditions", required=True, help="Wi-Fi band/AP, placement, traffic and device settings")
    parser.add_argument("--browser", action="store_true", help="Collect Chromium getStats alongside decoding")
    parser.add_argument("--debug-ts", action="store_true", help="Retain publisher demux/encode/mux timestamp traces")
    parser.add_argument("--event-samples", type=Path, help="JSON: stage name -> measured delays in milliseconds")
    parser.add_argument("--output", type=Path, default=app.ROOT / ".runtime" / "transport-measurements")
    args = parser.parse_args()
    if args.seconds < 1 or args.repeats < 1:
        parser.error("seconds and repeats must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    config = args.output / "mediamtx.yml"
    config.write_text("rtspTransports: [udp, tcp]\nrtspAddress: 0.0.0.0:18554\n"
        "rtpAddress: 0.0.0.0:19002\nrtcpAddress: 0.0.0.0:19003\n"
        "webrtcAddress: 127.0.0.1:18889\nwebrtcLocalUDPAddress: 0.0.0.0:18189\n"
        "webrtcLocalTCPAddress: ''\nwebrtcIPsFromInterfaces: true\nwebrtcAdditionalHosts: [127.0.0.1]\n"
        "rtmp: false\nhls: false\nsrt: false\nmoq: false\npaths:\n  maix01:\n    source: publisher\n"
        "  headsetmic:\n    source: publisher\n")
    results = []
    with (args.output / "mediamtx.log").open("wb") as log:
        # No inherited listener overrides; never stop the production supervisor.
        relay = subprocess.Popen([str(app.media_executable()), str(config)], stdout=log, stderr=log,
                                 env={k: v for k, v in os.environ.items() if not k.startswith("MTX_")})
        try:
            time.sleep(1)
            if relay.poll() is not None:
                raise RuntimeError("Isolated MediaMTX failed; inspect mediamtx.log for a port conflict")
            for repeat in range(args.repeats):
                transports = args.transports if repeat % 2 == 0 else list(reversed(args.transports))
                for mode in args.modes:
                    for transport in transports:
                        print(f"Trial {len(results) + 1}: {transport}/{mode}", flush=True)
                        results.append(run_trial(args, transport, mode, len(results) + 1, args.output))
                        (args.output / "results.json").write_text(json.dumps(results, indent=2))
            if args.event_samples:
                samples = json.loads(args.event_samples.read_text())
                measured = {stage: distribution(values) for stage, values in samples.items()}
                (args.output / "physical-events.json").write_text(json.dumps(measured, indent=2))
        finally:
            app.stop_process(relay)
    print(str(args.output / "results.json"))


if __name__ == "__main__":
    main()
