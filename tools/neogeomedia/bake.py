from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Final, TypedDict

import numpy as np
import numpy.typing as npt
from fmvcore import ffmpeg

from neogeomedia import (
    bakeargs,
    blobs,
    bundle,
    codegen,
    crom,
    encode,
    epochs,
    frames,
    neocolor,
    preview,
    quality,
    soundtrack,
)
from neogeomedia import stream as stream_mod

SECONDS_PER_MINUTE: Final = 60.0
OVERRAN: Final = 4
TIER_NAME_CHARS: Final = 8


@dataclass(frozen=True, slots=True)
class BakeRequest:
    source: Path
    start: float
    duration: float
    build_dir: Path
    fit: frames.FitMode = "fill"
    palette_count: int = bakeargs.DEFAULT_PALETTE_COUNT
    base_bank: int = bakeargs.DEFAULT_BASE_BANK
    keyframe_interval: int = bakeargs.DEFAULT_KEYFRAME_INTERVAL
    tolerance: float = bakeargs.DEFAULT_TOLERANCE
    scene_cut_ratio: float = bakeargs.DEFAULT_SCENE_CUT_RATIO
    candidates: int = bakeargs.DEFAULT_CANDIDATES
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


class TierKnobs(TypedDict):
    denoise: float
    chroma_weight: float
    quality: str | None
    tile_budget: int
    tolerance: float
    candidates: int
    frame_hold: int
    audio_rate_hz: float


@dataclass(frozen=True, slots=True)
class BakeOutcome:
    request: BakeRequest
    result: encode.EncodeResult
    build_dir: Path
    artifacts: dict[str, Path] = field(default_factory=dict)

    def report(self) -> dict[str, Any]:
        seconds = self.result.stats.frames / float(frames.VBLANK_FPS)
        head = {"frames": self.result.stats.frames, "seconds": round(seconds, 3)}
        minutes = seconds / SECONDS_PER_MINUTE
        return {**head, **self._settings(), **self._sizes(), **self._projections(minutes)}

    def _settings(self) -> dict[str, Any]:
        request = self.request
        return {
            "denoise": request.denoise,
            "frame_hold": request.frame_hold,
            "motion_blur": request.motion_blur,
            "motion_masking": request.motion_masking,
            "dither": request.dither,
            "chroma_weight": request.chroma_weight,
            "scene_cut_floor": request.scene_cut_floor,
            "palette_epoch_seconds": request.palette_epoch_seconds,
            "palette_epochs": len(self.result.palette_sets),
            "has_audio": "voice" in self.artifacts,
            "tile_budget": request.tile_budget,
        }

    def _sizes(self) -> dict[str, Any]:
        stats = self.result.stats
        return {
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
        }

    def _projections(self, minutes: float) -> dict[str, Any]:
        crom_per_minute = self.result.stats.crom_payload_bytes / minutes
        stream_per_minute = self.result.stats.stream_bytes / minutes
        return {
            "projected_crom_bytes_per_minute": round(crom_per_minute),
            "projected_stream_bytes_per_minute": round(stream_per_minute),
            "projected_minutes_per_crom_bank": round(codegen.CROM_BANK_BYTES / crom_per_minute, 2),
        }


def self_tier_name(request: BakeRequest) -> str:
    return (request.quality or "custom").upper()[:TIER_NAME_CHARS]


def write_movie_bundle(target: Path, outcome: BakeOutcome) -> bundle.BundleLayout:
    stats = outcome.result.stats
    return bundle.write_bundle(
        target=target,
        build_dir=outcome.build_dir,
        figures=bundle.MovieFigures(
            stream_banks=outcome.result.stream.bank_count(),
            max_updates=stats.max_updates,
            tick_cycles=stats.max_updates * codegen.CYCLES_PER_UPDATE,
            tile_count=stats.tile_count,
            crom_payload=outcome.result.dictionary.payload_bytes(),
            crom_size=crom.rom_size_for(stats.tile_count),
            palette_base=outcome.result.palette_set.base_bank,
            first_sprite=stream_mod.FIRST_SPRITE,
            frames=stats.frames,
            version=codegen.baker_version(),
        ),
    )


def _palette_sample(
    request: BakeRequest,
) -> tuple[list[epochs.EpochSample] | None, npt.NDArray[np.uint16]]:
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
    epoch_samples = epochs.epoch_samples(
        sample_grids,
        epoch_seconds=request.palette_epoch_seconds,
        sample_stride=request.sample_stride,
        duration=request.duration,
        palette_count=request.palette_count,
        scene_cut_floor=request.scene_cut_floor,
        seed=request.seed,
    )
    tiles = sample_grids.reshape(-1, encode.TILE_PX, encode.TILE_PX)
    return epoch_samples, epochs.thin_sample(tiles, request.seed)


def _encode_options(request: BakeRequest) -> encode.EncodeOptions:
    return encode.EncodeOptions(
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
    )


def _encode(request: BakeRequest) -> encode.EncodeResult:
    epoch_samples, sample_tiles = _palette_sample(request)
    writer = preview.PreviewWriter(request.preview) if request.preview else None
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
        _encode_options(request),
        sample_tiles=sample_tiles,
        epoch_samples=epoch_samples,
        total_frames=frames.frame_count(seconds=request.duration),
        on_render=writer.write if writer else None,
    )
    if writer:
        writer.close()
    return result


def _audio_rate(request: BakeRequest) -> float:
    if request.audio_rate_hz is not None:
        return request.audio_rate_hz
    return quality.audio_hz_for(request.duration / quality.SECONDS_PER_MINUTE)


def _bake_voice(request: BakeRequest, baked: Path, rate_hz: float) -> soundtrack.Voice:
    if not request.audio:
        return soundtrack.Voice(path=None, pages=Fraction(0))
    return soundtrack.bake_voice(
        source=request.source,
        start=request.start,
        duration=request.duration,
        rate_hz=rate_hz,
        baked=baked,
        build_dir=request.build_dir,
    )


def _write_cart_data(request: BakeRequest, result: encode.EncodeResult) -> dict[str, Path]:
    baked = request.build_dir / "baked"
    baked.mkdir(parents=True, exist_ok=True)
    subtitle = blobs.subtitle_blob(
        source=request.source,
        explicit=request.subtitles,
        start=request.start,
        duration=request.duration,
    )
    artifacts = blobs.write_payload(blobs.cart_payload(baked, result, subtitle))
    rate_hz = _audio_rate(request)
    voice = _bake_voice(request, baked, rate_hz)
    voiced = artifacts if voice.path is None else {**artifacts, "voice": voice.path}
    settings = codegen.SourceSettings(
        tier_name=self_tier_name(request),
        chroma_weight=request.chroma_weight,
        frame_hold=request.frame_hold,
        audio_pages=voice.pages,
        audio_hz=rate_hz,
    )
    asm, header = codegen.write_sources(request.build_dir, voiced, result, settings)
    return {**voiced, "asm": asm, "header": header}


def run(request: BakeRequest) -> BakeOutcome:
    result = _encode(request)
    artifacts = _write_cart_data(request, result)
    stubs = codegen.write_stream_banks(
        request.build_dir, artifacts["stream"], result.stream.bank_count()
    )
    banks = {f"stream_bank{bank}": stub for bank, stub in enumerate(stubs)}
    previewed = {} if request.preview is None else {"preview": request.preview}
    return BakeOutcome(
        request=request,
        result=result,
        build_dir=request.build_dir,
        artifacts={**artifacts, **banks, **previewed},
    )


def _overran(report: dict[str, object]) -> bool:
    return (
        bool(report.get("dictionary_full"))
        or bool(report.get("budget_exceeded"))
        or bool(report.get("truncated"))
    )


def _announce_silence(source: Path) -> None:
    if source.is_file() and not ffmpeg.has_audio(source):
        print(
            f"{source} carries no audio track, so the cartridge will be silent. "
            "Nothing is wrong with the video; there is simply no soundtrack to encode.",
            file=sys.stderr,
        )


def _audio_rate_for(args: argparse.Namespace) -> float:
    if args.audio_rate is not None:
        return float(args.audio_rate)
    return quality.audio_hz_for(args.duration / quality.SECONDS_PER_MINUTE)


def _tier_knobs(args: argparse.Namespace, tier: quality.Tier | None, frame_hold: int) -> TierKnobs:
    tile_budget = quality.CROM_TILES if tier is not None else None
    return {
        "frame_hold": frame_hold,
        "audio_rate_hz": _audio_rate_for(args),
        "denoise": bakeargs.pick(args.denoise, tier.denoise if tier else None, 0.0),
        "chroma_weight": bakeargs.pick(
            args.chroma_weight, tier.chroma_weight if tier else None, 1.0
        ),
        "quality": tier.name if tier is not None else args.quality,
        "tile_budget": bakeargs.pick(args.tile_budget, tile_budget, 0),
        "tolerance": bakeargs.pick(
            args.tolerance, tier.tolerance if tier else None, bakeargs.DEFAULT_TOLERANCE
        ),
        "candidates": bakeargs.pick(
            args.candidates, tier.candidates if tier else None, bakeargs.DEFAULT_CANDIDATES
        ),
    }


def _request_from(
    args: argparse.Namespace, measured: bakeargs.Measured, knobs: TierKnobs
) -> BakeRequest:
    return BakeRequest(
        source=args.source,
        start=args.start,
        duration=args.duration,
        build_dir=args.build_dir,
        subtitles=args.subtitles,
        fit=args.fit,
        motion_blur=args.motion_blur,
        motion_masking=args.motion_masking,
        dither=args.dither,
        scene_cut_floor=measured.scene_cut_floor,
        palette_epoch_seconds=measured.palette_epoch_seconds,
        stop_when_over_budget=args.stop_when_over_budget,
        palette_count=args.palette_count,
        base_bank=args.base_bank,
        keyframe_interval=args.keyframe_interval,
        scene_cut_ratio=args.scene_cut_ratio,
        allow_flip=args.flip,
        sample_stride=measured.sample_stride,
        seed=args.seed,
        preview=args.preview,
        **knobs,
    )


def _finish(args: argparse.Namespace, outcome: BakeOutcome) -> int:
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


def main(argv: list[str] | None = None) -> int:
    args = bakeargs.parse_args(sys.argv[1:] if argv is None else argv)
    args.duration = bakeargs.resolve_duration(args)
    _announce_silence(args.source)
    tier = bakeargs.resolve_quality(args)
    measured = bakeargs.measured_settings(args)
    frame_hold = bakeargs.resolve_frame_hold(args, tier)
    outcome = run(_request_from(args, measured, _tier_knobs(args, tier, frame_hold)))
    return _finish(args, outcome)


if __name__ == "__main__":
    raise SystemExit(main())
