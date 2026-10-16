from __future__ import annotations

import ctypes
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIBRARY_DIR = ROOT / "src" / "fmv"
STUB_DIR = Path(__file__).resolve().parent / "hwstub"

GRID_COLS = 20
GRID_ROWS = 14
PALETTE_WORDS = 16
EPOCH_PALETTES = 4
EPOCH_SLICE = 8
PALETTE_BASE = 16
FIRST_SPRITE = 1
FRAMES = 3

VRAM_SCB3 = 0x8200
SCB1_WORDS_PER_SPRITE = 64
SCB3_GRID_HEAD = 0xF80E
SCB3_GRID_STICKY = 0xF840
LSPC_DISABLE_AUTOANIM = 0x0008
PROM_BANK_BYTES = 0x100000

FMV_FIX_CART = 0
FMV_FIX_BOARD = 1
FMV_FINISHED = 0
FMV_SKIPPED = 1
FMV_CORRUPT = 2
FMV_PAD_A = 0x10
FMV_START = 0x01
SOUND_PLAY = 0x50
SOUND_STOP = 0x60
PAD_RELEASED = 0xFF

SKIP_FN = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
PLAYER_BYTES = 256

UINT16_RESULTS = (
    "fmv_epoch",
    "fmv_stream_bank",
    "fmv_test_lspc_mode",
    "fmv_test_prom_bank",
    "fmv_test_watchdog_kicks",
    "fmv_test_vblank_waits",
    "fmv_test_vram",
    "fmv_test_palram",
    "fmv_test_player_stream_bank",
    "fmv_test_player_updates",
    "fmv_test_player_epoch",
    "fmv_test_player_sprite_offset",
)
UINT8_RESULTS = (
    "fmv_test_fix_source",
    "fmv_test_palette_bank",
    "fmv_test_player_open",
    "fmv_test_last_sound_command",
)
SIZE_RESULTS = ("fmv_test_sizeof_options", "fmv_test_sizeof_movie", "fmv_test_sizeof_player")


class Options(ctypes.Structure):
    _fields_ = [
        ("first_sprite", ctypes.c_uint16),
        ("top_line", ctypes.c_uint16),
        ("left_pixel", ctypes.c_uint16),
        ("lspc_mode", ctypes.c_uint16),
        ("fix_source", ctypes.c_uint8),
        ("palette_bank", ctypes.c_uint8),
        ("prom_bank", ctypes.c_uint8),
        ("skip_pad", ctypes.c_uint8),
        ("skip_start", ctypes.c_uint8),
        ("audio", ctypes.c_uint8),
        ("skip", SKIP_FN),
        ("skip_user", ctypes.c_void_p),
    ]


class Movie(ctypes.Structure):
    _fields_ = [
        ("index", ctypes.c_void_p),
        ("keyframes", ctypes.c_void_p),
        ("palettes", ctypes.c_void_p),
        ("epochs", ctypes.c_void_p),
        ("subtitles", ctypes.c_void_p),
        ("stream_base", ctypes.c_uint32),
        ("frames", ctypes.c_uint32),
        ("keyframe_count", ctypes.c_uint32),
        ("fps_num", ctypes.c_uint32),
        ("fps_den", ctypes.c_uint32),
        ("audio_page_num", ctypes.c_uint32),
        ("audio_page_den", ctypes.c_uint32),
        ("epoch_count", ctypes.c_uint16),
        ("epoch_palettes", ctypes.c_uint16),
        ("epoch_slice", ctypes.c_uint16),
        ("palette_base", ctypes.c_uint16),
        ("first_sprite", ctypes.c_uint16),
        ("grid_cols", ctypes.c_uint16),
        ("grid_rows", ctypes.c_uint16),
        ("max_updates", ctypes.c_uint16),
        ("subtitle_count", ctypes.c_uint16),
        ("subtitle_columns", ctypes.c_uint16),
        ("subtitle_lines", ctypes.c_uint16),
    ]


def _stage(root: Path) -> Path:
    staged = root / "fmv"
    staged.mkdir()
    for source in sorted(LIBRARY_DIR.glob("*.[ch]")):
        shutil.copy2(source, staged / source.name)
    shutil.copy2(STUB_DIR / "hw.h", staged / "hw.h")
    shutil.copy2(STUB_DIR / "probe.c", staged / "probe.c")
    return staged


def _compile_command(compiler: str, staged: Path, library: Path, *, audio: bool) -> list[str]:
    sources = [staged / "fmv.c", staged / "guard.c", staged / "timeline.c", staged / "probe.c"]
    flags = ["-std=c99", "-O1", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", f"-I{staged}"]
    if audio:
        sources.append(staged / "fmv_audio.c")
    else:
        flags.append("-DFMV_NO_AUDIO")
    return [compiler, *flags, *(str(path) for path in sources), "-o", str(library)]


def _declare_results(loaded: Any) -> Any:
    loaded.fmv_defaults.restype = Options
    loaded.fmv_position.restype = ctypes.c_uint32
    loaded.fmv_ended.restype = ctypes.c_int
    loaded.fmv_last_updates.restype = ctypes.c_uint16
    loaded.fmv_play.restype = ctypes.c_int
    loaded.fmv_faulted.restype = ctypes.c_int
    loaded.fmv_test_player_frame.restype = ctypes.c_uint32
    for names, result in (
        (UINT16_RESULTS, ctypes.c_uint16),
        (UINT8_RESULTS, ctypes.c_uint8),
        (SIZE_RESULTS, ctypes.c_size_t),
    ):
        for name in names:
            getattr(loaded, name).restype = result
    return loaded


def build(tmp_path_factory: pytest.TempPathFactory, *, audio: bool) -> Any:
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("no host C compiler")
    name = "audio" if audio else "silent"
    root = tmp_path_factory.mktemp(f"fmv-{name}")
    library = root / f"libfmv-{name}.so"
    subprocess.run(_compile_command(compiler, _stage(root), library, audio=audio), check=True)
    return _declare_results(ctypes.CDLL(str(library)))


def keyframe_record() -> bytes:
    body = struct.pack("=H", 1)
    body += struct.pack("=HH", FIRST_SPRITE * SCB1_WORDS_PER_SPRITE, GRID_ROWS)
    for row in range(GRID_ROWS):
        body += struct.pack("=HH", 0x1000 + row, 0x0020)
    return body


def _words(*values: int) -> ctypes.Array[ctypes.c_uint8]:
    packed = b"".join(struct.pack("=I", value) for value in values)
    return (ctypes.c_uint8 * len(packed)).from_buffer_copy(packed)


def _palette_buffer() -> ctypes.Array[ctypes.c_uint8]:
    palettes = (ctypes.c_uint8 * (2 * EPOCH_PALETTES * PALETTE_WORDS))()
    for word in range(EPOCH_PALETTES * PALETTE_WORDS):
        struct.pack_into("=H", palettes, word * 2, 0x8000 | word)
    return palettes


def _layout() -> dict[str, int]:
    return {
        "stream_base": 0,
        "frames": FRAMES,
        "keyframe_count": 1,
        "fps_num": 15625,
        "fps_den": 264,
        "audio_page_num": 1,
        "audio_page_den": 1000,
        "epoch_count": 1,
        "epoch_palettes": EPOCH_PALETTES,
        "epoch_slice": EPOCH_SLICE,
        "palette_base": PALETTE_BASE,
        "first_sprite": FIRST_SPRITE,
        "grid_cols": GRID_COLS,
        "grid_rows": GRID_ROWS,
        "max_updates": GRID_ROWS,
        "subtitle_count": 0,
        "subtitle_columns": 40,
        "subtitle_lines": 2,
    }


def movie_for(library: Any) -> Movie:
    library.fmv_test_reset()
    record = keyframe_record()
    stream = (ctypes.c_uint8 * (len(record) * FRAMES)).from_buffer_copy(record * FRAMES)
    library.fmv_test_set_bank_window(stream)
    buffers = {
        "index": _words(*(frame * len(record) for frame in range(FRAMES))),
        "keyframes": _words(0),
        "palettes": _palette_buffer(),
        "epochs": _words(0),
        "subtitles": (ctypes.c_uint8 * 4)(),
    }
    pointers = {name: ctypes.cast(buffer, ctypes.c_void_p) for name, buffer in buffers.items()}
    value = Movie(**pointers, **_layout())
    value._keepalive = (*buffers.values(), stream)
    return value


def new_player() -> ctypes.Array[ctypes.c_uint8]:
    return (ctypes.c_uint8 * PLAYER_BYTES)()


def opened(library: Any, movie: Movie, options: Options) -> ctypes.Array[ctypes.c_uint8]:
    player = new_player()
    library.fmv_open(player, ctypes.byref(movie), ctypes.byref(options))
    return player


def started(library: Any, movie: Movie, options: Options) -> ctypes.Array[ctypes.c_uint8]:
    player = opened(library, movie, options)
    library.fmv_start(player)
    return player


def played(library: Any, movie: Movie, options: Options) -> ctypes.Array[ctypes.c_uint8]:
    player = started(library, movie, options)
    library.fmv_close(player)
    return player


def corrupt(
    movie: Movie, frame: int, *, runs: int | None = None, address: int | None = None
) -> None:
    stream = movie._keepalive[-1]
    offset = frame * len(keyframe_record())
    if runs is not None:
        struct.pack_into("=H", stream, offset, runs)
    if address is not None:
        struct.pack_into("=H", stream, offset + 2, address)
