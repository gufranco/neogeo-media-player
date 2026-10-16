from __future__ import annotations

import argparse
import struct
import tempfile
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import arguments, libretro
from fmvcore.libretro import Joypad

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
HOLD_MARK: Final = ":"
BUTTON_JOIN: Final = "+"
BUTTONS: Final = {
    "a": Joypad.B,
    "b": Joypad.A,
    "c": Joypad.Y,
    "d": Joypad.X,
    "start": Joypad.START,
    "select": Joypad.SELECT,
    "up": Joypad.UP,
    "down": Joypad.DOWN,
    "left": Joypad.LEFT,
    "right": Joypad.RIGHT,
}


def core_options(*, full_raster: bool) -> dict[str, str]:
    if not full_raster:
        return dict(SYSTEM_TYPE)
    return {**SYSTEM_TYPE, **{f"geolith_overscan_{side}": "0" for side in OVERSCAN_SIDES}}


def parse_hold(text: str) -> tuple[int, frozenset[Joypad]]:
    frame, mark, names = text.partition(HOLD_MARK)
    if not mark or not frame.isdigit() or not names:
        msg = f"a hold reads FRAME:BUTTON[+BUTTON], got {text!r}"
        raise argparse.ArgumentTypeError(msg)
    unknown = [name for name in names.split(BUTTON_JOIN) if name not in BUTTONS]
    if unknown:
        msg = f"unknown button {unknown[0]!r}; use {', '.join(sorted(BUTTONS))}"
        raise argparse.ArgumentTypeError(msg)
    return int(frame), frozenset(BUTTONS[name] for name in names.split(BUTTON_JOIN))


def _schedule(holds: Sequence[tuple[int, frozenset[Joypad]]]) -> Mapping[int, frozenset[int]]:
    schedule: dict[int, frozenset[int]] = {}
    for frame, buttons in holds:
        schedule = {**schedule, frame: schedule.get(frame, frozenset()) | buttons}
    return schedule


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
    parser.add_argument("--hold", type=parse_hold, action="append", default=[])
    saved = arguments.count(low=0, high=limits.MAX_FRAMES, name="--save")
    parser.add_argument("--save", type=saved, action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    last = args.frames - 1
    with tempfile.TemporaryDirectory() as saves:
        shots = libretro.capture(
            args.core,
            args.rom,
            frames=args.frames,
            system_dir=args.system_dir,
            keep=frozenset({last, *args.save}),
            options=core_options(full_raster=args.full_raster),
            held=_schedule(args.hold),
            save_dir=Path(saves),
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for index, frame in shots:
        target = args.out if index == last else _beside(args.out, index)
        write_png(target, frame)
        print(target)


def _beside(out: Path, index: int) -> Path:
    return out.with_name(f"{out.stem}-{index:05d}{out.suffix}")


if __name__ == "__main__":
    main()
