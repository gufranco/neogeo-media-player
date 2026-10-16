from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from neogeomedia import encode, frames, neocolor


def preview_codec(path: Path) -> list[str]:
    if path.suffix.lower() == ".mkv":
        return ["-c:v", "ffv1", "-level", "3", "-pix_fmt", "rgb24"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"]


def _writer_command(path: Path) -> list[str]:
    rate = frames.VBLANK_FPS
    return [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{encode.FRAME_WIDTH}x{encode.FRAME_HEIGHT}",
        "-r",
        f"{rate.numerator}/{rate.denominator}",
        "-i",
        "-",
        *preview_codec(path),
        str(path),
    ]


class PreviewWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._process = subprocess.Popen(_writer_command(path), stdin=subprocess.PIPE)
        self._path = path

    def write(self, frame: np.ndarray) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(neocolor.color_index_to_rgb(frame).astype(np.uint8).tobytes())

    def close(self) -> None:
        assert self._process.stdin is not None
        self._process.stdin.close()
        if self._process.wait() != 0:
            msg = f"ffmpeg failed to write the preview at {self._path}"
            raise RuntimeError(msg)
