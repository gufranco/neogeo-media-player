from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "fmv" / "guard.c"
SUFFIX = ".dylib" if sys.platform == "darwin" else ".so"
SPRITE_WORDS = 64
SPRITE_COUNT = 381


class Limits(ctypes.Structure):
    _fields_ = (
        ("first", ctypes.c_uint16),
        ("end", ctypes.c_uint32),
        ("max_tiles", ctypes.c_uint16),
    )


class Layout(ctypes.Structure):
    _fields_ = (
        ("first_sprite", ctypes.c_uint16),
        ("grid_cols", ctypes.c_uint16),
        ("grid_rows", ctypes.c_uint16),
        ("palette_base", ctypes.c_uint16),
        ("epoch_palettes", ctypes.c_uint16),
        ("epoch_count", ctypes.c_uint16),
        ("caller_first_sprite", ctypes.c_uint16),
    )


@pytest.fixture(scope="module")
def guard(tmp_path_factory):
    if shutil.which("cc") is None:
        reason = "cc not on the path, and this test builds the player's guard"
        if os.environ.get("NEOGEOMEDIA_CC_REQUIRED") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    built = tmp_path_factory.mktemp("guard") / f"guard{SUFFIX}"
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            "-O1",
            "-o",
            str(built),
            str(SOURCE),
        ],
        check=True,
    )
    library = ctypes.CDLL(str(built))
    library.fmv_run_fits.argtypes = (
        ctypes.POINTER(Limits),
        ctypes.c_uint16,
        ctypes.c_uint16,
        ctypes.c_uint16,
    )
    library.fmv_run_fits.restype = ctypes.c_int
    library.fmv_layout_fits.argtypes = (ctypes.POINTER(Layout),)
    library.fmv_layout_fits.restype = ctypes.c_int
    return library


def grid(first_sprite: int = 1, cols: int = 20, max_tiles: int = 280) -> Limits:
    return Limits(first_sprite * SPRITE_WORDS, (first_sprite + cols) * SPRITE_WORDS, max_tiles)


def layout(**changes: int) -> Layout:
    values = {
        "first_sprite": 1,
        "grid_cols": 20,
        "grid_rows": 14,
        "palette_base": 16,
        "epoch_palettes": 120,
        "epoch_count": 3,
        "caller_first_sprite": 1,
    }
    return Layout(**{**values, **changes})


class TestRuns:
    def test_a_run_inside_the_grid_fits(self, guard):
        # Arrange
        limits = grid()

        # Act
        fits = guard.fmv_run_fits(ctypes.byref(limits), SPRITE_WORDS, 14, 0)

        # Assert
        assert fits == 1

    def test_a_run_ending_exactly_at_the_grid_edge_fits(self, guard):
        # Arrange
        limits = grid()
        start = 21 * SPRITE_WORDS - 4

        # Act
        fits = guard.fmv_run_fits(ctypes.byref(limits), start, 2, 0)

        # Assert
        assert fits == 1

    def test_a_run_past_the_grid_edge_is_refused(self, guard):
        # Arrange
        limits = grid()
        start = 21 * SPRITE_WORDS - 4

        # Act
        fits = guard.fmv_run_fits(ctypes.byref(limits), start, 3, 0)

        # Assert
        assert fits == 0

    def test_a_run_below_the_grid_is_refused(self, guard):
        # Arrange
        limits = grid()

        # Act
        fits = guard.fmv_run_fits(ctypes.byref(limits), SPRITE_WORDS - 2, 1, 0)

        # Assert
        assert fits == 0

    def test_a_run_over_the_frame_budget_is_refused(self, guard):
        # Arrange
        limits = grid(max_tiles=280)

        # Act
        fits = guard.fmv_run_fits(ctypes.byref(limits), SPRITE_WORDS, 10, 275)

        # Assert
        assert fits == 0

    def test_an_address_that_would_wrap_sixteen_bits_is_refused(self, guard):
        # Arrange
        limits = Limits(0, 0x10000, 0xFFFF)

        # Act
        fits = guard.fmv_run_fits(ctypes.byref(limits), 0xFFFE, 0x8000, 0)

        # Assert
        assert fits == 0


class TestLayout:
    def test_the_reference_layout_fits(self, guard):
        # Arrange
        movie = layout()

        # Act
        fits = guard.fmv_layout_fits(ctypes.byref(movie))

        # Assert
        assert fits == 1

    @pytest.mark.parametrize(
        "changes",
        [
            {"caller_first_sprite": SPRITE_COUNT - 19},
            {"first_sprite": SPRITE_COUNT - 19},
            {"grid_rows": 33},
            {"grid_cols": 0},
            {"epoch_count": 0},
            {"epoch_palettes": 121},
            {"palette_base": 17},
        ],
    )
    def test_a_layout_the_hardware_cannot_hold_is_refused(self, guard, changes):
        # Arrange
        movie = layout(**changes)

        # Act
        fits = guard.fmv_layout_fits(ctypes.byref(movie))

        # Assert
        assert fits == 0
