from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "fmv" / "timeline.c"
SUFFIX = ".dylib" if sys.platform == "darwin" else ".so"
VBLANK_NUM = 59185
VBLANK_DEN = 1000


@pytest.fixture(scope="module")
def timeline(tmp_path_factory):
    if shutil.which("cc") is None:
        reason = "cc not on the path, and this test builds the player's timeline"
        if os.environ.get("NEOGEOMEDIA_CC_REQUIRED") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    built = tmp_path_factory.mktemp("timeline") / f"timeline{SUFFIX}"
    command = ["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC"]
    subprocess.run([*command, "-O1", "-o", str(built), str(SOURCE)], check=True)
    library = ctypes.CDLL(str(built))
    for name in ("timeline_frame_to_seconds", "timeline_frame_to_nearest_second"):
        function = getattr(library, name)
        function.argtypes = (ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32)
        function.restype = ctypes.c_uint32
    return library


class TestSeconds:
    def test_a_film_just_under_five_seconds_reads_five_in_total(self, timeline):
        # Arrange
        frames = 295

        # Act
        seconds = timeline.timeline_frame_to_nearest_second(frames, VBLANK_NUM, VBLANK_DEN)

        # Assert
        assert seconds == 5

    def test_the_same_film_floors_to_four_seconds_elapsed(self, timeline):
        # Arrange
        frames = 295

        # Act
        seconds = timeline.timeline_frame_to_seconds(frames, VBLANK_NUM, VBLANK_DEN)

        # Assert
        assert seconds == 4

    def test_a_rate_of_zero_reads_zero_seconds(self, timeline):
        # Arrange
        frames = 296

        # Act
        seconds = timeline.timeline_frame_to_nearest_second(frames, 0, VBLANK_DEN)

        # Assert
        assert seconds == 0

    def test_just_under_half_a_second_rounds_down(self, timeline):
        # Arrange
        frames = 29

        # Act
        seconds = timeline.timeline_frame_to_nearest_second(frames, VBLANK_NUM, VBLANK_DEN)

        # Assert
        assert seconds == 0
