"""Display rotation for copied H.264, without resizing or re-encoding frames."""
import functools
import subprocess


def validate_rotation(rotation):
    if type(rotation) is not int or rotation not in (0, 90, 180, 270):
        raise ValueError("rotation must be 0, 90, 180 or 270 counter-clockwise degrees")
    return rotation


@functools.lru_cache(maxsize=1)
def supports_display_rotation():
    # FFmpeg 6+ moved rotation control to an input option. The deployed Debian
    # FFmpeg 5 still writes the MP4 matrix from the rotate metadata tag.
    result = subprocess.run(["ffmpeg", "-hide_banner", "-h", "full"],
                            capture_output=True, text=True, timeout=10,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    result.check_returncode()
    return "-display_rotation" in result.stdout


def rotation_options(rotation):
    validate_rotation(rotation)
    if rotation == 0:
        return [], []
    angle = str(rotation)  # Manager controls and FFmpeg both use CCW degrees.
    if supports_display_rotation():
        return ["-noautorotate", "-display_rotation:v:0", angle], []
    return [], ["-metadata:s:v:0", "rotate=" + angle]
