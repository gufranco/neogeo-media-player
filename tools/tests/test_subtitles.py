from __future__ import annotations

import pytest
from fmvcore import subtitles as srt
from fmvcore.testing import seeded

from neogeomedia import fixtiles, subtitles

SAMPLE = """1
00:00:01,000 --> 00:00:03,500
Hello there

2
00:00:04,000 --> 00:00:06,000
A second line
and its continuation
"""
OVERLAPPING = (
    "1\n00:00:00,000 --> 00:00:05,000\nfirst\n\n2\n00:00:02,000 --> 00:00:06,000\nsecond\n"
)
EIGHT_WORDS = "word word word word word word word word"


def one_cue(text: str) -> str:
    return f"1\n00:00:00,000 --> 00:00:01,000\n{text}\n"


def first_text_row(blob: bytes) -> bytes:
    return blob[8 : 8 + subtitles.COLUMNS]


def word(field: int, blob: bytes, record: int = 0) -> int:
    offset = record * subtitles.RECORD_BYTES + field * 4
    return int.from_bytes(blob[offset : offset + 4], "big")


def film(tmp_path):
    source = tmp_path / f"{seeded().word()}.mkv"
    source.write_bytes(b"")
    return source


class TestLayout:
    @pytest.mark.parametrize("count", [20, 60])
    def test_a_long_line_is_wrapped_to_at_most_the_lines_that_fit(self, count):
        # Arrange
        text = ("word " * count).strip()

        # Act
        laid = subtitles.layout(text)

        # Assert
        assert laid == (EIGHT_WORDS, EIGHT_WORDS)
        assert all(len(line) <= subtitles.COLUMNS for line in laid)
        assert len(laid) <= subtitles.MAX_LINES

    def test_wrapping_never_splits_a_word(self):
        # Arrange
        text = "antidisestablishmentarian words here"

        # Act
        laid = subtitles.layout(text)

        # Assert
        assert laid == ("antidisestablishmentarian words here",)

    def test_a_word_longer_than_the_raster_is_cut_rather_than_lost(self):
        # Arrange
        text = "x" * 60

        # Act
        laid = subtitles.layout(text)

        # Assert
        assert laid == ("x" * 40, "x" * 20)


class TestEncoding:
    def test_each_cue_becomes_one_fixed_size_record(self):
        # Arrange
        cues = srt.parse(SAMPLE)

        # Act
        blob = subtitles.encode(cues, fps=60.0)

        # Assert
        assert len(blob) == 2 * (8 + 40 * 2)

    def test_frames_come_from_the_timings_and_the_rate(self):
        # Arrange
        cues = srt.parse(SAMPLE)

        # Act
        start, end = subtitles.frame_span(cues[0], fps=60.0)

        # Assert
        assert start == 60
        assert end == 210

    def test_text_is_stored_as_glyph_indices(self):
        # Arrange
        cues = srt.parse(one_cue("A"))

        # Act
        blob = subtitles.encode(cues, fps=60.0)

        # Assert
        assert fixtiles.GLYPHS["A"] in first_text_row(blob)

    def test_lowercase_keeps_its_own_shape_rather_than_folding_to_capitals(self):
        # Arrange
        cues = srt.parse(one_cue("ag"))

        # Act
        blob = subtitles.encode(cues, fps=60.0)

        # Assert
        row = first_text_row(blob)
        assert fixtiles.GLYPHS["a"] in row
        assert fixtiles.GLYPHS["g"] in row
        assert fixtiles.GLYPHS["A"] not in row

    def test_an_unknown_character_becomes_a_blank(self):
        # Arrange
        cues = srt.parse(one_cue("§"))

        # Act
        blob = subtitles.encode(cues, fps=60.0)

        # Assert
        assert set(first_text_row(blob)) == {fixtiles.GLYPHS["blank"]}

    def test_lines_are_centred(self):
        # Arrange
        cues = srt.parse(one_cue("AB"))

        # Act
        blob = subtitles.encode(cues, fps=60.0)

        # Assert
        row = first_text_row(blob)
        lit = [index for index, value in enumerate(row) if value != fixtiles.GLYPHS["blank"]]
        assert lit == [19, 20]

    def test_records_are_ordered_by_start_frame(self):
        # Arrange
        cues = srt.parse(SAMPLE)[::-1]

        # Act
        blob = subtitles.encode(cues, fps=60.0)

        # Assert
        assert [word(0, blob, record) for record in range(2)] == [60, 240]

    def test_overlapping_cues_are_trimmed_so_one_shows_at_a_time(self):
        # Arrange
        overlapping = srt.parse(OVERLAPPING)

        # Act
        blob = subtitles.encode(overlapping, fps=60.0)

        # Assert
        first_end = word(1, blob)
        second_start = word(0, blob, 1)
        assert first_end <= second_start
        assert (first_end, second_start) == (120, 120)
