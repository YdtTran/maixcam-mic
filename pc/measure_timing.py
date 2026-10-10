"""Measure decoded arrival-time drift against RTP-derived PTS at an RTSP stage.

This measures growth in delay, NOT absolute source-to-screen latency. Use the
same decoder settings when comparing the camera and MediaMTX outputs.
"""
import argparse
import json
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

from pc.measure_transport import distribution
from app import stop_process


def summarize(samples):
    if not samples:
        return {"frames": 0, "relative_arrival_minus_pts_ms": distribution([]), "drift_ms_per_second": None}
    first = samples[0]
    values = [(s["arrival_seconds"] - first["arrival_seconds"] - s["pts_seconds"] + first["pts_seconds"]) * 1000
              for s in samples]
    elapsed = samples[-1]["arrival_seconds"] - first["arrival_seconds"]
    return {"frames": len(samples), "relative_arrival_minus_pts_ms": distribution(values),
            "drift_ms_per_second": values[-1] / elapsed if elapsed > 0 else None,
            "first_pts_seconds": first["pts_seconds"], "last_pts_seconds": samples[-1]["pts_seconds"],
            "wall_interval_seconds": elapsed, "absolute_latency_ms": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--transport", choices=("tcp", "udp"), required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("seconds must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info", "-nostats",
               "-rtsp_transport", args.transport, "-timeout", "5000000", "-max_delay", "100000",
               "-buffer_size", "4194304", "-reorder_queue_size", "512",
               "-fflags", "nobuffer", "-flags", "low_delay", "-analyzeduration", "1000000",
               "-probesize", "1000000", "-i", args.url, "-map", "0:v:0", "-an",
               "-vf", "showinfo", "-t", str(args.seconds), "-f", "null", "-"]
    events = queue.Queue()
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    def read():
        for line in process.stderr:
            events.put((time.monotonic() - started, line))
        events.put(None)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    samples = []
    try:
        with (args.output / "decoder.log").open("w") as log:
            while time.monotonic() - started < args.seconds + 15:
                try:
                    event = events.get(timeout=.2)
                except queue.Empty:
                    continue
                if event is None:
                    break
                arrival, line = event
                log.write(line)
                match = re.search(r"\[Parsed_showinfo[^\n]*?pts_time:([\d.-]+)", line)
                if match:
                    samples.append({"arrival_seconds": arrival, "pts_seconds": float(match[1])})
    finally:
        stop_process(process)
        reader.join(timeout=1)
        process.stderr.close()
    result = {"url": args.url, "transport": args.transport, "command": command,
              "summary": summarize(samples), "samples": samples}
    (args.output / "timing.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result["summary"], indent=2))
    raise SystemExit(0 if samples else 1)


if __name__ == "__main__":
    main()
