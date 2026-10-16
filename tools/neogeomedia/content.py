from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from fmvcore import ffmpeg

from neogeomedia import encode, frames, neocolor, palettes

MIN_EPOCH_SECONDS: Final = 2.5
MAX_EPOCH_SECONDS: Final = 8.0
CUT_SCORE_THRESHOLD: Final = 10.0
SECONDS_PER_MINUTE: Final = 60.0

_METADATA = re.compile(r"lavfi\.(\S+)=([0-9.eE+-]+)")


@dataclass(frozen=True, slots=True)
class ContentProfile:
    saturation: float
    cuts_per_minute: float


def _metadata_values(path: Path, filter_spec: str, key: str, *, duration: float) -> list[float]:
    result = subprocess.run(
        [
            ffmpeg.require_tool("ffmpeg"),
            "-hide_banner",
            "-v",
            "error",
            "-i",
            str(path),
            "-t",
            f"{duration:.6f}",
            "-vf",
            f"{filter_spec},metadata=print:file=-",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return [float(value) for name, value in _METADATA.findall(result.stdout) if name.endswith(key)]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def measure(path: Path, *, duration: float = 8.0) -> ContentProfile:
    path = Path(path)

    saturation = _metadata_values(path, "signalstats", "SATAVG", duration=duration)
    scores = _metadata_values(
        path, f"scdet=threshold={CUT_SCORE_THRESHOLD}", "score", duration=duration
    )

    cuts = sum(1 for score in scores if score > CUT_SCORE_THRESHOLD)
    minutes = max(duration, 1e-6) / SECONDS_PER_MINUTE
    return ContentProfile(
        saturation=max(0.0, _mean(saturation)),
        cuts_per_minute=cuts / minutes,
    )


def epoch_seconds_for(*, cuts_per_minute: float) -> float:
    if cuts_per_minute <= 0.0:
        return MAX_EPOCH_SECONDS
    wanted = SECONDS_PER_MINUTE / cuts_per_minute
    return min(MAX_EPOCH_SECONDS, max(MIN_EPOCH_SECONDS, wanted))


MOVEMENT_PERCENTILE: Final = 99.0

MOVEMENT_FLOOR_MINIMUM: Final = 1e-6

MOVEMENT_SAMPLE_SECONDS: Final = 1.2


def movement_floor(path: Path, *, duration: float = MOVEMENT_SAMPLE_SECONDS) -> float:
    clip = np.concatenate(list(frames.stream(Path(path), start=0.0, duration=duration)))
    if clip.shape[0] < 2:
        return MOVEMENT_FLOOR_MINIMUM
    grid = palettes.oklab_grid(1.0)
    tiles = encode.to_tiles(neocolor.rgb_to_color_index(clip))
    moved = ((grid[tiles[1:]] - grid[tiles[:-1]]) ** 2).sum(axis=-1).mean(axis=(-2, -1))
    return max(MOVEMENT_FLOOR_MINIMUM, float(np.percentile(moved.reshape(-1), MOVEMENT_PERCENTILE)))
