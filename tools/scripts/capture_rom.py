from __future__ import annotations

import argparse
import struct
import zlib
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import arguments, libretro

from neogeomedia import limits

DEFAULT_FRAMES: Final = 600
DEFAULT_ROM: Final = Path("build/neogeomedia.neo")
DEFAULT_OUT: Final = Path("build/last-capture.png")
DEFAULT_CORE: Final = (
    Path.home() / "Library/Application Support/RetroArch/cores/geolith_libretro.dylib"
)
DEFAULT_SYSTEM: Final = Path.home() / "Documents/RetroArch/system"
SYSTEM_TYPE: Final = {"geolith_system_type": "uni"}
OVERSCAN_SIDES: Final = ("t", "b", "l", "r")
PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
PNG_DEPTH: Final = 8
PNG_TRUECOLOUR: Final = 2
NO_FILTER: Final = b"\x00"


def core_options(*, full_raster: bool) -> dict[str, str]:
    if not full_raster:
        return dict(SYSTEM_TYPE)
    return {**SYSTEM_TYPE, **{f"geolith_overscan_{side}": "0" for side in OVERSCAN_SIDES}}


def write_png(path: Path, frame: npt.NDArray[np.uint8]) -> None:
    height, width = frame.shape[0], frame.shape[1]
    rows = b"".join(NO_FILTER + frame[row].tobytes() for row in range(height))
    header = struct.pack(">IIBBBBB", width, height, PNG_DEPTH, PNG_TRUECOLOUR, 0, 0, 0)
    chunks = (_chunk(b"IHDR", header), _chunk(b"IDAT", zlib.compress(rows)), _chunk(b"IEND", b""))
    path.write_bytes(PNG_SIGNATURE + b"".join(chunks))


def _chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind + payload)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the cartridge headless in geolith and save the last frame as a PNG."
    )
    frames = arguments.count(low=1, high=limits.MAX_FRAMES, name="--frames")
    parser.add_argument("--frames", type=frames, default=DEFAULT_FRAMES)
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--system-dir", type=Path, default=DEFAULT_SYSTEM)
    parser.add_argument("--full-raster", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    last = args.frames - 1
    [(_, frame)] = libretro.capture(
        args.core,
        args.rom,
        frames=args.frames,
        system_dir=args.system_dir,
        keep=frozenset({last}),
        options=core_options(full_raster=args.full_raster),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_png(args.out, frame)
    print(args.out)


if __name__ == "__main__":
    main()
