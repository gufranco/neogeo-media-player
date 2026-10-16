from __future__ import annotations

import argparse
import struct
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neogeomedia import neocolor
from tests.geolith_model import GeolithTileReader, StreamPlayer

RASTER_WIDTH = 320
RASTER_HEIGHT = 224

TIE = 1e-9


def tied_run(scored: dict[int, float], best: int) -> set[int]:
    run = {best}
    for direction in (-1, 1):
        step = best
        while step + direction in scored and abs(scored[step + direction] - scored[best]) <= TIE:
            step += direction
            run.add(step)
    return run


def _decode_rgb(path: Path) -> bytes:
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
        check=True,
    ).stdout


def stream_preview(path: Path) -> Iterator[np.ndarray]:
    stride = RASTER_WIDTH * RASTER_HEIGHT * 3
    process = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )
    if process.stdout is None:
        msg = "ffmpeg produced no output pipe"
        raise RuntimeError(msg)
    try:
        while True:
            payload = process.stdout.read(stride)
            if len(payload) < stride:
                return
            yield np.frombuffer(payload, np.uint8).reshape(RASTER_HEIGHT, RASTER_WIDTH, 3)
    finally:
        process.stdout.close()
        process.wait()


def decode_capture(path: Path) -> np.ndarray:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    width, height = (int(part) for part in probe.stdout.strip().split(","))
    return np.frombuffer(_decode_rgb(path), np.uint8).reshape(height, width, 3)


def downscale_capture(capture: np.ndarray) -> np.ndarray:
    height, width = capture.shape[:2]
    if height % RASTER_HEIGHT != 0:
        return capture
    factor = height // RASTER_HEIGHT
    if factor < 2 or width % factor != 0:
        return capture
    offset = factor // 2
    return capture[offset::factor, offset::factor]


def _palette_colors(blob: bytes) -> np.ndarray:
    words = np.frombuffer(blob, ">u2").reshape(-1, neocolor.PALETTE_COLORS)[:, 1:]
    r5 = ((words >> 8) & 0x0F) << 1 | ((words >> 14) & 1)
    g5 = ((words >> 4) & 0x0F) << 1 | ((words >> 13) & 1)
    b5 = (words & 0x0F) << 1 | ((words >> 12) & 1)
    return ((r5 << 10) | (g5 << 5) | b5).astype(np.uint16)


def _epoch_palettes(baked: Path, frame: int, colors: np.ndarray) -> tuple[int, np.ndarray]:
    table = baked / "epochs.bin"
    if not table.is_file():
        return 0, colors
    starts = struct.unpack(f">{table.stat().st_size // 4}I", table.read_bytes())
    if len(starts) <= 1:
        return 0, colors
    epoch = 0
    while epoch + 1 < len(starts) and starts[epoch + 1] <= frame:
        epoch += 1
    per_epoch = colors.shape[0] // len(starts)
    return epoch, colors[epoch * per_epoch : (epoch + 1) * per_epoch]


def reconstruct_frame(baked: Path, frame: int, *, base_bank: int = 16) -> np.ndarray:
    baked = Path(baked)
    stream = (baked / "stream.bin").read_bytes()
    index = (baked / "index.bin").read_bytes()
    offsets = struct.unpack(f">{len(index) // 4}I", index)
    if not 0 <= frame < len(offsets):
        msg = f"frame {frame} is outside the {len(offsets)} frame movie"
        raise ValueError(msg)

    player = StreamPlayer()
    for step in range(frame + 1):
        player.apply(stream, offsets[step])

    reader = GeolithTileReader((baked / "c1.bin").read_bytes(), (baked / "c2.bin").read_bytes())
    colors = _palette_colors((baked / "palettes.bin").read_bytes())
    epoch, colors = _epoch_palettes(baked, frame, colors)
    return neocolor.color_index_to_rgb(
        player.render(reader, colors, base_bank + (epoch & 1) * colors.shape[0])
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Match a capture against the baked render.")
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--preview", type=Path, default=None)
    parser.add_argument("--baked", type=Path, default=None)
    parser.add_argument("--frame", type=int, default=None)
    parser.add_argument("--overscan", type=int, default=8)
    parser.add_argument("--max-mean-error", type=float, default=1.0)
    parser.add_argument("--min-separation", type=float, default=1.0)
    args = parser.parse_args(argv)

    if args.preview is None and args.baked is None:
        parser.error("pass either --preview or --baked")
    if args.baked is not None and args.frame is None:
        parser.error("--baked needs --frame")

    capture = downscale_capture(decode_capture(args.capture))

    height, width = capture.shape[:2]
    if height != RASTER_HEIGHT:
        print(
            f"capture height {height} is not the {RASTER_HEIGHT} line active area",
            file=sys.stderr,
        )
        return 2

    left = args.overscan
    right = RASTER_WIDTH - args.overscan
    if width != right - left:
        print(
            f"capture width {width} does not match a {args.overscan} pixel overscan",
            file=sys.stderr,
        )
        return 2

    reference = (
        stream_preview(args.preview)
        if args.preview is not None
        else iter([reconstruct_frame(args.baked, args.frame)])
    )
    target = capture.astype(np.int16)
    best, best_error, best_frame, count = -1, float("inf"), None, 0
    worst = 0.0
    scored: dict[int, float] = {}
    for index, frame in enumerate(reference):
        cropped = frame[:, left:right, :].astype(np.int16)
        error = float(np.abs(cropped - target).mean())
        scored[index] = error
        worst = max(worst, error)
        if error < best_error:
            best, best_error, best_frame = index, error, cropped
        count = index + 1
    if best_frame is None:
        print("the reference produced no frames", file=sys.stderr)
        return 2

    print(f"best match: rendered frame {best} of {count}")
    print(f"mean absolute error: {best_error:.4f} of 255")
    print(f"exact pixel match: {np.array_equal(best_frame.astype(np.uint8), capture)}")
    print(f"worst frame error: {worst:.4f}")

    rivals = {step: error for step, error in scored.items() if step not in tied_run(scored, best)}
    contender = min(rivals, key=lambda step: rivals[step]) if rivals else None
    if contender is not None:
        margin = rivals[contender] - best_error
        print(f"nearest rival: frame {contender} at {rivals[contender]:.4f}, {margin:.4f} behind")

    if best_error > args.max_mean_error:
        print(
            f"FAIL: best match error {best_error:.4f} exceeds {args.max_mean_error}",
            file=sys.stderr,
        )
        return 1

    if contender is not None and rivals[contender] - best_error < args.min_separation:
        print(
            f"AMBIGUOUS: frame {best} at {best_error:.4f} and frame {contender} at "
            f"{rivals[contender]:.4f} sit within {args.min_separation} of each other, so which "
            f"one the capture shows is a guess rather than a measurement",
            file=sys.stderr,
        )
        return 2

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
