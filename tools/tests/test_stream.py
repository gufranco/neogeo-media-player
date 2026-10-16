from __future__ import annotations

import numpy as np
import pytest
from fmvcore.testing import SEED

from neogeomedia import stream
from tests.streamhelp import EMPTY_RECORD, SINGLE_UPDATE_RECORD, read_runs, update


class TestVramAddress:
    def test_the_grid_starts_at_sprite_one(self):
        # Arrange
        col, row = 0, 0

        # Act
        address = stream.vram_address(col, row)

        # Assert
        assert address == 64

    def test_each_column_advances_one_sprite_block(self):
        # Arrange
        col, row = 1, 0

        # Act
        address = stream.vram_address(col, row)

        # Assert
        assert address == 128

    def test_each_row_advances_one_tile_entry(self):
        # Arrange
        col, row = 0, 1

        # Act
        address = stream.vram_address(col, row)

        # Assert
        assert address == 66

    def test_the_last_slot_stays_inside_its_sprite_block(self):
        # Arrange
        col, row = 19, 13

        # Act
        address = stream.vram_address(col, row)

        # Assert
        assert address == 20 * 64 + 26

    @pytest.mark.parametrize(("col", "row"), [(-1, 0), (20, 0), (0, -1), (0, 14)])
    def test_out_of_grid_slots_are_rejected(self, col, row):
        # Arrange
        slot = (col, row)

        # Act
        with pytest.raises(ValueError, match="grid") as raised:
            stream.vram_address(*slot)

        # Assert
        assert str(slot) in str(raised.value)


class TestAttributeWord:
    @pytest.mark.parametrize(
        ("fields", "expected"),
        [
            ({"palette": 0xA5, "tile": 0, "hflip": False, "vflip": False}, 0xA500),
            ({"palette": 0, "tile": 0xD_0000, "hflip": False, "vflip": False}, 0x00D0),
            ({"palette": 0, "tile": 0xFFFF, "hflip": False, "vflip": False}, 0x0000),
            ({"palette": 0, "tile": 0, "hflip": True, "vflip": False}, 0x0001),
            ({"palette": 0, "tile": 0, "hflip": False, "vflip": True}, 0x0002),
            ({"palette": 0x20, "tile": 0x9_1234, "hflip": True, "vflip": True}, 0x2093),
        ],
        ids=[
            "the palette occupies the high byte",
            "the high tile bits occupy bits seven to four",
            "the low tile bits do not reach the attribute word",
            "horizontal flip is bit zero",
            "vertical flip is bit one",
            "a full entry combines every field",
        ],
    )
    def test_each_field_lands_in_its_documented_bits(self, fields, expected):
        # Arrange
        arguments = dict(fields)

        # Act
        word = stream.attribute_word(**arguments)

        # Assert
        assert word == expected

    def test_auto_animation_bits_stay_clear(self):
        # Arrange
        arguments = {"palette": 0xFF, "tile": 0xF_FFFF, "hflip": True, "vflip": True}

        # Act
        word = stream.attribute_word(**arguments)

        # Assert
        assert word & 0x000C == 0
        assert word == 0xFFF3

    @pytest.mark.parametrize(
        ("fields", "named"),
        [
            ({"palette": 256, "tile": 0}, "palette"),
            ({"palette": 0, "tile": 1 << 20}, "tile"),
        ],
    )
    def test_a_field_outside_its_width_is_rejected(self, fields, named):
        # Arrange
        arguments = {**fields, "hflip": False, "vflip": False}

        # Act
        with pytest.raises(ValueError, match=named) as raised:
            stream.attribute_word(**arguments)

        # Assert
        assert str(fields[named]) in str(raised.value)


class TestPackFrame:
    def test_an_empty_frame_is_just_a_zero_run_count(self):
        # Arrange
        updates: list[stream.SlotUpdate] = []

        # Act
        blob = stream.pack_frame(updates)

        # Assert
        assert blob == EMPTY_RECORD

    def test_a_single_update_becomes_one_run_of_one_tile(self):
        # Arrange
        updates = [update(0, 0, tile=5, palette=17)]

        # Act
        blob = stream.pack_frame(updates)

        # Assert
        assert read_runs(blob) == [(64, [(5, 0x1100)])]

    def test_consecutive_rows_in_one_column_merge_into_one_run(self):
        # Arrange
        updates = [update(3, r, tile=r) for r in range(4)]

        # Act
        blob = stream.pack_frame(updates)

        # Assert
        assert read_runs(blob) == [(256, [(0, 0x1000), (1, 0x1000), (2, 0x1000), (3, 0x1000)])]

    def test_a_gap_between_rows_splits_the_run(self):
        # Arrange
        updates = [update(3, 0), update(3, 1), update(3, 5)]

        # Act
        blob = stream.pack_frame(updates)

        # Assert
        assert [(addr, len(entries)) for addr, entries in read_runs(blob)] == [(256, 2), (266, 1)]

    def test_different_columns_never_merge(self):
        # Arrange
        updates = [update(0, 13), update(1, 0)]

        # Act
        blob = stream.pack_frame(updates)

        # Assert
        assert [(addr, len(entries)) for addr, entries in read_runs(blob)] == [(90, 1), (128, 1)]

    def test_updates_are_sorted_before_packing(self):
        # Arrange
        rng = np.random.default_rng(SEED)
        ordered = [update(5, row, tile=row) for row in range(3)]
        updates = [ordered[int(index)] for index in rng.permutation(len(ordered))]

        # Act
        blob = stream.pack_frame(updates)

        # Assert
        assert read_runs(blob) == [(384, [(0, 0x1000), (1, 0x1000), (2, 0x1000)])]

    def test_duplicate_slots_in_one_frame_are_rejected(self):
        # Arrange
        updates = [update(1, 1, tile=1), update(1, 1, tile=2)]

        # Act
        with pytest.raises(ValueError, match="duplicate") as raised:
            stream.pack_frame(updates)

        # Assert
        assert "(1, 1)" in str(raised.value)

    def test_a_full_keyframe_packs_to_the_documented_size(self):
        # Arrange
        updates = [update(c, r) for c in range(20) for r in range(14)]

        # Act
        blob = stream.pack_frame(updates)

        # Assert
        assert len(blob) == 2 + 20 * (4 + 14 * 4)

    def test_a_full_keyframe_uses_one_run_per_column(self):
        # Arrange
        updates = [update(c, r) for c in range(20) for r in range(14)]

        # Act
        blob = stream.pack_frame(updates)

        # Assert
        assert [addr for addr, _ in read_runs(blob)] == [64 * (col + 1) for col in range(20)]

    @pytest.mark.parametrize(("count", "size"), [(0, 2), (1, 10), (4, 22), (7, 34)])
    def test_every_record_stays_word_aligned(self, count, size):
        # Arrange
        updates = [update(0, r) for r in range(count)]

        # Act
        blob = stream.pack_frame(updates)

        # Assert
        assert len(blob) == size
        assert len(blob) % 2 == 0


class TestMovieStream:
    def test_the_stream_concatenates_frame_records(self):
        # Arrange
        movie = stream.MovieStream()
        movie.append([update(0, 0)])
        movie.append([])

        # Act
        blob = movie.blob()

        # Assert
        assert blob[: len(SINGLE_UPDATE_RECORD) + 2] == SINGLE_UPDATE_RECORD + EMPTY_RECORD

    def test_offsets_point_at_the_start_of_each_record(self):
        # Arrange
        movie = stream.MovieStream()
        movie.append([update(0, 0)])
        movie.append([])

        # Act
        offsets = movie.frame_offsets()

        # Assert
        assert list(offsets) == [0, len(SINGLE_UPDATE_RECORD)]

    def test_keyframes_are_tracked_separately(self):
        # Arrange
        movie = stream.MovieStream()
        movie.append([update(0, 0)], keyframe=True)
        movie.append([])
        movie.append([update(1, 1)], keyframe=True)

        # Act
        keyframes = movie.keyframes()

        # Assert
        assert list(keyframes) == [0, 2]

    def test_the_index_blob_is_four_bytes_per_frame(self):
        # Arrange
        movie = stream.MovieStream()
        movie.append([])
        movie.append([])

        # Act
        index = movie.index_blob()

        # Assert
        assert len(index) == 8

    def test_the_index_blob_is_big_endian(self):
        # Arrange
        movie = stream.MovieStream()
        movie.append([update(0, 0)])
        movie.append([])

        # Act
        index = movie.index_blob()

        # Assert
        assert index == b"\x00\x00\x00\x00\x00\x00\x00\x0a"

    def test_an_empty_stream_has_no_frames(self):
        # Arrange
        movie = stream.MovieStream()

        # Act
        frames = len(movie)

        # Assert
        assert frames == 0

    def test_an_empty_stream_blob_is_all_zero(self):
        # Arrange
        movie = stream.MovieStream(bank_size=64)

        # Act
        blob = movie.blob()

        # Assert
        assert blob == bytes(64)
