import subprocess
from typing import TYPE_CHECKING

from script_generator.debug.logger import log_vid

if TYPE_CHECKING:
    from script_generator.state.app_state import AppState

HW_TEST_CMDS = {
    "cuda": [
        "-init_hw_device", "cuda=0",
        "-f", "lavfi", "-i", "nullsrc=size=256x256:duration=0.1:rate=1",
        "-c:v", "h264_nvenc",
        "-f", "null", "-"
    ],
    "vaapi": [
        "-init_hw_device", "vaapi=/dev/dri/renderD128",
        "-f", "lavfi", "-i", "nullsrc=size=256x256:duration=0.1:rate=1",
        "-c:v", "h264_vaapi",
        "-f", "null", "-"
    ],
    "amf": [
        "-f", "lavfi", "-i", "nullsrc=size=256x256:duration=0.1:rate=1",
        "-c:v", "h264_amf",
        "-f", "null", "-"
    ],
    "qsv": [
        "-init_hw_device", "qsv=hw:0",
        "-f", "lavfi", "-i", "nullsrc=size=256x256:duration=0.1:rate=1",
        "-c:v", "h264_qsv",
        "-f", "null", "-"
    ],
    "d3d11va": [
        "-init_hw_device", "d3d11va=hw:0",
        "-f", "lavfi", "-i", "nullsrc=size=256x256:duration=0.1:rate=1",
        "-f", "null", "-"
    ],
    "videotoolbox": [
        "-f", "lavfi", "-i", "nullsrc=size=256x256:duration=0.1:rate=1",
        "-pix_fmt", "yuv420p",
        "-c:v", "h264_videotoolbox",
        "-f", "null", "-"
    ]
}


def _run_cmd(cmd):
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return (r.returncode == 0, r.stderr)
    except Exception as e:
        return (False, str(e))


def _list_ffmpeg_hwaccels(ffmpeg_path):
    try:
        r = subprocess.run(
            [ffmpeg_path, "-hwaccels"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        lines = [l.strip() for l in r.stdout.lower().replace("hardware acceleration methods:", "").splitlines() if l.strip()]
        log_vid.info(f"hardware acceleration methods compiled in FFmpeg binary: {', '.join(lines)}")
        return lines
    except Exception as e:
        log_vid.error(e)
        return []


def _test_hwaccel(ffmpeg_path, hw):
    if hw in HW_TEST_CMDS:
        cmd = [ffmpeg_path] + HW_TEST_CMDS[hw]
        ok, err = _run_cmd(cmd)
        if not ok: log_vid.debug(f"{hw} test failed: {err}")
        return ok
    ok, _ = _run_cmd([ffmpeg_path, "-init_hw_device", hw])
    return ok


def get_preferred_hwaccel(ffmpeg_path):
    supported = _list_ffmpeg_hwaccels(ffmpeg_path)
    for hw in ["cuda", "vaapi", "amf", "videotoolbox", "qsv", "d3d11va"]:
        if hw in supported and _test_hwaccel(ffmpeg_path, hw):
            log_vid.info(f"Setting preferred FFmpeg hardware acceleration too: {hw}")
            return hw
    log_vid.info("No working hwaccel found.")
    return None


def get_hwaccel_read_args(state):
    hwaccel = state.ffmpeg_hwaccel
    if hwaccel == "cuda":
        if supports_cuda_scale(state):
            return ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
        return ["-hwaccel", "cuda"]
    if hwaccel == "vaapi":
        return ["-hwaccel", "vaapi", "-hwaccel_device", "/dev/dri/renderD128"]
    if hwaccel == "amf":
        return ["-hwaccel", "amf"]
    if hwaccel == "videotoolbox":
        return ["-hwaccel", "videotoolbox"]
    if hwaccel == "qsv":
        return ["-hwaccel", "qsv"]
    if hwaccel == "d3d11va":
        return ["-hwaccel", "d3d11va"]
    return []


scale_cuda = None
def _has_scale_cuda(ffmpeg_path):
    global scale_cuda
    if scale_cuda is not None:
        return scale_cuda

    # Check if FFmpeg supports the scale_cuda filter.
    try:
        r = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-filters"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        filters = r.stdout.lower()
        scale_cuda = "scale_cuda" in filters
        log_vid.info(f"FFmpeg {'supports' if scale_cuda else 'does not support'} scale_cuda")
        return scale_cuda
    except Exception as e:
        log_vid.error(f"Failed to check scale_cuda support: {e}")
        scale_cuda = False
        return False

def supports_cuda_scale(state: "AppState"):
    video = state.video_info
    return (
        state.ffmpeg_hwaccel == "cuda"
        and video.bit_depth == 8
        and (video.codec_name != "h264" or (video.width <= 4096 and video.height <= 4096))
        and _has_scale_cuda(state.ffmpeg_path)
    )
