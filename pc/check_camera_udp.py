"""Verify requested RTSP media transport by receiving actual camera video packets."""
import argparse
import json
import os
import subprocess


def check_camera(host, run=subprocess.run, transport="udp"):
    if transport not in ("tcp", "udp"):
        raise ValueError("RTSP transport must be tcp or udp")
    command = ["ffprobe", "-v", "error", "-rtsp_transport", transport, "-timeout", "5000000",
               "-read_intervals", "%+3", "-count_packets", "-show_entries",
               "stream=codec_name,codec_type,nb_read_packets", "-of", "json",
               f"rtsp://{host}:8554/live"]
    try:
        result = run(command, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"verified": False, "transport": transport, "error": str(error)}
    if result.returncode:
        return {"verified": False, "transport": transport, "error": result.stderr.strip()}
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except (ValueError, AttributeError):
        return {"verified": False, "transport": transport, "error": "Invalid ffprobe response"}
    video = [stream for stream in streams if stream.get("codec_type") == "video"
             and str(stream.get("nb_read_packets", "")).isdigit()
             and int(stream["nb_read_packets"]) > 0]
    return {"verified": bool(video), "transport": transport, "streams": streams}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maix-ip", default=os.environ.get("MAIX_IP", "192.168.1.7"))
    parser.add_argument("--transport", choices=("tcp", "udp"), default="udp")
    args = parser.parse_args()
    result = check_camera(args.maix_ip, transport=args.transport)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["verified"] else 1)


if __name__ == "__main__":
    main()
