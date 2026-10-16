from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fmvcore import ffmpeg

from neogeomedia import calibrate, frames, quality


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="neogeomedia plan",
        description="Measure a source and report which quality tiers fit a cartridge.",
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=calibrate.DEFAULT_SAMPLE_COUNT)
    parser.add_argument("--sample-seconds", type=float, default=calibrate.DEFAULT_SAMPLE_SECONDS)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args(argv)


def _calibrate(
    args: argparse.Namespace, info: ffmpeg.SourceInfo
) -> tuple[float, dict[float, float]]:
    windows = calibrate.sample_windows(
        info.duration, count=args.samples, seconds=args.sample_seconds
    )
    sampled = sum(span for _, span in windows)
    print(
        f"Calibrating on {len(windows)} sample(s), {sampled:.0f}s of"
        f" {info.duration:.0f}s, at the '{quality.REFERENCE_TIER}' tier...",
        file=sys.stderr,
    )
    return calibrate.measure_anchors(
        args.source,
        count=args.samples,
        seconds=args.sample_seconds,
        seed=args.seed,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    info = ffmpeg.probe(args.source)
    rate, anchors = _calibrate(args, info)
    print(
        quality.format_plan(
            source=str(args.source),
            minutes=info.duration / quality.SECONDS_PER_MINUTE,
            width=info.width,
            height=info.height,
            source_fps=float(info.fps),
            has_audio=ffmpeg.has_audio(args.source),
            reference_rate=rate,
            vblank_fps=float(frames.VBLANK_FPS),
            anchors=anchors,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
