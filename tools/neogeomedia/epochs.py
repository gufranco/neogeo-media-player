from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

from neogeomedia import encode, frames, palettes

MAX_SAMPLE_TILES: Final = 200_000
SCENE_CUT_SHARE: Final = 0.6
PALETTE_WORDS_PER_FRAME: Final = 48
EPOCH_UPLOAD_MARGIN: Final = 3
WORDS_PER_PALETTE: Final = 16
SAMPLES_PER_EPOCH: Final = 64
CUT_SPACING_DIVISOR: Final = 4

EpochSample = tuple[int, npt.NDArray[np.uint16]]


def stride_for_epoch(*, epoch_frames: int) -> int:
    return max(1, round(epoch_frames / SAMPLES_PER_EPOCH))


def thin_sample(tiles: np.ndarray, seed: int) -> np.ndarray:
    if tiles.shape[0] <= MAX_SAMPLE_TILES:
        return tiles
    rng = np.random.default_rng(seed)
    keep = np.sort(rng.choice(tiles.shape[0], MAX_SAMPLE_TILES, replace=False))
    return tiles[keep]


def epoch_upload_frames(palette_count: int) -> int:
    words = (palette_count // 2) * WORDS_PER_PALETTE
    upload = -(-words // PALETTE_WORDS_PER_FRAME)
    return upload * EPOCH_UPLOAD_MARGIN


def _moved_share(
    grid: npt.NDArray[np.float32],
    current: npt.NDArray[np.uint16],
    previous: npt.NDArray[np.uint16],
    floor: float,
) -> float:
    moved = ((grid[current] - grid[previous]) ** 2).sum(axis=4).mean(axis=(2, 3))
    return float((moved > floor).mean())


def _cut_starts(grids: npt.NDArray[np.uint16], step: int, stride: int, floor: float) -> list[int]:
    grid = palettes.oklab_grid(1.0)
    starts = [0]
    for row in range(1, grids.shape[0]):
        frame = row * stride
        share = _moved_share(grid, grids[row], grids[row - 1], floor)
        if share > SCENE_CUT_SHARE and frame - starts[-1] >= step // CUT_SPACING_DIVISOR:
            starts = [*starts, frame]
    return starts


def _subdivided(starts: list[int], step: int, total: int) -> list[int]:
    stops = [*starts[1:], total]
    return [
        frame
        for start, stop in zip(starts, stops, strict=True)
        for frame in range(start, stop, step)
    ]


def _spaced(starts: list[int], minimum: int) -> list[int]:
    spaced: list[int] = []
    for start in starts:
        if not spaced or start - spaced[-1] >= minimum:
            spaced = [*spaced, start]
    return spaced


def epoch_starts(
    grids: npt.NDArray[np.uint16],
    step: int,
    stride: int,
    total: int,
    *,
    floor: float,
    minimum: int,
) -> list[int]:
    cuts = _cut_starts(grids, step, stride, floor)
    return _spaced(_subdivided(cuts, step, total), minimum)


def _epoch_step(epoch_seconds: float) -> int:
    if epoch_seconds <= 0.0:
        return 0
    return int(epoch_seconds * float(frames.VBLANK_FPS))


def epoch_samples(
    grids: npt.NDArray[np.uint16],
    *,
    epoch_seconds: float,
    sample_stride: int,
    duration: float,
    palette_count: int,
    scene_cut_floor: float,
    seed: int,
) -> list[EpochSample] | None:
    step = _epoch_step(epoch_seconds)
    if step <= 0:
        return None
    stride = max(1, sample_stride)
    total = frames.frame_count(seconds=duration)
    minimum = epoch_upload_frames(palette_count)
    starts = epoch_starts(grids, step, stride, total, floor=scene_cut_floor, minimum=minimum)
    buckets = [
        (start, grids[start // stride : (min(start + step, total) + stride - 1) // stride])
        for start in starts
    ]
    samples = [
        (start, thin_sample(rows.reshape(-1, encode.TILE_PX, encode.TILE_PX), seed + start))
        for start, rows in buckets
        if rows.shape[0] != 0
    ]
    return samples or None
