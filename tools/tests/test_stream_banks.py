from __future__ import annotations

import pytest

from neogeomedia import stream
from tests.streamhelp import SINGLE_UPDATE_RECORD, filled_stream, row_of, update


class TestBankContainment:
    def test_records_never_straddle_a_bank_boundary(self):
        # Arrange
        movie = stream.MovieStream(bank_size=256)
        big = [update(c, r) for c in range(4) for r in range(14)]

        # Act
        for _ in range(12):
            movie.append(big)

        # Assert
        assert list(movie.frame_offsets()) == [256 * index for index in range(12)]

    def test_padding_advances_the_offset_to_the_next_bank(self):
        # Arrange
        movie = stream.MovieStream(bank_size=64)
        movie.append([update(0, 0)])

        # Act
        movie.append(row_of(7))

        # Assert
        assert list(movie.frame_offsets()) == [0, 64]

    def test_a_record_larger_than_a_bank_is_rejected(self):
        # Arrange
        movie = stream.MovieStream(bank_size=16)

        # Act
        with pytest.raises(ValueError, match="bank") as raised:
            movie.append(row_of(8))

        # Assert
        assert "66 bytes" in str(raised.value)

    def test_the_blob_is_padded_out_to_whole_banks(self):
        # Arrange
        movie = stream.MovieStream(bank_size=64)
        movie.append([update(0, 0)])

        # Act
        blob = movie.blob()

        # Assert
        assert blob == SINGLE_UPDATE_RECORD + bytes(64 - len(SINGLE_UPDATE_RECORD))

    def test_the_bank_count_covers_every_record(self):
        # Arrange
        movie = filled_stream(bank_size=64, records=6, columns=2)

        # Act
        banks = movie.bank_count()

        # Assert
        assert banks == 2

    def test_an_empty_stream_still_reports_one_bank(self):
        # Arrange
        movie = stream.MovieStream(bank_size=64)

        # Act
        banks = movie.bank_count()

        # Assert
        assert banks == 1

    def test_the_default_bank_size_is_the_switchable_window(self):
        # Arrange
        movie = stream.MovieStream()

        # Act
        blob = movie.blob()

        # Assert
        assert len(blob) == 1 << 20

    def test_records_fill_each_bank_window_before_the_next(self):
        # Arrange
        movie = stream.MovieStream(bank_size=128)

        # Act
        for _ in range(10):
            movie.append(row_of(3))

        # Assert
        assert list(movie.frame_offsets()) == [0, 26, 52, 78, 128, 154, 180, 206, 256, 282]


class TestPayloadSize:
    def test_payload_size_excludes_bank_padding(self):
        # Arrange
        movie = stream.MovieStream(bank_size=64)
        movie.append([update(0, 0)])

        # Act
        size = movie.payload_size()

        # Assert
        assert size == len(SINGLE_UPDATE_RECORD)

    def test_payload_size_counts_padding_inserted_between_records(self):
        # Arrange
        movie = stream.MovieStream(bank_size=64)
        movie.append([update(0, 0)])
        movie.append(row_of(7))

        # Act
        size = movie.payload_size()

        # Assert
        assert size == 64 + 2 + 7 * 8


class TestHardwareBankLimit:
    def test_the_limit_matches_the_three_bit_bank_register(self):
        # Arrange
        register_bits = 3

        # Act
        limit = stream.PROM_BANK_LIMIT

        # Assert
        assert limit == 1 << register_bits

    def test_a_stream_inside_the_limit_is_accepted(self):
        # Arrange
        movie = filled_stream(bank_size=64, records=8, columns=3)

        # Act
        banks = movie.bank_count()

        # Assert
        assert banks == 4

    def test_overrunning_the_bank_register_is_rejected(self):
        # Arrange
        movie = filled_stream(bank_size=64, records=120, columns=6)

        # Act
        with pytest.raises(ValueError, match="bank register") as raised:
            movie.bank_count()

        # Assert
        assert "120 banks" in str(raised.value)

    def test_the_error_names_the_remedy(self):
        # Arrange
        movie = filled_stream(bank_size=64, records=120, columns=6)

        # Act
        with pytest.raises(ValueError, match="bank register") as raised:
            movie.bank_count()

        # Assert
        assert "compress" in str(raised.value)
