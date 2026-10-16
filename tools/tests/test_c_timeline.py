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
SEEK_NONE = 0xFFFFFFFF
BACK = 0
AHEAD = 1
GRACE = 120
EVERY = 600
FILM = 3_000
EVERY_FRAME = list(range(FILM))


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
    library.timeline_seek_target.argtypes = (
        ctypes.POINTER(SeekGrid),
        ctypes.c_uint32,
        ctypes.c_int,
    )
    library.timeline_seek_target.restype = ctypes.c_uint32
    return library


class SeekGrid(ctypes.Structure):
    _fields_ = (
        ("keyframes", ctypes.POINTER(ctypes.c_uint32)),
        ("keyframe_count", ctypes.c_uint32),
        ("every", ctypes.c_uint32),
        ("frames", ctypes.c_uint32),
    )


def seek_from(timeline, *, keyframes, every, frames, position, direction):
    table = (ctypes.c_uint32 * len(keyframes))(*keyframes)
    grid = SeekGrid(table, len(keyframes), every, frames)
    return timeline.timeline_seek_target(ctypes.byref(grid), position, direction)


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


class TestSeekPoints:
    def test_ahead_from_the_start_lands_on_the_first_point(self, timeline):
        # Arrange
        position = 1

        # Act
        target = seek_from(
            timeline,
            keyframes=EVERY_FRAME,
            every=EVERY,
            frames=FILM,
            position=position,
            direction=AHEAD,
        )

        # Assert
        assert target == EVERY

    @pytest.mark.parametrize(
        ("shown", "target"),
        [(0, EVERY), (GRACE - 1, EVERY), (GRACE, 2 * EVERY)],
        ids=["just-landed", "last-frame-of-the-grace", "past-the-grace"],
    )
    def test_back_inside_the_grace_goes_to_the_point_before(self, timeline, shown, target):
        # Arrange
        position = 2 * EVERY + shown + 1

        # Act
        found = seek_from(
            timeline,
            keyframes=EVERY_FRAME,
            every=EVERY,
            frames=FILM,
            position=position,
            direction=BACK,
        )

        # Assert
        assert found == target

    def test_back_inside_the_first_point_stays_at_the_start(self, timeline):
        # Arrange
        position = GRACE // 2

        # Act
        found = seek_from(
            timeline,
            keyframes=EVERY_FRAME,
            every=EVERY,
            frames=FILM,
            position=position,
            direction=BACK,
        )

        # Assert
        assert found == 0

    def test_ahead_from_the_last_point_has_nowhere_to_go(self, timeline):
        # Arrange
        position = FILM - 1

        # Act
        found = seek_from(
            timeline,
            keyframes=EVERY_FRAME,
            every=EVERY,
            frames=FILM,
            position=position,
            direction=AHEAD,
        )

        # Assert
        assert found == SEEK_NONE

    @pytest.mark.parametrize(
        ("direction", "target"), [(AHEAD, SEEK_NONE), (BACK, 0)], ids=["ahead", "back"]
    )
    def test_no_spacing_leaves_only_the_start(self, timeline, direction, target):
        # Arrange
        position = FILM // 2

        # Act
        found = seek_from(
            timeline,
            keyframes=EVERY_FRAME,
            every=0,
            frames=FILM,
            position=position,
            direction=direction,
        )

        # Assert
        assert found == target

    def test_a_point_landing_on_an_earlier_keyframe_never_traps_ahead(self, timeline):
        # Arrange
        keyframes = list(range(0, FILM, 90))
        landed = 540 + 1

        # Act
        found = seek_from(
            timeline,
            keyframes=keyframes,
            every=EVERY,
            frames=FILM,
            position=landed,
            direction=AHEAD,
        )

        # Assert
        assert found == 2 * EVERY
