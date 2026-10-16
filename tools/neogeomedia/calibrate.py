from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
from fmvcore import ffmpeg

from neogeomedia import encode, frames, neocolor, quality

DEFAULT_SAMPLE_COUNT: int = 24
DEFAULT_SAMPLE_SECONDS: float = 3.0


def sample_windows(duration: float, *, count: int, seconds: float) -> list[tuple[float, float]]:
    if duration <= 0.0:
        msg = f"duration must be positive, got {duration}"
        raise ValueError(msg)
    if count < 1:
        msg = f"sample count must be at least one, got {count}"
        raise ValueError(msg)
    if seconds <= 0.0:
        msg = f"sample seconds must be positive, got {seconds}"
        raise ValueError(msg)
    if duration <= seconds:
        return [(0.0, duration)]

    usable = min(count, int(duration // seconds))
    stride = duration / usable
    windows: list[tuple[float, float]] = []
    for index in range(usable):
        centre = stride * (index + 0.5)
        start = min(max(0.0, centre - seconds / 2.0), duration - seconds)
        windows.append((start, seconds))
    return windows


def measure_reference_rate(
    source: Path,
    *,
    count: int = DEFAULT_SAMPLE_COUNT,
    seconds: float = DEFAULT_SAMPLE_SECONDS,
    fit: frames.FitMode = "fill",
    seed: int = 0,
    start: float = 0.0,
    duration: float | None = None,
) -> float:
    source = Path(source)
    info = ffmpeg.probe(source)
    span_total = info.duration - start
    if duration is not None:
        span_total = min(span_total, duration)
    windows = sample_windows(span_total, count=count, seconds=seconds)

    chunks = [
        np.concatenate(list(frames.stream(source, start=start + offset, duration=span, fit=fit)))
        for offset, span in windows
    ]
    clip = np.concatenate(chunks)
    tier = quality.tier_by_name(quality.REFERENCE_TIER)
    sample_tiles = encode.to_tiles(neocolor.rgb_to_color_index(clip[::4])).reshape(-1, 16, 16)
    result = encode.encode_stream(
        [clip],
        encode.EncodeOptions(
            collect_rendered=False,
            chroma_weight=tier.chroma_weight,
            frame_hold=tier.frame_hold,
            tolerance=tier.tolerance,
            seed=seed,
        ),
        sample_tiles=sample_tiles,
        total_frames=clip.shape[0],
    )
    minutes = clip.shape[0] / float(frames.VBLANK_FPS) / quality.SECONDS_PER_MINUTE
    rate: float = result.stats.tile_count / minutes
    return rate


def measure_anchors(
    source: Path,
    *,
    count: int = DEFAULT_SAMPLE_COUNT,
    seconds: float = DEFAULT_SAMPLE_SECONDS,
    fit: frames.FitMode = "fill",
    seed: int = 0,
    start: float = 0.0,
    duration: float | None = None,
) -> tuple[float, dict[float, float]]:
    source = Path(source)
    info = ffmpeg.probe(source)
    span_total = info.duration - start
    if duration is not None:
        span_total = min(span_total, duration)
    windows = sample_windows(span_total, count=count, seconds=seconds)
    clip = np.concatenate(
        [
            np.concatenate(
                list(frames.stream(source, start=start + offset, duration=span, fit=fit))
            )
            for offset, span in windows
        ]
    )
    minutes = clip.shape[0] / float(frames.VBLANK_FPS) / quality.SECONDS_PER_MINUTE

    measured: dict[float, float] = {}
    reference_rate = 0.0
    anchors = quality.anchor_tiers(float(info.fps), float(frames.VBLANK_FPS))
    for tier in anchors:
        rate = _encode_rate(clip, tier, seed=seed) / minutes
        measured[tier.relative_cost] = rate
        if tier.name == quality.REFERENCE_TIER:
            reference_rate = rate

    return reference_rate, {rung: rate / reference_rate for rung, rate in measured.items()}


def _encode_rate(clip: npt.NDArray[np.uint8], tier: quality.Tier, *, seed: int) -> float:
    sample_tiles = encode.to_tiles(neocolor.rgb_to_color_index(clip[::4])).reshape(-1, 16, 16)
    result = encode.encode_stream(
        [clip],
        encode.EncodeOptions(
            collect_rendered=False,
            chroma_weight=tier.chroma_weight,
            frame_hold=tier.frame_hold,
            tolerance=tier.tolerance,
            seed=seed,
        ),
        sample_tiles=sample_tiles,
        total_frames=clip.shape[0],
    )
    return float(result.stats.tile_count)
