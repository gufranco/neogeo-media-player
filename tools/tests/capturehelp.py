from __future__ import annotations

import importlib.util
import struct
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import numpy as np
from fmvcore.testing import SEED

from neogeomedia import neocolor
from tests.geolith_model import GRID_COLS, GRID_ROWS, SCB1_WORDS_PER_SPRITE, TILE_BYTES

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
WIDTH = 320
HEIGHT = 224
OVERSCAN = 8
BASE_BANK = 16
C5_LEVELS = 32
CAPTURE_RATE = "60"


def load_script(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        msg = f"cannot load {name}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def noise_frames(count: int, stream: int) -> np.ndarray:
    rng = np.random.default_rng((SEED, stream))
    return rng.integers(0, 256, size=(count, HEIGHT, WIDTH, 3), dtype=np.uint8)


def active(frame: np.ndarray) -> np.ndarray:
    return frame[:, OVERSCAN : WIDTH - OVERSCAN]


def _encode(path: Path, frames: np.ndarray, *output: str) -> None:
    height, width = frames.shape[-3:-1]
    command = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24"]
    command += ["-s", f"{width}x{height}", "-r", CAPTURE_RATE, "-i", "-", *output, str(path)]
    subprocess.run(command, input=frames.tobytes(), check=True)


def write_lossless(path: Path, frames: np.ndarray) -> Path:
    _encode(path, frames, "-c:v", "ffv1", "-level", "3", "-pix_fmt", "rgb24")
    return path


def write_png(path: Path, image: np.ndarray) -> Path:
    _encode(path, image, "-frames:v", "1")
    return path


def grey(level: int) -> int:
    return int(neocolor.C5_TO_SRGB8[level])


def _grey_palettes() -> bytes:
    index = np.array([(c5 << 10) | (c5 << 5) | c5 for c5 in range(C5_LEVELS)])
    words = neocolor.color_index_to_palette_word(index)
    return b"".join(struct.pack(">16H", 0, *([int(word)] * 15)) for word in words)


def _flat_frame(level: int) -> bytes:
    attr = (BASE_BANK + level) << 8
    runs = [
        struct.pack(">HH", (col + 1) * SCB1_WORDS_PER_SPRITE, GRID_ROWS)
        + struct.pack(">HH", 0, attr) * GRID_ROWS
        for col in range(GRID_COLS)
    ]
    return struct.pack(">H", GRID_COLS) + b"".join(runs)


def flat_bake(directory: Path, levels: Sequence[int]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    blobs = [_flat_frame(level) for level in levels]
    offsets = np.cumsum([0, *(len(blob) for blob in blobs[:-1])])
    (directory / "stream.bin").write_bytes(b"".join(blobs))
    (directory / "index.bin").write_bytes(struct.pack(f">{len(levels)}I", *offsets))
    (directory / "c1.bin").write_bytes(bytes([0xFF, 0x00]) * (TILE_BYTES // 4))
    (directory / "c2.bin").write_bytes(bytes(TILE_BYTES // 2))
    (directory / "palettes.bin").write_bytes(_grey_palettes())
    return directory


def flat_capture(path: Path, level: int) -> Path:
    shot = np.full((HEIGHT, WIDTH - 2 * OVERSCAN, 3), grey(level), dtype=np.uint8)
    return write_png(path, shot)
