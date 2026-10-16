from __future__ import annotations

import numpy as np
import pytest
from fmvcore.testing import SEED

from neogeomedia import crom
from tests.geolith_model import GeolithTileReader

TILE_BYTES = 128


def random_tiles(count: int, stream: int) -> np.ndarray:
    rng = np.random.default_rng((SEED, stream))
    return rng.integers(0, 16, size=(count, 16, 16), dtype=np.uint8)


def read_back(c1: np.ndarray | bytes, c2: np.ndarray | bytes, count: int, **flips: bool):
    reader = GeolithTileReader(c1, c2)
    return np.stack([reader.tile(index, **flips) for index in range(count)])


class TestPackTiles:
    def test_each_tile_occupies_sixty_four_bytes_per_rom(self):
        # Arrange
        tiles = random_tiles(7, stream=1)

        # Act
        c1, c2 = crom.pack_tiles(tiles)

        # Assert
        assert c1.shape == (7, 64)
        assert c2.shape == (7, 64)

    @pytest.mark.parametrize(
        ("flips", "rows", "columns"),
        [
            ({}, slice(None), slice(None)),
            ({"hflip": True}, slice(None), slice(None, None, -1)),
            ({"vflip": True}, slice(None, None, -1), slice(None)),
            ({"hflip": True, "vflip": True}, slice(None, None, -1), slice(None, None, -1)),
        ],
        ids=["plain", "horizontal", "vertical", "both"],
    )
    def test_packed_tiles_read_back_through_the_emulator_decoder(self, flips, rows, columns):
        # Arrange
        tiles = random_tiles(16, stream=2)

        # Act
        c1, c2 = crom.pack_tiles(tiles)

        # Assert
        assert np.array_equal(read_back(c1, c2, len(tiles), **flips), tiles[:, rows, columns])

    def test_a_uniform_tile_packs_to_a_constant_byte_pattern(self):
        # Arrange
        tiles = np.full((1, 16, 16), 0x0F, dtype=np.uint8)

        # Act
        c1, c2 = crom.pack_tiles(tiles)

        # Assert
        assert c1.tobytes() == b"\xff" * 64
        assert c2.tobytes() == b"\xff" * 64

    def test_a_zero_tile_packs_to_zero_bytes(self):
        # Arrange
        tiles = np.zeros((1, 16, 16), dtype=np.uint8)

        # Act
        c1, c2 = crom.pack_tiles(tiles)

        # Assert
        assert c1.tobytes() == bytes(64)
        assert c2.tobytes() == bytes(64)

    def test_a_single_lit_pixel_sets_exactly_one_bit(self):
        # Arrange
        tiles = np.zeros((1, 16, 16), dtype=np.uint8)
        tiles[0, 5, 3] = 0x08

        # Act
        c1, c2 = crom.pack_tiles(tiles)

        # Assert
        assert int(c1.sum()) == 0
        assert int(np.unpackbits(c2).sum()) == 1

    def test_pixel_values_above_the_nibble_range_are_rejected(self):
        # Arrange
        tiles = np.zeros((1, 16, 16), dtype=np.uint8)
        tiles[0, 0, 0] = 16

        # Act
        with pytest.raises(ValueError) as raised:
            crom.pack_tiles(tiles)

        # Assert
        assert str(raised.value) == "tile pixels must be 4-bit palette indices in the range 0 to 15"

    def test_wrongly_shaped_input_is_rejected(self):
        # Arrange
        tiles = np.zeros((1, 8, 8), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as raised:
            crom.pack_tiles(tiles)

        # Assert
        assert str(raised.value) == "tiles must be a batch of 16x16 arrays, got shape (1, 8, 8)"

    def test_an_empty_batch_packs_to_empty_roms(self):
        # Arrange
        tiles = np.zeros((0, 16, 16), dtype=np.uint8)

        # Act
        c1, c2 = crom.pack_tiles(tiles)

        # Assert
        assert c1.shape == (0, 64)
        assert c2.shape == (0, 64)


class TestRomImages:
    def test_rom_images_pad_to_the_requested_size(self):
        # Arrange
        tiles = random_tiles(3, stream=3)

        # Act
        c1, c2 = crom.build_rom_images(tiles, pad_to=4096)

        # Assert
        assert len(c1) == 4096
        assert len(c2) == 4096

    def test_rom_images_hold_the_packed_tiles_at_the_front(self):
        # Arrange
        tiles = random_tiles(3, stream=4)

        # Act
        c1, c2 = crom.build_rom_images(tiles, pad_to=4096)

        # Assert
        assert np.array_equal(read_back(c1[: 3 * 64], c2[: 3 * 64], 3), tiles)
        assert c1[3 * 64 :] == bytes(4096 - 3 * 64)

    def test_padding_smaller_than_the_payload_is_rejected(self):
        # Arrange
        tiles = random_tiles(64, stream=5)

        # Act
        with pytest.raises(ValueError) as raised:
            crom.build_rom_images(tiles, pad_to=128)

        # Assert
        assert str(raised.value) == "pad_to 128 is smaller than the 4096 byte payload"


class TestPowerOfTwoPadding:
    @pytest.mark.parametrize(
        ("tile_count", "expected"),
        [(0, 1 << 20), (1, 1 << 20), (16384, 1 << 20), (16385, 1 << 21), (100_000, 1 << 23)],
    )
    def test_rom_size_rounds_up_to_a_power_of_two(self, tile_count, expected):
        # Arrange
        count = tile_count

        # Act
        size = crom.rom_size_for(count)

        # Assert
        assert size == expected


class TestUnpacking:
    def test_unpacking_recovers_the_original_tiles(self):
        # Arrange
        tiles = random_tiles(32, stream=6)
        c1, c2 = crom.pack_tiles(tiles)

        # Act
        unpacked = crom.unpack_tiles(c1, c2)

        # Assert
        assert np.array_equal(unpacked, tiles)

    def test_unpacking_an_empty_batch_yields_no_tiles(self):
        # Arrange
        c1, c2 = crom.pack_tiles(np.zeros((0, 16, 16), dtype=np.uint8))

        # Act
        unpacked = crom.unpack_tiles(c1, c2)

        # Assert
        assert unpacked.shape == (0, 16, 16)
