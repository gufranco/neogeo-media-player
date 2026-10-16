from __future__ import annotations

from pathlib import Path

import pytest
from faker import Faker

from neogeomedia import blobs, fixtiles
from neogeomedia import subtitles as subtitles_mod

FAKE = Faker()
Faker.seed(20261016)


def _cue_file(path: Path, *cues: tuple[str, str, str]) -> Path:
    blocks = [
        f"{number}\n{start} --> {end}\n{text}\n"
        for number, (start, end, text) in enumerate(cues, start=1)
    ]
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def _word() -> str:
    return FAKE.word().upper()


class TestSubtitleSource:
    def test_an_explicit_subtitle_file_is_used(self, tmp_path):
        # Arrange
        captions = _cue_file(tmp_path / "captions.srt", ("00:00:00,000", "00:00:01,000", _word()))

        # Act
        blob = blobs.subtitle_blob(
            source=tmp_path / "movie.mkv", explicit=captions, start=0.0, duration=10.0
        )

        # Assert
        assert len(blob) == subtitles_mod.RECORD_BYTES

    def test_it_falls_back_to_the_sidecar_beside_the_source(self, tmp_path):
        # Arrange
        source = tmp_path / "movie.mkv"
        source.write_bytes(b"")
        _cue_file(tmp_path / "movie.srt", ("00:00:00,000", "00:00:01,000", _word()))

        # Act
        blob = blobs.subtitle_blob(source=source, explicit=None, start=0.0, duration=10.0)

        # Assert
        assert len(blob) == subtitles_mod.RECORD_BYTES

    def test_an_explicit_file_overrides_the_sidecar(self, tmp_path):
        # Arrange
        source = tmp_path / "movie.mkv"
        source.write_bytes(b"")
        _cue_file(tmp_path / "movie.srt", ("00:00:00,000", "00:00:01,000", _word()))
        chosen = _cue_file(
            tmp_path / "chosen.srt",
            ("00:00:00,000", "00:00:01,000", _word()),
            ("00:00:02,000", "00:00:03,000", _word()),
        )

        # Act
        blob = blobs.subtitle_blob(source=source, explicit=chosen, start=0.0, duration=10.0)

        # Assert
        assert len(blob) == 2 * subtitles_mod.RECORD_BYTES

    def test_no_subtitles_anywhere_is_an_empty_blob(self, tmp_path):
        # Arrange
        source = tmp_path / "movie.mkv"

        # Act
        blob = blobs.subtitle_blob(source=source, explicit=None, start=0.0, duration=10.0)

        # Assert
        assert blob == b""

    def test_a_named_subtitle_file_that_does_not_exist_is_an_error(self, tmp_path):
        # Arrange
        missing = tmp_path / "missing.srt"

        # Act
        with pytest.raises(FileNotFoundError) as raised:
            blobs.subtitle_blob(
                source=tmp_path / "movie.mkv", explicit=missing, start=0.0, duration=10.0
            )

        # Assert
        assert "missing.srt" in str(raised.value)


class TestSubtitleWindow:
    def test_cues_outside_the_baked_window_are_dropped(self, tmp_path):
        # Arrange
        captions = _cue_file(
            tmp_path / "captions.srt",
            ("00:00:01,000", "00:00:02,000", _word()),
            ("00:00:21,000", "00:00:22,000", _word()),
            ("00:00:41,000", "00:00:42,000", _word()),
        )

        # Act
        blob = blobs.subtitle_blob(
            source=tmp_path / "movie.mkv", explicit=captions, start=20.0, duration=10.0
        )

        # Assert
        assert len(blob) == subtitles_mod.RECORD_BYTES

    def test_a_cue_is_shifted_to_the_front_of_the_window(self, tmp_path):
        # Arrange
        text = _word()
        captions = _cue_file(tmp_path / "captions.srt", ("00:00:21,000", "00:00:22,000", text))
        shifted = subtitles_mod.Cue(start=1.0, end=2.0, lines=(text,))
        expected = subtitles_mod.encode([shifted], fps=blobs.FPS)

        # Act
        blob = blobs.subtitle_blob(
            source=tmp_path / "movie.mkv", explicit=captions, start=20.0, duration=10.0
        )

        # Assert
        assert blob == expected

    def test_a_cue_straddling_the_window_is_clipped_to_it(self, tmp_path):
        # Arrange
        text = _word()
        captions = _cue_file(tmp_path / "captions.srt", ("00:00:19,000", "00:00:31,000", text))
        clipped = subtitles_mod.Cue(start=0.0, end=10.0, lines=(text,))
        expected = subtitles_mod.encode([clipped], fps=blobs.FPS)

        # Act
        blob = blobs.subtitle_blob(
            source=tmp_path / "movie.mkv", explicit=captions, start=20.0, duration=10.0
        )

        # Assert
        assert blob == expected


class TestFixPalette:
    def test_every_colour_word_is_stored_big_endian(self):
        # Arrange
        words = fixtiles.palette_words()

        # Act
        blob = blobs.fix_palette_blob()

        # Assert
        assert [int.from_bytes(blob[i : i + 2], "big") for i in range(0, len(blob), 2)] == words


class TestWordAlignment:
    def test_an_odd_blob_is_padded_with_one_zero_byte(self, tmp_path):
        # Arrange
        payload = {"odd": (tmp_path / "odd.bin", b"\x01\x02\x03")}

        # Act
        written = blobs.write_payload(payload)

        # Assert
        assert written == {"odd": tmp_path / "odd.bin"}
        assert (tmp_path / "odd.bin").read_bytes() == b"\x01\x02\x03\x00"

    def test_an_even_blob_is_written_as_it_is(self, tmp_path):
        # Arrange
        payload = {"even": (tmp_path / "even.bin", b"\x01\x02")}

        # Act
        blobs.write_payload(payload)

        # Assert
        assert (tmp_path / "even.bin").read_bytes() == b"\x01\x02"
