from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import capture as core
from fmvcore import colour, libretro

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capture_rom

from neogeomedia import frames

RASTER_WIDTH: Final = 320
PANEL_TOP: Final = 184
LAG_WINDOW: Final = 120
SAMPLE_EVERY: Final = 4

Frames = npt.NDArray[np.uint8]


def crop_like_capture(raster: Frames, *, width: int) -> Frames:
    margin = RASTER_WIDTH - width
    if margin < 0 or margin % 2:
        msg = f"a capture {width} pixels wide is not {RASTER_WIDTH} less an even overscan"
        raise ValueError(msg)
    side = margin // 2
    return raster[:, :, side : RASTER_WIDTH - side]


def measure(shown: Frames, source: Frames, *, rate: float, window: int) -> dict[str, float]:
    picture = shown[:, :PANEL_TOP]
    wanted = source[:, :PANEL_TOP]
    fields = list(range(min(picture.shape[0], wanted.shape[0])))
    lags = core.measured_lags(picture, wanted, completes=fields, window=window)
    pairs = list(zip(fields, lags, strict=False))[::SAMPLE_EVERY]
    matched = [colour.oklab_error(picture[f], wanted[f - lag]) for f, lag in pairs]
    blurred = [colour.blurred_error(picture[[f]], wanted[[f - lag]]) for f, lag in pairs]
    median = int(np.median(lags))
    return {
        "frames": len(fields),
        "frame_error": float(np.mean(matched)),
        "blurred_frame_error": float(np.mean(blurred)),
        "mixed_share": core.mixed_share(picture, completes=fields),
        "lag_first_frames": lags[0],
        "lag_median_frames": median,
        "lag_last_frames": lags[-1],
        "lag_median_s": median / rate,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Play the cartridge headless and measure it against its source film."
    )
    parser.add_argument("--rom", type=Path, default=capture_rom.DEFAULT_ROM)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--film-frame", type=int, required=True)
    parser.add_argument("--core", type=Path, default=capture_rom.DEFAULT_CORE)
    parser.add_argument("--system-dir", type=Path, default=capture_rom.DEFAULT_SYSTEM)
    parser.add_argument("--json", type=Path, default=None)
    return parser


def _played(args: argparse.Namespace, count: int) -> Frames:
    first = args.film_frame
    with tempfile.TemporaryDirectory() as saves:
        shots = libretro.capture(
            args.core,
            args.rom,
            frames=first + count,
            system_dir=args.system_dir,
            keep=frozenset(range(first, first + count)),
            options=capture_rom.core_options(full_raster=False),
            save_dir=Path(saves),
        )
    return np.stack([frame for _, frame in shots])


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    source = frames.decode(args.source, start=args.start, duration=args.duration)
    shown = _played(args, source.shape[0])
    report = measure(
        shown,
        crop_like_capture(source, width=shown.shape[2]),
        rate=float(frames.VBLANK_FPS),
        window=LAG_WINDOW,
    )
    text = json.dumps(report, indent=2)
    print(text)
    if args.json is not None:
        args.json.write_text(text + "\n")


if __name__ == "__main__":
    main()
