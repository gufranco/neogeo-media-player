from __future__ import annotations

import numpy as np
import pytest

from neogeomedia import palettes

THREE_ENTRIES = [0, 0x1000, 0x7FFF]


def a_ramp_tile(low: int, high: int) -> np.ndarray:
    row = np.linspace(low, high, palettes.TILE_PX, dtype=np.float64)
    return np.tile(row, (palettes.TILE_PX, 1)).astype(np.uint16)


def a_palette_set(colors: list[int]) -> palettes.PaletteSet:
    entries = np.zeros((1, palettes.PALETTE_SLOTS), dtype=np.uint16)
    entries[0, : len(colors)] = colors
    entries[0, len(colors) :] = colors[-1]
    return palettes.PaletteSet(colors=entries, base_bank=16)


def dithering() -> palettes.PaletteAssigner:
    return palettes.PaletteAssigner(a_palette_set(THREE_ENTRIES), dither=True)


class TestTheThresholdField:
    def test_it_covers_a_whole_tile(self):
        # Arrange
        expected = (16, 16)

        # Act
        field = palettes.bayer_thresholds()

        # Assert
        assert field.shape == expected

    def test_it_stays_inside_the_unit_interval(self):
        # Arrange
        low, high = 0.0, 1.0

        # Act
        field = palettes.bayer_thresholds()

        # Assert
        assert field.min() > low
        assert field.max() < high

    def test_it_repeats_on_a_period_that_divides_a_tile(self):
        # Arrange
        period = 8

        # Act
        field = palettes.bayer_thresholds()

        # Assert
        assert np.array_equal(field[:period, :period], field[period:, period:])
        assert np.array_equal(field[:period, :period], field[period:, :period])

    def test_every_level_appears_equally_often(self):
        # Arrange
        repeats_per_tile = 4

        # Act
        field = palettes.bayer_thresholds()

        # Assert
        _, counts = np.unique(field, return_counts=True)
        assert set(counts.tolist()) == {repeats_per_tile}


class TestItKeepsTilesInternable:
    def test_two_identical_tiles_still_quantise_identically(self):
        # Arrange
        tiles = np.stack([a_ramp_tile(0, 0x7FFF)] * 2)
        assigner = dithering()

        # Act
        out = assigner.assign(tiles)

        # Assert
        assert np.array_equal(out.nibbles[0], out.nibbles[1])

    def test_a_tile_quantises_the_same_wherever_it_sits_in_the_frame(self):
        # Arrange
        one = a_ramp_tile(0, 0x7FFF)
        other = a_ramp_tile(0x2000, 0x5000)
        assigner = dithering()
        elsewhere = assigner.assign(np.stack([other, one]))

        # Act
        first = assigner.assign(np.stack([one, other, one]))

        # Assert
        assert np.array_equal(first.nibbles[0], first.nibbles[2])
        assert np.array_equal(first.nibbles[0], elsewhere.nibbles[1])


class TestItActuallyDithers:
    def test_a_gradient_gains_intermediate_levels(self):
        # Arrange
        tiles = a_ramp_tile(0, 0x7FFF)[None, :, :]
        plain = palettes.PaletteAssigner(a_palette_set(THREE_ENTRIES)).assign(tiles)

        # Act
        mixed = dithering().assign(tiles)

        # Assert
        assert len(np.unique(mixed.nibbles)) >= len(np.unique(plain.nibbles))

    def test_a_colour_sitting_on_a_palette_entry_is_never_swapped(self):
        # Arrange
        flat = np.full((1, palettes.TILE_PX, palettes.TILE_PX), 0x1000, dtype=np.uint16)
        assigner = dithering()

        # Act
        out = assigner.assign(flat)

        # Assert
        assert len(np.unique(out.nibbles)) == 1

    def test_leaving_it_off_changes_nothing(self):
        # Arrange
        tiles = a_ramp_tile(0, 0x7FFF)[None, :, :]
        palette = a_palette_set(THREE_ENTRIES)
        before = palettes.PaletteAssigner(palette).assign(tiles)

        # Act
        after = palettes.PaletteAssigner(palette, dither=False).assign(tiles)

        # Assert
        assert np.array_equal(before.nibbles, after.nibbles)


def swapped_pixels(strength: float) -> int:
    tiles = a_ramp_tile(0, 0x7FFF)[None, :, :]
    palette = a_palette_set(THREE_ENTRIES)
    plain = palettes.PaletteAssigner(palette).assign(tiles)
    mixed = palettes.PaletteAssigner(palette, dither=strength).assign(tiles)
    return int(np.count_nonzero(plain.nibbles != mixed.nibbles))


class TestTies:
    def test_a_tie_takes_the_first_entry_as_the_undithered_choice_does(self):
        # Arrange
        rng = np.random.default_rng(7)
        base = rng.random((4096, 8), dtype=np.float32)
        distance = np.concatenate([base, base], axis=1)[:, rng.permutation(16)]

        # Act
        nearest, _, _ = palettes._two_nearest(distance, palettes.MAX_DITHER)

        # Assert
        assert np.array_equal(nearest, np.argmin(distance, axis=1))

    def test_the_runner_up_is_never_the_nearest(self):
        # Arrange
        distance = np.array([[1.0, 1.0, 5.0], [3.0, 1.0, 1.0]], dtype=np.float32)

        # Act
        nearest, runner, _ = palettes._two_nearest(distance, palettes.MAX_DITHER)

        # Assert
        assert (nearest.tolist(), runner.tolist()) == ([0, 1], [1, 2])


class TestStrength:
    def test_a_weaker_dither_swaps_fewer_pixels_than_a_full_one(self):
        # Arrange
        half, full = 0.5, palettes.MAX_DITHER

        # Act
        swapped = (swapped_pixels(half), swapped_pixels(full))

        # Assert
        assert 0 < swapped[0] < swapped[1]

    def test_strength_zero_is_no_dither(self):
        # Arrange
        strength = palettes.NO_DITHER

        # Act
        swapped = swapped_pixels(strength)

        # Assert
        assert swapped == 0

    @pytest.mark.parametrize("strength", [-0.1, 1.1], ids=["negative", "past-the-maximum"])
    def test_a_strength_outside_the_range_is_refused(self, strength):
        # Arrange
        palette = a_palette_set(THREE_ENTRIES)

        # Act
        with pytest.raises(ValueError, match="dither strength") as raised:
            palettes.PaletteAssigner(palette, dither=strength)

        # Assert
        assert f"{strength:g}" in str(raised.value)
