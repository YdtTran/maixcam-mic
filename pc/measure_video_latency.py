"""Read original and delayed stopwatches from the SAME desktop capture.

Requires Windows FFmpeg gdigrab and built-in Windows OCR. No app input is sent.
Uncertain/ambiguous readings are rejected and retained as local evidence.
Manual CSV readings are supported when OCR cannot recognize the camera image.
"""
import argparse
import csv
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from pc.measure_transport import distribution


def stopwatch_ms(text):
    # Reject ambiguous multiple timers, invalid fields, or guesses about O/0.
    matches = re.findall(r"(?<!\d)(\d{2}):\s*(\d{2}):\s*(\d{2})[.,]\s*(\d{2})(?!\d)", text)
    if len(matches) != 1:
        raise ValueError("Exactly one HH:MM:SS.hh stopwatch is required")
    hours, minutes, seconds, hundredths = map(int, matches[0])
    if minutes >= 60 or seconds >= 60:
        raise ValueError("Invalid stopwatch fields")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + hundredths * 10


def summarize(samples):
    accepted = [s for s in samples if s.get("latency_ms") is not None]
    drift = None
    if len(accepted) > 1:
        elapsed = accepted[-1]["elapsed_seconds"] - accepted[0]["elapsed_seconds"]
        if elapsed > 0:
            drift = (accepted[-1]["latency_ms"] - accepted[0]["latency_ms"]) / elapsed
    return {"latency_ms": distribution([s["latency_ms"] for s in accepted]),
            "rejected_samples": len(samples) - len(accepted),
            "endpoint_drift_ms_per_second": drift, "samples": samples}


def roi(value):
    try:
        x, y, width, height = map(int, value.split(","))
        if x < 0 or y < 0 or width <= 0 or height <= 0:
            raise ValueError
        return x, y, width, height
    except ValueError:
        raise argparse.ArgumentTypeError("ROI must be x,y,width,height with positive dimensions")


def measure(args):
    args.output.mkdir(parents=True, exist_ok=False)
    samples = []
    started = time.monotonic()
    for index in range(args.samples):
        sample = {"elapsed_seconds": time.monotonic() - started,
                  "utc": datetime.now(timezone.utc).isoformat(), "transport": args.transport,
                  "stage": args.stage, "latency_ms": None}
        image = args.output / f"{index:03d}-screen.png"
        crops = [args.output / f"{index:03d}-{kind}.png" for kind in ("reference", "feed")]
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "gdigrab",
                "-framerate", "1", "-i", "desktop", "-frames:v", "1", "-y", str(image)],
                check=True, capture_output=True, timeout=10)
            # Crop both readings from one capture; no asynchronous screenshot subtraction.
            for crop, region in zip(crops, (args.reference_roi, args.feed_roi)):
                x, y, width, height = region
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(image),
                    "-vf", f"crop={width}:{height}:{x}:{y},scale=iw*2:ih*2", "-frames:v", "1", "-y", str(crop)],
                    check=True, capture_output=True, timeout=10)
            if args.capture_only:
                sample["evidence"] = str(image)
                sample["error"] = "Awaiting manual readings from the saved simultaneous capture"
                samples.append(sample)
                (args.output / "latency.json").write_text(json.dumps(summarize(samples), indent=2))
                with (args.output / "readings.csv").open("w", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow(["elapsed_seconds", "reference", "feed"])
                    writer.writerows([s["elapsed_seconds"], "", ""] for s in samples)
                print(str(image), flush=True)
                if index + 1 < args.samples:
                    time.sleep(max(0, started + (index + 1) * args.interval - time.monotonic()))
                continue
            result = subprocess.run(["powershell.exe", "-NoProfile", "-File",
                str(Path(__file__).with_name("read_stopwatch.ps1")), "-ReferenceImage", str(crops[0]),
                "-FeedImage", str(crops[1])],
                capture_output=True, text=True, timeout=15)
            if result.returncode:
                raise ValueError(result.stderr.strip())
            readings = json.loads(result.stdout)
            sample["ocr_readings"] = readings
            reference = stopwatch_ms(readings[0]["text"])
            feed = stopwatch_ms(readings[1]["text"])
            delay = reference - feed
            if not 0 <= delay <= args.max_delay_ms:
                raise ValueError("Delay outside configured bounds; reset/wrap or OCR error")
            sample.update(reference_ms=reference, feed_ms=feed, latency_ms=delay)
        except (ValueError, OSError, subprocess.SubprocessError, IndexError) as error:
            sample["error"] = str(error)
        samples.append(sample)
        (args.output / "latency.json").write_text(json.dumps(summarize(samples), indent=2))
        print(json.dumps(sample), flush=True)
        if index + 1 < args.samples:
            time.sleep(max(0, started + (index + 1) * args.interval - time.monotonic()))
    return summarize(samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-roi", type=roi)
    parser.add_argument("--feed-roi", type=roi)
    parser.add_argument("--transport", required=True, choices=("tcp", "udp"))
    parser.add_argument("--stage", required=True, help="direct-camera / relay-rtsp / browser, with mode")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--max-delay-ms", type=int, default=60000)
    parser.add_argument("--output", type=Path, default=Path(".runtime/video-latency"))
    parser.add_argument("--manual-csv", type=Path, help="elapsed_seconds,reference,feed; both readings from one image")
    parser.add_argument("--capture-only", action="store_true", help="Save simultaneous snapshots and CSV template; skip OCR")
    args = parser.parse_args()
    if args.samples < 1 or args.interval <= 0:
        parser.error("samples and interval must be positive")
    if args.manual_csv:
        samples = []
        with args.manual_csv.open(newline="") as file:
            for row in csv.DictReader(file):
                delay = stopwatch_ms(row["reference"]) - stopwatch_ms(row["feed"])
                if not 0 <= delay <= args.max_delay_ms:
                    parser.error("Manual reading out of range; inspect the corresponding image")
                samples.append({"elapsed_seconds": float(row["elapsed_seconds"]), "latency_ms": delay,
                                "transport": args.transport, "stage": args.stage})
        args.output.mkdir(parents=True, exist_ok=False)
        result = summarize(samples)
        (args.output / "latency.json").write_text(json.dumps(result, indent=2))
    else:
        if not args.reference_roi or not args.feed_roi:
            parser.error("Both ROIs are required for automated capture")
        result = measure(args)
    print(json.dumps({k: v for k, v in result.items() if k != "samples"}, indent=2))


if __name__ == "__main__":
    main()
