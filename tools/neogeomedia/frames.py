from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from itertools import islice
from pathlib import Path
from typing import Final, Literal

import numpy as np
import numpy.typing as npt
from fmvcore import ffmpeg, source

_ANALYSIS_SECONDS: Final = 8.0

VBLANK_FPS: Final = Fraction(6_000_000, 384 * 264)
DISPLAY_ASPECT: Final = 4 / 3
PIXEL_ASPECT: Final = DISPLAY_ASPECT * 224 / 320
_ROW_EPSILON: Final = 1e-6

TARGET_WIDTH: Final = 320
TARGET_HEIGHT: Final = 224
TILE_PX: Final = 16
RGB_CHANNELS: Final = 3

FitMode = Literal["fill", "letterbox"]
_FIT_MODES: Final = ("fill", "letterbox")


@dataclass(frozen=True, slots=True)
class Denoise:
    luma_spatial: float = 4.0
    chroma_spatial: float = 3.0
    luma_temporal: float = 6.0
    chroma_temporal: float = 4.5

    def scaled(self, strength: float) -> Denoise:
        return Denoise(
            luma_spatial=self.luma_spatial * strength,
            chroma_spatial=self.chroma_spatial * strength,
            luma_temporal=self.luma_temporal * strength,
            chroma_temporal=self.chroma_temporal * strength,
        )

    def to_filter(self) -> str:
        return (
            f"hqdn3d={self.luma_spatial:g}:{self.chroma_spatial:g}"
            f":{self.luma_temporal:g}:{self.chroma_temporal:g}"
        )


@dataclass(frozen=True, slots=True)
class Geometry:
    crop: tuple[int, int]
    image: tuple[int, int]
    target: tuple[int, int]
    pad_top: int


def frame_count(*, seconds: float) -> int:
    return int(seconds * VBLANK_FPS)


def hold_for_target_fps(target: float) -> int:
    if target <= 0.0:
        msg = f"target fps must be positive, got {target}"
        raise ValueError(msg)
    return max(1, round(float(VBLANK_FPS) / target))


def source_frames_kept(hold: int, source_fps: float) -> float:
    effective = float(VBLANK_FPS) / max(1, hold)
    return min(1.0, effective / float(source_fps))


def _analysed_size(info: ffmpeg.SourceInfo, analysis: source.SourceAnalysis) -> tuple[int, int]:
    if analysis.crop is None:
        return info.width, info.height
    return analysis.crop[0], analysis.crop[1]


def _even(value: int) -> int:
    return value - (value % 2)


def _fill_geometry(source_width: int, source_height: int, target: tuple[int, int]) -> Geometry:
    target_aspect = (target[0] / target[1]) * PIXEL_ASPECT
    if source_width / source_height > target_aspect:
        crop = (_even(round(source_height * target_aspect)), _even(source_height))
    else:
        crop = (_even(source_width), _even(round(source_width / target_aspect)))
    return Geometry(crop=crop, image=target, target=target, pad_top=0)


def _letterbox_rows(source_aspect: float, target_width: int, target_height: int) -> int:
    rows_total = target_height // TILE_PX
    ideal_rows = (target_width * PIXEL_ASPECT / source_aspect) / TILE_PX
    return max(
        (
            rows
            for rows in range(rows_total, 0, -1)
            if rows <= ideal_rows + _ROW_EPSILON and (rows_total - rows) % 2 == 0
        ),
        default=rows_total,
    )


def plan_geometry(
    source_width: int,
    source_height: int,
    target_width: int = TARGET_WIDTH,
    target_height: int = TARGET_HEIGHT,
    *,
    fit: FitMode = "fill",
) -> Geometry:
    if fit not in _FIT_MODES:
        msg = f"unknown fit mode {fit!r}, expected one of {_FIT_MODES}"
        raise ValueError(msg)
    target = (target_width, target_height)
    if fit == "fill":
        return _fill_geometry(source_width, source_height, target)
    rows = _letterbox_rows(source_width / source_height, target_width, target_height)
    image_height = rows * TILE_PX
    return Geometry(
        crop=(_even(source_width), _even(source_height)),
        image=(target_width, image_height),
        target=target,
        pad_top=(target_height - image_height) // 2,
    )


def _source_stages(deinterlace: bool, pre_crop: tuple[int, int, int, int] | None) -> list[str]:
    stages = ["yadif=mode=0:parity=-1:deint=0"] if deinterlace else []
    if pre_crop is None:
        return stages
    bar_w, bar_h, bar_x, bar_y = pre_crop
    return [*stages, f"crop={bar_w}:{bar_h}:{bar_x}:{bar_y}"]


def _picture_stages(denoise: float, motion_blur: int) -> list[str]:
    cleaned = [Denoise().scaled(denoise).to_filter()] if denoise > 0.0 else []
    blurred = [f"tmix=frames={motion_blur}"] if motion_blur > 1 else []
    return [*cleaned, *blurred]


def build_filter(
    geometry: Geometry,
    fps: Fraction = VBLANK_FPS,
    denoise: float = 0.0,
    motion_blur: int = 0,
    *,
    deinterlace: bool = False,
    pre_crop: tuple[int, int, int, int] | None = None,
) -> str:
    crop_w, crop_h = geometry.crop
    image_w, image_h = geometry.image
    target_w, target_h = geometry.target
    padded = [f"pad={target_w}:{target_h}:0:{geometry.pad_top}:black"] if geometry.pad_top else []
    stages = [
        *_source_stages(deinterlace, pre_crop),
        f"crop={crop_w}:{crop_h}",
        f"scale={image_w}:{image_h}:flags=lanczos",
        *_picture_stages(denoise, motion_blur),
        *padded,
        f"fps={fps.numerator}/{fps.denominator}",
        "format=rgb24",
    ]
    return ",".join(stages)


def decode(
    path: Path,
    *,
    start: float,
    duration: float,
    fit: FitMode = "fill",
    target_width: int = TARGET_WIDTH,
    target_height: int = TARGET_HEIGHT,
    denoise: float = 0.0,
    motion_blur: int = 0,
) -> npt.NDArray[np.uint8]:
    wanted = frame_count(seconds=duration)
    window = Window(start, duration, fit, (target_width, target_height), denoise, motion_blur)
    produced = list(_frames(Path(path), window, wanted))
    if not produced:
        msg = f"ffmpeg produced no frames for {path} at {start}s for {duration}s"
        raise RuntimeError(msg)
    if wanted - len(produced) > MAX_SHORTFALL:
        msg = f"ffmpeg produced {len(produced)} frames, expected {wanted}"
        raise RuntimeError(msg)
    tail = [produced[-1]] * (wanted - len(produced))
    return np.stack([*produced, *tail])


DEFAULT_CHUNK_FRAMES: Final = 64
MAX_SHORTFALL: Final = 2


@dataclass(frozen=True, slots=True)
class Window:
    start: float
    duration: float
    fit: FitMode
    size: tuple[int, int]
    denoise: float
    motion_blur: int


def stream(
    path: Path,
    *,
    start: float,
    duration: float,
    fit: FitMode = "fill",
    target_width: int = TARGET_WIDTH,
    target_height: int = TARGET_HEIGHT,
    denoise: float = 0.0,
    motion_blur: int = 0,
    chunk_frames: int = DEFAULT_CHUNK_FRAMES,
) -> Iterator[npt.NDArray[np.uint8]]:
    wanted = frame_count(seconds=duration)
    window = Window(start, duration, fit, (target_width, target_height), denoise, motion_blur)
    pending = iter(_frames(Path(path), window, wanted))
    for _ in range(wanted):
        batch = list(islice(pending, chunk_frames))
        if not batch:
            return
        yield np.stack(batch)


def _frames(path: Path, window: Window, wanted: int) -> Iterator[npt.NDArray[np.uint8]]:
    info = ffmpeg.probe(path)
    analysis = source.analyse(
        path, start=window.start, duration=min(window.duration, _ANALYSIS_SECONDS)
    )
    width, height = _analysed_size(info, analysis)
    target_width, target_height = window.size
    geometry = plan_geometry(width, height, target_width, target_height, fit=window.fit)
    chain = build_filter(
        geometry,
        denoise=window.denoise,
        motion_blur=window.motion_blur,
        deinterlace=analysis.interlaced,
        pre_crop=analysis.crop,
    )
    command = ffmpeg.frame_command(
        path, start=window.start, duration=window.duration, stages=[chain]
    )
    shape = (target_height, target_width, RGB_CHANNELS)
    yield from islice(
        ffmpeg.stream_frames(command, path=path, shape=shape, max_frames=wanted), wanted
    )


def sample(
    path: Path,
    *,
    start: float,
    duration: float,
    stride: int,
    fit: FitMode = "fill",
    denoise: float = 0.0,
    motion_blur: int = 0,
) -> npt.NDArray[np.uint8]:
    kept: list[npt.NDArray[np.uint8]] = []
    index = 0
    for chunk in stream(
        path, start=start, duration=duration, fit=fit, denoise=denoise, motion_blur=motion_blur
    ):
        offsets = [i for i in range(len(chunk)) if (index + i) % stride == 0]
        if offsets:
            kept.append(chunk[offsets])
        index += len(chunk)
    if not kept:
        return np.zeros((0, TARGET_HEIGHT, TARGET_WIDTH, 3), dtype=np.uint8)
    return np.concatenate(kept)
