"""Thin ffmpeg/ffprobe subprocess wrappers (research D5).

No Python media dependencies on purpose — ffmpeg is a system binary (README
prerequisite). Every call has a hard timeout; on failure the tail of stderr becomes
the exception message, which the pipeline records as ``Wallpaper.failure_reason``.
Tests mock this module at the boundary (Constitution X).
"""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

PROBE_TIMEOUT = 60
TRANSCODE_TIMEOUT = 1800  # 30 min — generous even for 500 MB 4K sources

# Preview rendition (research D5): shortest side 720, first 10 s, translucent
# corner watermark, aggressive CRF — it is a taster, not the product.
PREVIEW_SHORT_SIDE = 720
PREVIEW_SECONDS = 10
WATERMARK_TEXT = "LiveCanvas"


class FfmpegError(RuntimeError):
    """A media tool failed; ``str(exc)`` is safe to store as failure_reason."""


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:  # binary not installed
        raise FfmpegError(f"{cmd[0]} binary not found on this host") from exc
    except subprocess.TimeoutExpired as exc:
        raise FfmpegError(f"{cmd[0]} timed out after {timeout}s") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-500:]
        raise FfmpegError(f"{cmd[0]} failed (rc={proc.returncode}): {tail}")
    return proc


def probe(path: Path) -> dict:
    """Return ``{width, height, duration}`` of the first video stream."""
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-print_format",
            "json",
            str(path),
        ],
        PROBE_TIMEOUT,
    )
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    if not streams or not streams[0].get("width"):
        raise FfmpegError("no video stream found")
    return {
        "width": int(streams[0]["width"]),
        "height": int(streams[0]["height"]),
        "duration": float(data.get("format", {}).get("duration", 0.0)),
    }


def normalize_master(src: Path, dst: Path) -> None:
    """Re-encode to the device-compatible H.264 master, keeping source resolution."""
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            # Only the primary video stream: sources may carry audio/data (e.g. Pexels
            # timecode) streams that cannot be muxed into the normalized MP4.
            "-map",
            "0:v:0",
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",  # wallpapers are silent
            str(dst),
        ],
        TRANSCODE_TIMEOUT,
    )


def extract_thumbnail(src: Path, dst: Path) -> None:
    """One JPEG frame at t=1s, long side capped at 1080."""
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            "1",
            "-i",
            str(src),
            "-vf",
            "scale='min(1080,iw)':-2",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(dst),
        ],
        PROBE_TIMEOUT,
    )


@lru_cache(maxsize=1)
def _has_drawtext() -> bool:
    """``drawtext`` needs an ffmpeg built with libfreetype — not all builds have it
    (e.g. slim Homebrew bottles). Probed once per process."""
    try:
        proc = _run(["ffmpeg", "-hide_banner", "-filters"], PROBE_TIMEOUT)
    except FfmpegError:
        return False
    return "drawtext" in proc.stdout


def _watermark_filter() -> str:
    if _has_drawtext():
        return (
            f"drawtext=text='{WATERMARK_TEXT}':fontcolor=white@0.35:fontsize=h/20:"
            f"x=w-tw-10:y=h-th-10"
        )
    # Fallback for freetype-less builds: a translucent corner band still marks the
    # preview as a taster. Full text branding needs `brew install ffmpeg` (with
    # libfreetype) — noted in README.
    return "drawbox=x=iw-iw/4-10:y=ih-ih/30-10:w=iw/4:h=ih/30:color=white@0.35:t=fill"


def render_preview(src: Path, dst: Path) -> None:
    """Watermarked 720p-class 10-second preview (public zone)."""
    vf = (
        f"scale='if(gt(iw,ih),-2,{PREVIEW_SHORT_SIDE})':'if(gt(iw,ih),{PREVIEW_SHORT_SIDE},-2)',"
        f"{_watermark_filter()}"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-map",
            "0:v:0",  # primary video stream only (see normalize_master)
            "-t",
            str(PREVIEW_SECONDS),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(dst),
        ],
        TRANSCODE_TIMEOUT,
    )
