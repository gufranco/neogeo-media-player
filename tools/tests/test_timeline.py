from __future__ import annotations

import ctypes
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "src" / "fmv" / "timeline.c"
FPS_NUM = 24
FPS_DEN = 1
SUBTITLE_STRIDE = 8 + 40 * 2
BAR_SPAN = 26
FILM_FRAMES = 1_000
KEYFRAMES = [0, 90, 180, 270]


@pytest.fixture(scope="session")
def timeline(tmp_path_factory):
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("no host C compiler")
    library = tmp_path_factory.mktemp("timeline") / "libtimeline.so"
    flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC"]
    subprocess.run([compiler, *flags, str(SOURCE), "-o", str(library)], check=True)
    loaded = ctypes.CDLL(str(library))
    loaded.timeline_clamp_frame.restype = ctypes.c_uint32
    loaded.timeline_keyframe_at_or_before.restype = ctypes.c_uint32
    loaded.timeline_subtitle_at.restype = ctypes.c_uint16
    loaded.timeline_seconds_to_frames.restype = ctypes.c_uint32
    loaded.timeline_frame_to_seconds.restype = ctypes.c_uint32
    loaded.timeline_audio_page.restype = ctypes.c_uint16
    loaded.timeline_bar_fill.restype = ctypes.c_uint16
    return loaded


def keyframe_table(frames):
    array = (ctypes.c_uint32 * len(frames))(*frames)
    return array, len(frames)


def cue_table(cues):
    blob = bytearray()
    for start, end in cues:
        blob += struct.pack(">II", start, end)
        blob += bytes(SUBTITLE_STRIDE - 8)
    return (ctypes.c_ubyte * len(blob)).from_buffer(blob), len(cues)


class TestSeekingLandsOnAKeyframe:
    @pytest.mark.parametrize(
        ("table", "frame", "landing"),
        [
            (KEYFRAMES, 200, 180),
            (KEYFRAMES, 180, 180),
            ([10, 90, 180], 0, 10),
            ([0, 90, 180], 10_000, 180),
        ],
        ids=["between-keyframes", "on-a-keyframe", "before-the-first", "past-the-last"],
    )
    def test_a_seek_lands_on_the_keyframe_at_or_before_it(self, timeline, table, frame, landing):
        # Arrange
        keyframes, count = keyframe_table(table)

        # Act
        found = timeline.timeline_keyframe_at_or_before(keyframes, count, frame)

        # Assert
        assert found == landing

    def test_every_frame_in_a_span_lands_on_the_same_keyframe(self, timeline):
        # Arrange
        keyframes, count = keyframe_table(KEYFRAMES)

        # Act
        landings = {
            timeline.timeline_keyframe_at_or_before(keyframes, count, f) for f in range(90, 180)
        }

        # Assert
        assert landings == {90}

    def test_an_empty_table_does_not_read_off_the_end(self, timeline):
        # Arrange
        keyframes, _ = keyframe_table([0])

        # Act
        found = timeline.timeline_keyframe_at_or_before(keyframes, 0, 500)

        # Assert
        assert found == 0


class TestClampingASeek:
    @pytest.mark.parametrize(
        ("target", "count", "landing"),
        [(5_000, 1_000, 999), (400, 1_000, 400), (999, 1_000, 999), (0, 0, 0)],
        ids=["past-the-end", "inside-the-film", "the-last-frame", "an-empty-film"],
    )
    def test_a_seek_is_clamped_to_the_film(self, timeline, target, count, landing):
        # Arrange
        film = (target, count)

        # Act
        clamped = timeline.timeline_clamp_frame(*film)

        # Assert
        assert clamped == landing


class TestWhichCueIsShowing:
    @pytest.mark.parametrize(
        ("cues", "frame", "showing"),
        [
            ([(0, 50), (100, 150), (200, 250)], 120, 1),
            ([(0, 50), (100, 150)], 75, 2),
            ([(100, 150)], 100, 0),
            ([(100, 150)], 150, 1),
            ([(100, 150)], 10, 1),
            ([(100, 150)], 9_999, 1),
        ],
        ids=[
            "inside-a-cue",
            "in-the-gap",
            "on-the-first-frame",
            "on-the-end-frame",
            "before-every-cue",
            "after-every-cue",
        ],
    )
    def test_it_finds_the_cue_on_screen_or_reports_none(self, timeline, cues, frame, showing):
        # Arrange
        table, count = cue_table(cues)

        # Act
        found = timeline.timeline_subtitle_at(table, count, SUBTITLE_STRIDE, frame)

        # Assert
        assert found == showing

    def test_back_to_back_cues_never_leave_a_hole(self, timeline):
        # Arrange
        table, count = cue_table([(0, 100), (100, 200)])

        # Act
        showing = [
            timeline.timeline_subtitle_at(table, count, SUBTITLE_STRIDE, f) for f in range(200)
        ]

        # Assert
        assert showing == [0] * 100 + [1] * 100

    def test_a_film_with_no_cues_finds_nothing(self, timeline):
        # Arrange
        table, _ = cue_table([(0, 100)])

        # Act
        found = timeline.timeline_subtitle_at(table, 0, SUBTITLE_STRIDE, 50)

        # Assert
        assert found == 0


class TestTheClock:
    @pytest.mark.parametrize(
        ("frames", "seconds"),
        [(24, 1), (2_232, 93), (240_000, 10_000)],
        ids=["a-second", "a-minute-and-a-half", "a-long-film"],
    )
    def test_frames_read_as_whole_seconds(self, timeline, frames, seconds):
        # Arrange
        rate = (FPS_NUM, FPS_DEN)

        # Act
        shown = timeline.timeline_frame_to_seconds(frames, *rate)

        # Assert
        assert shown == seconds

    @pytest.mark.parametrize(
        ("seconds", "frames"),
        [(93, 2_232), (10_000, 240_000)],
        ids=["a-minute-and-a-half", "a-long-film-without-overflow"],
    )
    def test_seconds_convert_to_frames(self, timeline, seconds, frames):
        # Arrange
        rate = (FPS_NUM, FPS_DEN)

        # Act
        converted = timeline.timeline_seconds_to_frames(seconds, *rate)

        # Assert
        assert converted == frames


class TestTheBar:
    @pytest.mark.parametrize(
        ("frame", "total", "fill"),
        [
            (0, FILM_FRAMES, 0),
            (999, FILM_FRAMES, BAR_SPAN),
            (5_000, FILM_FRAMES, BAR_SPAN),
            (0, 1, 0),
        ],
        ids=["starts-empty", "ends-full", "never-runs-past-its-end", "single-frame-film"],
    )
    def test_the_bar_fills_in_proportion_to_the_film(self, timeline, frame, total, fill):
        # Arrange
        position = (frame, total, BAR_SPAN)

        # Act
        filled = timeline.timeline_bar_fill(*position)

        # Assert
        assert filled == fill

    def test_the_bar_only_ever_moves_forward(self, timeline):
        # Arrange
        frames = range(FILM_FRAMES)

        # Act
        seen = [timeline.timeline_bar_fill(f, FILM_FRAMES, BAR_SPAN) for f in frames]

        # Assert
        assert seen == sorted(seen)
        assert (seen[0], seen[-1]) == (0, BAR_SPAN)


class TestWhichAudioPage:
    @pytest.mark.parametrize(
        ("frame", "num", "den", "page"),
        [
            (0, 1, 100, 0),
            (1_000, 3, 100, 30),
            (2_000, 3, 100, 60),
            (1, 1, 2, 1),
            (1_000_000, 4_000, 1_000_000, 4_000),
            (5_000, 0, 100, 0),
        ],
        ids=[
            "first-frame-first-page",
            "pages-advance-early",
            "pages-advance-late",
            "rounds-to-nearest",
            "past-32-bits",
            "a-silent-film",
        ],
    )
    def test_the_audio_page_scales_with_the_film(self, timeline, frame, num, den, page):
        # Arrange
        scale = (num, den)

        # Act
        found = timeline.timeline_audio_page(frame, *scale)

        # Assert
        assert found == page
