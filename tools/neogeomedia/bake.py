from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt
from fmvcore import arguments, ffmpeg

from neogeomedia import (
    adpcmb,
    bundle,
    content,
    crom,
    encode,
    fixtiles,
    frames,
    limits,
    neocolor,
    palettes,
    quality,
    subtitles,
)
from neogeomedia import stream as stream_mod

SECONDS_PER_MINUTE: Final = 60.0
CROM_BANK_BYTES: Final = 128 << 20
OVERRAN: Final = 4
ADPCM_B_BYTES: Final = 16 << 20
V_ROM_MIN_BYTES: Final = 1 << 19
MAX_SAMPLE_TILES: Final = 200_000
_SCENE_CUT_SHARE: Final = 0.6

MOVIE_SYMBOL: Final = "fmv_movie_data"
STREAM_BASE_SYMBOL: Final = "fmv_stream_base"

STREAM_BANK_SYMBOL: Final = "fmv_stream_bank"
STREAM_BANK_STEM: Final = "fmv_stream__bank"

PALETTE_WORDS_PER_FRAME: Final = 48

EPOCH_UPLOAD_MARGIN: Final = 3

WORDS_PER_PALETTE: Final = 16

SAMPLES_PER_EPOCH: Final = 64


def stride_for_epoch(*, epoch_frames: int) -> int:
    return max(1, round(epoch_frames / SAMPLES_PER_EPOCH))


FIX_PALETTE_BANK: Final = 1
S_ROM_BYTES: Final = 131072

CYCLES_PER_UPDATE: Final = 64

CYCLES_PER_LINE: Final = 768
BLANK_LINES: Final = 40
VBLANK_CYCLES: Final = (BLANK_LINES - 1) * CYCLES_PER_LINE


def has_audio_stream(source: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(source),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _decode_audio(
    source: Path, start: float, duration: float, rate_hz: float
) -> npt.NDArray[np.int16]:
    if not has_audio_stream(source):
        return np.zeros(0, dtype=np.int16)
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{start:.6f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.6f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(int(rate_hz)),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return np.frombuffer(result.stdout, dtype="<i2")


def self_tier_name(request: BakeRequest) -> str:
    return (request.quality or "custom").upper()[:8]


def _fix_defines() -> str:
    names = {
        "blank": "FIX_TILE_BLANK",
        "panel": "FIX_TILE_PANEL",
        "0": "FIX_TILE_DIGIT0",
        "colon": "FIX_TILE_COLON",
        "slash": "FIX_TILE_SLASH",
        "play": "FIX_TILE_PLAY",
        "pause": "FIX_TILE_PAUSE",
        "forward": "FIX_TILE_FORWARD",
        "rewind": "FIX_TILE_REWIND",
        "bar_empty": "FIX_TILE_BAR_EMPTY",
        "bar_filled": "FIX_TILE_BAR_FILLED",
        "panel_top": "FIX_TILE_PANEL_TOP",
        "bar_cap_left": "FIX_TILE_BAR_CAP_LEFT",
        "bar_cap_right": "FIX_TILE_BAR_CAP_RIGHT",
        "bar_knob": "FIX_TILE_BAR_KNOB",
        "A": "FIX_TILE_A",
        "percent": "FIX_TILE_PERCENT",
        "dot": "FIX_TILE_DOT",
        "dash": "FIX_TILE_DASH",
    }
    return "\n".join(f"#define {macro} {fixtiles.GLYPHS[glyph]}" for glyph, macro in names.items())


_PROFILE_SECONDS: Final = 30.0

_HEADER_TEMPLATE: Final = """#ifndef MOVIE_DATA_H
#define MOVIE_DATA_H

#include "fmv.h"

#define MOVIE_BAKER_VERSION_MAJOR {baker_major}
#define MOVIE_BAKER_VERSION_MINOR {baker_minor}
#define MOVIE_BAKER_VERSION_STRING "{baker_major}.{baker_minor}"

#if MOVIE_BAKER_VERSION_MAJOR != FMV_VERSION_MAJOR \\
    || MOVIE_BAKER_VERSION_MINOR != FMV_VERSION_MINOR
#pragma message("this movie was baked by neogeomedia " MOVIE_BAKER_VERSION_STRING)
#pragma message("the fmv library beside it is " FMV_VERSION_STRING)
#error "baked movie and fmv library are different versions; re-bake, or replace fmv/"
#endif

#define MOVIE_FRAME_COUNT {frames}
#define MOVIE_TILE_COUNT {tiles}
#define MOVIE_FIRST_FREE_TILE {tiles}
#define MOVIE_FREE_TILES {free_tiles}
#define MOVIE_CROM_BYTES {crom_size}
#define MOVIE_PALETTE_COUNT {palettes}
#define MOVIE_PALETTE_BASE {base_bank}
#define MOVIE_EPOCH_COUNT {epochs}
#define MOVIE_EPOCH_PALETTES {epoch_palettes}
#define MOVIE_EPOCH_SLICE {epoch_slice}u
#define MOVIE_IMAGE_WIDTH {image_width}
#define MOVIE_IMAGE_HEIGHT {image_height}
#define MOVIE_TIER_NAME "{tier_name}"
#define MOVIE_CHROMA_PERCENT {chroma_percent}
#define MOVIE_CROM_PERCENT {crom_percent}
#define MOVIE_AUDIO_HZ {audio_hz}
#define MOVIE_FRAME_HOLD {frame_hold}
#define MOVIE_KEYFRAME_COUNT {keyframes}
#define MOVIE_GRID_COLS {cols}
#define MOVIE_GRID_ROWS {rows}
#define MOVIE_MAX_UPDATES {max_updates}
#define MOVIE_CYCLES_PER_UPDATE {cycles_per_update}
#define MOVIE_TICK_CYCLES {tick_cycles}
#define MOVIE_VBLANK_CYCLES {vblank_cycles}
#define MOVIE_STREAM_BANKS {stream_banks}
#define MOVIE_STREAM_BYTES {stream_bytes}u
#define MOVIE_FPS_NUM {fps_num}u
#define MOVIE_FPS_DEN {fps_den}u
#define MOVIE_AUDIO_PAGE_NUM {audio_page_num}u
#define MOVIE_AUDIO_PAGE_DEN {audio_page_den}u
#define MOVIE_SUBTITLE_COUNT {subtitle_count}
#define MOVIE_SUBTITLE_COLUMNS {subtitle_columns}
#define MOVIE_SUBTITLE_LINES {subtitle_lines}

#define FIX_PALETTE {fix_palette}
{fix_defines}

extern const unsigned char movie_index[];
extern const unsigned char movie_keyframes[];
extern const unsigned char movie_palettes[];
extern const unsigned char movie_epochs[];
extern const unsigned char movie_subtitles[];
extern const unsigned char movie_fix_palette[];

extern const fmv_movie {movie_symbol};

#endif
"""

_MOVIE_TEMPLATE: Final = """#include "fmv.h"
#include "movie_data.h"

extern const unsigned char {stream_base_symbol}[];

const fmv_movie {movie_symbol} = {{
    .index = movie_index,
    .keyframes = movie_keyframes,
    .palettes = movie_palettes,
    .epochs = movie_epochs,
    .subtitles = movie_subtitles,
    .stream_base = (uint32_t){stream_base_symbol},
    .frames = {frames}u,
    .keyframe_count = {keyframes}u,
    .fps_num = {fps_num}u,
    .fps_den = {fps_den}u,
    .audio_page_num = {audio_page_num}u,
    .audio_page_den = {audio_page_den}u,
    .epoch_count = {epochs}u,
    .epoch_palettes = {epoch_palettes}u,
    .epoch_slice = {epoch_slice}u,
    .palette_base = {base_bank}u,
    .first_sprite = {first_sprite}u,
    .grid_cols = {cols}u,
    .grid_rows = {rows}u,
    .max_updates = {max_updates}u,
    .subtitle_count = {subtitle_count}u,
    .subtitle_columns = {subtitle_columns}u,
    .subtitle_lines = {subtitle_lines}u,
}};
"""

_ASM_ENTRY: Final = """    .globl {symbol}
    .balign 2
{symbol}:
    .incbin "{path}"
"""

_STREAM_BANK_ENTRY: Final = """    .section .rodata
    .globl {symbol}
    .balign 2
{symbol}:
    .incbin "{path}", {skip}, {count}
"""


@dataclass(frozen=True, slots=True)
class BakeRequest:
    source: Path
    start: float
    duration: float
    build_dir: Path
    fit: frames.FitMode = "fill"
    palette_count: int = 240
    base_bank: int = 16
    keyframe_interval: int = 90
    tolerance: float = 0.0005
    scene_cut_ratio: float = 0.90
    candidates: int = 12
    allow_flip: bool = False
    sample_stride: int = 8
    seed: int = 0
    preview: Path | None = None
    denoise: float = 0.0
    frame_hold: int = 1
    motion_blur: int = 0
    motion_masking: float = 0.0
    dither: bool = False
    chroma_weight: float = 1.0
    scene_cut_floor: float = 0.01
    palette_epoch_seconds: float = 5.0
    quality: str | None = None
    tile_budget: int = 0
    stop_when_over_budget: bool = False
    audio_rate_hz: float | None = None
    subtitles: Path | None = None
    audio: bool = True


@dataclass(frozen=True, slots=True)
class BakeOutcome:
    request: BakeRequest
    result: encode.EncodeResult
    build_dir: Path
    artifacts: dict[str, Path] = field(default_factory=dict)

    def report(self) -> dict[str, Any]:
        stats = self.result.stats
        seconds = stats.frames / float(frames.VBLANK_FPS)
        minutes = seconds / SECONDS_PER_MINUTE
        crom_per_minute = stats.crom_payload_bytes / minutes
        stream_per_minute = stats.stream_bytes / minutes
        return {
            "frames": stats.frames,
            "seconds": round(seconds, 3),
            "denoise": self.request.denoise,
            "frame_hold": self.request.frame_hold,
            "motion_blur": self.request.motion_blur,
            "motion_masking": self.request.motion_masking,
            "dither": self.request.dither,
            "chroma_weight": self.request.chroma_weight,
            "scene_cut_floor": self.request.scene_cut_floor,
            "palette_epoch_seconds": self.request.palette_epoch_seconds,
            "palette_epochs": len(self.result.palette_sets),
            "has_audio": "voice" in self.artifacts,
            "tile_budget": self.request.tile_budget,
            "tile_count": stats.tile_count,
            "dictionary_full": stats.dictionary_full,
            "crom_payload_bytes": stats.crom_payload_bytes,
            "crom_rom_bytes": stats.crom_rom_bytes,
            "stream_bytes": stats.stream_bytes,
            "stream_rom_bytes": stats.stream_rom_bytes,
            "keyframe_bytes": stats.keyframe_bytes,
            "delta_bytes": stats.delta_bytes,
            "index_bytes": stats.index_bytes,
            "keyframe_count": stats.keyframe_count,
            "stream_banks": self.result.stream.bank_count(),
            "max_updates": stats.max_updates,
            "mean_updates": round(stats.mean_updates, 2),
            "mean_error": stats.mean_error,
            "peak_tolerance": stats.peak_tolerance,
            "budget_exceeded": stats.budget_exceeded,
            "truncated": stats.truncated,
            "rate_control_exhausted": stats.rate_control_exhausted,
            "displayed_error": stats.displayed_error,
            "blurred_error": stats.blurred_error,
            "projected_crom_bytes_per_minute": round(crom_per_minute),
            "projected_stream_bytes_per_minute": round(stream_per_minute),
            "projected_minutes_per_crom_bank": round(CROM_BANK_BYTES / crom_per_minute, 2),
        }


def _thin_sample(tiles: np.ndarray, seed: int) -> np.ndarray:
    if tiles.shape[0] <= MAX_SAMPLE_TILES:
        return tiles
    rng = np.random.default_rng(seed)
    keep = rng.choice(tiles.shape[0], MAX_SAMPLE_TILES, replace=False)
    keep.sort()
    return tiles[keep]


def audio_pages_per_frame(delta_n: int) -> Fraction:
    if delta_n <= 0:
        return Fraction(0)
    return adpcmb.exact_rate(delta_n) / (512 * frames.VBLANK_FPS)


def write_movie_bundle(target: Path, outcome: BakeOutcome) -> bundle.BundleLayout:
    stats = outcome.result.stats
    return bundle.write_bundle(
        target=target,
        build_dir=outcome.build_dir,
        stream_banks=outcome.result.stream.bank_count(),
        max_updates=stats.max_updates,
        tick_cycles=stats.max_updates * CYCLES_PER_UPDATE,
        tile_count=stats.tile_count,
        crom_payload=outcome.result.dictionary.payload_bytes(),
        crom_size=crom.rom_size_for(stats.tile_count),
        palette_base=outcome.result.palette_set.base_bank,
        first_sprite=stream_mod.FIRST_SPRITE,
        frames=stats.frames,
        version=baker_version(),
    )


def baker_version() -> tuple[int, int]:
    major, minor = version("neogeomedia").split(".")[:2]
    return int(major), int(minor)


def _write_stream_banks(build_dir: Path, stream_path: Path, banks: int) -> list[Path]:
    generated = build_dir / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    stubs: list[Path] = []
    for bank in range(banks):
        stub = generated / f"{STREAM_BANK_STEM}{bank}.S"
        stub.write_text(
            _STREAM_BANK_ENTRY.format(
                symbol=f"{STREAM_BANK_SYMBOL}{bank}",
                path=stream_path.name,
                skip=bank * stream_mod.PROM_BANK_BYTES,
                count=stream_mod.PROM_BANK_BYTES,
            )
        )
        stubs.append(stub)
    return stubs


def _write_sources(
    build_dir: Path,
    outcome_paths: dict[str, Path],
    result: encode.EncodeResult,
    request: BakeRequest,
    *,
    audio_pages: Fraction = Fraction(0),
    audio_hz: float = 0.0,
) -> tuple[Path, Path]:
    generated = build_dir / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    major, minor = baker_version()

    asm = generated / "movie_data.S"
    body = "    .section .rodata\n"
    for symbol, key in (
        ("movie_index", "index"),
        ("movie_keyframes", "keyframes"),
        ("movie_palettes", "palettes"),
        ("movie_epochs", "epochs"),
        ("movie_fix_palette", "fixpal"),
        ("movie_subtitles", "subtitles"),
    ):
        body += _ASM_ENTRY.format(symbol=symbol, path=outcome_paths[key].name)
    asm.write_text(body)

    fields = {
        "frames": result.stats.frames,
        "tiles": result.stats.tile_count,
        "palettes": len(result.palette_set),
        "epochs": len(result.palette_sets),
        "epoch_palettes": len(result.palette_sets[0]),
        "epoch_slice": PALETTE_WORDS_PER_FRAME,
        "image_width": encode.FRAME_WIDTH,
        "image_height": encode.FRAME_HEIGHT,
        "tier_name": self_tier_name(request),
        "chroma_percent": round(request.chroma_weight * 100),
        "crom_percent": round(100 * result.stats.crom_payload_bytes / CROM_BANK_BYTES),
        "audio_hz": round(audio_hz),
        "frame_hold": request.frame_hold,
        "base_bank": result.palette_set.base_bank,
        "keyframes": result.stats.keyframe_count,
        "cols": encode.GRID_COLS,
        "rows": encode.GRID_ROWS,
        "max_updates": result.stats.max_updates,
        "stream_banks": result.stream.bank_count(),
        "stream_bytes": result.stats.stream_bytes,
        "fps_num": frames.VBLANK_FPS.numerator,
        "fps_den": frames.VBLANK_FPS.denominator,
        "fix_palette": FIX_PALETTE_BANK,
        "fix_defines": _fix_defines(),
        "audio_page_num": audio_pages.numerator,
        "audio_page_den": audio_pages.denominator or 1,
        "subtitle_count": (
            outcome_paths["subtitles"].stat().st_size // subtitles.RECORD_BYTES
            if "subtitles" in outcome_paths
            else 0
        ),
        "subtitle_columns": subtitles.COLUMNS,
        "subtitle_lines": subtitles.MAX_LINES,
        "movie_symbol": MOVIE_SYMBOL,
        "first_sprite": stream_mod.FIRST_SPRITE,
        "stream_base_symbol": STREAM_BASE_SYMBOL,
        "baker_major": major,
        "baker_minor": minor,
        "crom_size": crom.rom_size_for(result.stats.tile_count),
        "free_tiles": (
            crom.rom_size_for(result.stats.tile_count)
            - result.stats.tile_count * crom.TILE_BYTES_PER_ROM
        )
        // crom.TILE_BYTES_PER_ROM,
        "cycles_per_update": CYCLES_PER_UPDATE,
        "tick_cycles": result.stats.max_updates * CYCLES_PER_UPDATE,
        "vblank_cycles": VBLANK_CYCLES,
    }

    header = generated / "movie_data.h"
    header.write_text(_HEADER_TEMPLATE.format(**fields))
    movie = generated / "movie_data_value.c"
    movie.write_text(_MOVIE_TEMPLATE.format(**fields))
    return asm, header


def _preview_codec(path: Path) -> list[str]:
    if path.suffix.lower() == ".mkv":
        return ["-c:v", "ffv1", "-level", "3", "-pix_fmt", "rgb24"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"]


def _write_audio_params(build_dir: Path, encoded: adpcmb.EncodedAudio) -> Path:
    generated = build_dir / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    path = generated / "audio_params.s"
    path.write_text(
        "\n".join(
            [
                f"    ADPCM_B_START_LO = 0x{encoded.start_address & 0xFF:02x}",
                f"    ADPCM_B_START_HI = 0x{(encoded.start_address >> 8) & 0xFF:02x}",
                f"    ADPCM_B_END_LO = 0x{encoded.end_address & 0xFF:02x}",
                f"    ADPCM_B_END_HI = 0x{(encoded.end_address >> 8) & 0xFF:02x}",
                f"    ADPCM_B_DELTA_LO = 0x{encoded.delta_n & 0xFF:02x}",
                f"    ADPCM_B_DELTA_HI = 0x{(encoded.delta_n >> 8) & 0xFF:02x}",
                "",
            ]
        )
    )
    return path


class _PreviewWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rate = frames.VBLANK_FPS
        self._process = subprocess.Popen(
            [
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
                *_preview_codec(path),
                str(path),
            ],
            stdin=subprocess.PIPE,
        )
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


def _palette_blob(result: encode.EncodeResult) -> bytes:
    return b"".join(palette_set.cram_blob() for palette_set in result.palette_sets)


def _subtitle_blob(request: BakeRequest) -> bytes:
    sidecar: Path
    if request.subtitles is not None:
        sidecar = Path(request.subtitles)
        if not sidecar.is_file():
            raise FileNotFoundError(f"subtitle file not found: {sidecar}")
    else:
        beside = subtitles.sidecar_for(request.source)
        if beside is None:
            return b""
        sidecar = beside
    cues = [
        subtitles.Cue(
            start=cue.start - request.start,
            end=min(cue.end, request.start + request.duration) - request.start,
            lines=cue.lines,
        )
        for cue in subtitles.parse(sidecar.read_text(encoding="utf-8", errors="replace"))
        if cue.end > request.start and cue.start < request.start + request.duration
    ]
    trimmed = [
        subtitles.Cue(start=max(0.0, cue.start), end=cue.end, lines=cue.lines)
        for cue in cues
        if cue.end > 0.0
    ]
    return subtitles.encode(trimmed, fps=float(frames.VBLANK_FPS))


def _epoch_blob(result: encode.EncodeResult) -> bytes:
    return np.asarray(result.epoch_starts, dtype=">u4").tobytes()


def epoch_upload_frames(palette_count: int) -> int:
    words = (palette_count // 2) * WORDS_PER_PALETTE
    upload = -(-words // PALETTE_WORDS_PER_FRAME)
    return upload * EPOCH_UPLOAD_MARGIN


def _epoch_starts(
    grids: npt.NDArray[np.uint16],
    step: int,
    stride: int,
    total: int,
    *,
    floor: float,
    minimum: int,
) -> list[int]:
    grid = palettes.oklab_grid(1.0)
    starts = [0]
    previous = grids[0] if grids.shape[0] else None
    for row in range(1, grids.shape[0]):
        current = grids[row]
        if previous is not None:
            moved = ((grid[current] - grid[previous]) ** 2).sum(axis=4).mean(axis=(2, 3))
            frame = row * stride
            if float((moved > floor).mean()) > _SCENE_CUT_SHARE and frame - starts[-1] >= step // 4:
                starts.append(frame)
        previous = current
    filled: list[int] = []
    for index, start in enumerate(starts):
        stop = starts[index + 1] if index + 1 < len(starts) else total
        filled.extend(range(start, stop, step))

    spaced: list[int] = []
    for start in filled:
        if not spaced or start - spaced[-1] >= minimum:
            spaced.append(start)
    return spaced


def _epoch_samples(
    grids: npt.NDArray[np.uint16], request: BakeRequest
) -> list[tuple[int, npt.NDArray[np.uint16]]] | None:
    if request.palette_epoch_seconds <= 0.0:
        return None
    step = int(request.palette_epoch_seconds * float(frames.VBLANK_FPS))
    if step <= 0:
        return None
    stride = max(1, request.sample_stride)
    total = frames.frame_count(seconds=request.duration)
    buckets: list[tuple[int, npt.NDArray[np.uint16]]] = []
    minimum = epoch_upload_frames(request.palette_count)
    for start in _epoch_starts(
        grids, step, stride, total, floor=request.scene_cut_floor, minimum=minimum
    ):
        stop = min(start + step, total)
        rows = grids[start // stride : (stop + stride - 1) // stride]
        if rows.shape[0] == 0:
            continue
        tiles = rows.reshape(-1, encode.TILE_PX, encode.TILE_PX)
        buckets.append((start, _thin_sample(tiles, request.seed + start)))
    return buckets or None


def run(request: BakeRequest) -> BakeOutcome:
    sample_clip = frames.sample(
        request.source,
        start=request.start,
        duration=request.duration,
        stride=max(1, request.sample_stride),
        fit=request.fit,
        denoise=request.denoise,
        motion_blur=request.motion_blur,
    )
    sample_grids = encode.to_tiles(neocolor.rgb_to_color_index(sample_clip))
    del sample_clip
    epoch_samples = _epoch_samples(sample_grids, request)
    sample_tiles = _thin_sample(
        sample_grids.reshape(-1, encode.TILE_PX, encode.TILE_PX), request.seed
    )
    del sample_grids

    preview = _PreviewWriter(request.preview) if request.preview else None
    chunks = frames.stream(
        request.source,
        start=request.start,
        duration=request.duration,
        fit=request.fit,
        denoise=request.denoise,
        motion_blur=request.motion_blur,
    )
    result = encode.encode_stream(
        chunks,
        encode.EncodeOptions(
            palette_count=request.palette_count,
            base_bank=request.base_bank,
            keyframe_interval=request.keyframe_interval,
            tolerance=request.tolerance,
            scene_cut_ratio=request.scene_cut_ratio,
            candidates=request.candidates,
            allow_flip=request.allow_flip,
            sample_stride=request.sample_stride,
            seed=request.seed,
            frame_hold=request.frame_hold,
            motion_masking=request.motion_masking,
            dither=request.dither,
            chroma_weight=request.chroma_weight,
            scene_cut_floor=request.scene_cut_floor,
            tile_budget=request.tile_budget,
            stop_when_over_budget=request.stop_when_over_budget,
            collect_rendered=False,
        ),
        sample_tiles=sample_tiles,
        epoch_samples=epoch_samples,
        total_frames=frames.frame_count(seconds=request.duration),
        on_render=preview.write if preview else None,
    )
    if preview:
        preview.close()

    baked = request.build_dir / "baked"
    baked.mkdir(parents=True, exist_ok=True)
    c1, c2 = result.dictionary.rom_images(pad_to=result.dictionary.payload_bytes())
    payload = {
        "c1": (baked / "c1.bin", c1),
        "c2": (baked / "c2.bin", c2),
        "stream": (baked / "stream.bin", result.stream.blob()),
        "index": (baked / "index.bin", result.stream.index_blob()),
        "keyframes": (baked / "keyframes.bin", result.stream.keyframe_blob()),
        "palettes": (baked / "palettes.bin", _palette_blob(result)),
        "epochs": (baked / "epochs.bin", _epoch_blob(result)),
        "subtitles": (baked / "subtitles.bin", _subtitle_blob(request)),
        "fix": (baked / "fix.s1", fixtiles.build_rom(pad_to=S_ROM_BYTES)),
        "fixpal": (
            baked / "fixpal.bin",
            b"".join(word.to_bytes(2, "big") for word in fixtiles.palette_words()),
        ),
    }
    artifacts: dict[str, Path] = {}
    for key, (path, blob) in payload.items():
        data = blob if len(blob) % 2 == 0 else blob + b"\x00"
        path.write_bytes(data)
        artifacts[key] = path

    audio_pages = Fraction(0)
    rate_hz = (
        request.audio_rate_hz
        if request.audio_rate_hz is not None
        else quality.audio_hz_for(request.duration / quality.SECONDS_PER_MINUTE)
    )
    if request.audio:
        samples = _decode_audio(request.source, request.start, request.duration, rate_hz)
        if samples.size:
            encoded = adpcmb.encode(samples, rate_hz=rate_hz)
            voice = adpcmb.build_rom(encoded, pad_to=max(V_ROM_MIN_BYTES, len(encoded.payload)))
            (baked / "v2.bin").write_bytes(voice)
            artifacts["voice"] = baked / "v2.bin"
            _write_audio_params(request.build_dir, encoded)
            audio_pages = audio_pages_per_frame(encoded.delta_n)

    asm, header = _write_sources(
        request.build_dir,
        artifacts,
        result,
        request,
        audio_pages=audio_pages,
        audio_hz=rate_hz,
    )
    artifacts["asm"] = asm
    artifacts["header"] = header
    for bank, stub in enumerate(
        _write_stream_banks(request.build_dir, artifacts["stream"], result.stream.bank_count())
    ):
        artifacts[f"stream_bank{bank}"] = stub

    if request.preview is not None:
        artifacts["preview"] = request.preview

    return BakeOutcome(
        request=request, result=result, build_dir=request.build_dir, artifacts=artifacts
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bake a video clip into Neo Geo cart data.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--quality", default=None)
    parser.add_argument(
        "--audio-rate",
        type=arguments.number(
            low=limits.MIN_AUDIO_RATE_HZ, high=limits.MAX_AUDIO_RATE_HZ, name="--audio-rate"
        ),
        default=None,
    )
    parser.add_argument(
        "--start",
        type=arguments.number(low=0.0, high=limits.MAX_SOURCE_SECONDS, name="--start"),
        default=0.0,
    )
    parser.add_argument(
        "--duration",
        type=arguments.number(
            low=limits.MIN_SECONDS, high=limits.MAX_SOURCE_SECONDS, name="--duration"
        ),
        default=None,
    )
    parser.add_argument("--subtitles", type=Path, default=None)
    parser.add_argument("--build-dir", type=Path, default=Path("build"))
    parser.add_argument("--fit", choices=("fill", "letterbox"), default="fill")
    parser.add_argument(
        "--denoise",
        type=arguments.number(low=0.0, high=limits.MAX_DENOISE, name="--denoise"),
        default=None,
    )
    parser.add_argument(
        "--frame-hold",
        type=arguments.count(low=1, high=limits.MAX_FRAME_HOLD, name="--frame-hold"),
        default=None,
    )
    parser.add_argument(
        "--motion-blur",
        type=arguments.count(low=0, high=limits.MAX_MOTION_BLUR, name="--motion-blur"),
        default=0,
    )
    parser.add_argument(
        "--target-fps",
        type=arguments.number(
            low=limits.MIN_TARGET_FPS, high=float(frames.VBLANK_FPS), name="--target-fps"
        ),
        default=None,
    )
    parser.add_argument(
        "--motion-masking",
        type=arguments.number(low=0.0, high=limits.MAX_MOTION_MASKING, name="--motion-masking"),
        default=0.0,
    )
    parser.add_argument(
        "--dither",
        action="store_true",
        help="ordered threshold across palette entries, to break up banding",
    )
    parser.add_argument(
        "--chroma-weight",
        type=arguments.number(
            low=limits.MIN_CHROMA_WEIGHT, high=limits.MAX_CHROMA_WEIGHT, name="--chroma-weight"
        ),
        default=None,
    )
    parser.add_argument(
        "--scene-cut-floor",
        type=arguments.number(low=0.0, high=limits.MAX_FRACTION, name="--scene-cut-floor"),
        default=None,
    )
    parser.add_argument(
        "--palette-epoch-seconds",
        type=arguments.number(
            low=0.0, high=limits.MAX_SOURCE_SECONDS, name="--palette-epoch-seconds"
        ),
        default=None,
    )
    parser.add_argument(
        "--tile-budget",
        type=arguments.count(low=1, high=limits.MAX_TILES, name="--tile-budget"),
        default=None,
    )
    parser.add_argument(
        "--stop-when-over-budget",
        action="store_true",
        help="abandon the bake once it cannot finish, instead of encoding the rest",
    )
    parser.add_argument(
        "--palette-count",
        type=arguments.count(low=1, high=limits.MAX_PALETTES, name="--palette-count"),
        default=240,
    )
    parser.add_argument(
        "--base-bank",
        type=arguments.count(low=0, high=limits.MAX_PALETTES - 1, name="--base-bank"),
        default=16,
    )
    parser.add_argument(
        "--keyframe-interval",
        type=arguments.count(low=1, high=limits.MAX_FRAMES, name="--keyframe-interval"),
        default=90,
    )
    parser.add_argument(
        "--tolerance",
        type=arguments.number(low=0.0, high=limits.MAX_FRACTION, name="--tolerance"),
        default=None,
    )
    parser.add_argument(
        "--scene-cut-ratio",
        type=arguments.number(low=0.0, high=limits.MAX_FRACTION, name="--scene-cut-ratio"),
        default=0.90,
    )
    parser.add_argument(
        "--candidates",
        type=arguments.count(low=0, high=limits.MAX_PALETTES, name="--candidates"),
        default=None,
    )
    parser.add_argument("--flip", action="store_true")
    parser.add_argument(
        "--sample-stride",
        type=arguments.count(low=1, high=limits.MAX_FRAMES, name="--sample-stride"),
        default=None,
    )
    parser.add_argument(
        "--seed", type=arguments.count(low=0, high=limits.MAX_SEED, name="--seed"), default=0
    )
    parser.add_argument("--preview", type=Path, default=None)
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument("--bundle", type=Path, default=None)
    return parser.parse_args(argv)


def _resolve_duration(args: argparse.Namespace) -> float:
    if args.duration is not None:
        return float(args.duration)
    return max(0.0, ffmpeg.probe(args.source).duration - float(args.start))


def _resolve_quality(args: argparse.Namespace) -> quality.Tier | None:
    if args.quality is None:
        return None
    if args.quality == "auto":
        message = (
            "'auto' is gone: it guessed the tier from a sample and the guess was wrong "
            "in both directions. Name a rung, or let the cartridge tool measure one "
            "with --quality search. To see the estimate without acting on it, run "
            "python -m neogeomedia.plan."
        )
        raise SystemExit(message)
    return quality.tier_by_name(args.quality)


def _pick[Knob: (int, float)](
    explicit: Knob | None, tier_value: Knob | None, fallback: Knob
) -> Knob:
    if explicit is not None:
        return explicit
    if tier_value is not None:
        return tier_value
    return fallback


def _resolve_frame_hold(args: argparse.Namespace, tier: quality.Tier | None) -> int:
    hold = int(_pick(args.frame_hold, tier.frame_hold if tier else None, 1))
    if args.target_fps is not None:
        hold = frames.hold_for_target_fps(args.target_fps)
    if hold <= 1:
        return 1
    source_fps = ffmpeg.probe(args.source).fps
    if frames.source_frames_kept(hold, source_fps) >= 1.0:
        effective = float(frames.VBLANK_FPS) / hold
        msg = (
            f"a hold of {hold} runs at {effective:.1f} fps, at or above the source's "
            f"{float(source_fps):.1f} fps, so it drops no source frame and saves no tiles. "
            f"Use a hold of {int(float(frames.VBLANK_FPS) // float(source_fps)) + 1} or more."
        )
        raise SystemExit(msg)
    return hold


def _overran(report: dict[str, object]) -> bool:
    return (
        bool(report.get("dictionary_full"))
        or bool(report.get("budget_exceeded"))
        or bool(report.get("truncated"))
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    args.duration = _resolve_duration(args)
    if args.source.is_file() and not has_audio_stream(args.source):
        print(
            f"{args.source} carries no audio track, so the cartridge will be silent. "
            "Nothing is wrong with the video; there is simply no soundtrack to encode.",
            file=sys.stderr,
        )
    tier = _resolve_quality(args)
    profile = content.measure(args.source, duration=_PROFILE_SECONDS)
    scene_cut_floor = (
        args.scene_cut_floor
        if args.scene_cut_floor is not None
        else content.movement_floor(args.source)
    )
    palette_epoch_seconds = (
        args.palette_epoch_seconds
        if args.palette_epoch_seconds is not None
        else content.epoch_seconds_for(cuts_per_minute=profile.cuts_per_minute)
    )
    sample_stride = (
        args.sample_stride
        if args.sample_stride is not None
        else stride_for_epoch(epoch_frames=round(palette_epoch_seconds * float(frames.VBLANK_FPS)))
    )
    print(
        f"measured from the source: scene cut floor {scene_cut_floor:.5f},"
        f" palette epoch {palette_epoch_seconds:.1f}s"
        f" ({profile.cuts_per_minute:.1f} cuts/min, saturation {profile.saturation:.1f}),"
        f" palette sample every {sample_stride} frames",
        file=sys.stderr,
    )
    frame_hold = _resolve_frame_hold(args, tier)
    tile_budget = quality.CROM_TILES if tier is not None else None
    audio_rate = args.audio_rate
    if audio_rate is None:
        audio_rate = quality.audio_hz_for(args.duration / quality.SECONDS_PER_MINUTE)
    outcome = run(
        BakeRequest(
            source=args.source,
            start=args.start,
            duration=args.duration,
            build_dir=args.build_dir,
            subtitles=args.subtitles,
            fit=args.fit,
            denoise=_pick(args.denoise, tier.denoise if tier else None, 0.0),
            frame_hold=frame_hold,
            motion_blur=args.motion_blur,
            motion_masking=args.motion_masking,
            dither=args.dither,
            chroma_weight=_pick(args.chroma_weight, tier.chroma_weight if tier else None, 1.0),
            scene_cut_floor=scene_cut_floor,
            palette_epoch_seconds=palette_epoch_seconds,
            quality=tier.name if tier is not None else args.quality,
            tile_budget=_pick(args.tile_budget, tile_budget, 0),
            stop_when_over_budget=args.stop_when_over_budget,
            palette_count=args.palette_count,
            base_bank=args.base_bank,
            keyframe_interval=args.keyframe_interval,
            tolerance=_pick(args.tolerance, tier.tolerance if tier else None, 0.0005),
            scene_cut_ratio=args.scene_cut_ratio,
            candidates=_pick(args.candidates, tier.candidates if tier else None, 12),
            allow_flip=args.flip,
            sample_stride=sample_stride,
            seed=args.seed,
            preview=args.preview,
            audio_rate_hz=audio_rate,
        )
    )
    report = outcome.report()
    if _overran(report):
        print(
            f"the dictionary ran out at tier '{args.quality}': "
            f"{report['tile_count']} tiles with the film unfinished. "
            "Everything past that point stops tracking the source. "
            "Choose a cheaper tier, or run the cartridge tool with "
            "--quality search to measure one.",
            file=sys.stderr,
        )
    if args.bundle is not None:
        layout = write_movie_bundle(args.bundle, outcome)
        print(f"wrote a drop-in bundle to {layout.root}", file=sys.stderr)
    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return OVERRAN if _overran(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
