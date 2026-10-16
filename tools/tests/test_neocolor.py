from __future__ import annotations

import numpy as np
import pytest
from fmvcore import colour

from neogeomedia import neocolor


def _six_bit_channels(word: int) -> tuple[int, int, int]:
    return (
        ((word >> 6) & 0x3C) | ((word >> 13) & 0x02) | ((word >> 15) & 0x01),
        ((word >> 2) & 0x3C) | ((word >> 12) & 0x02) | ((word >> 15) & 0x01),
        ((word << 2) & 0x3C) | ((word >> 11) & 0x02) | ((word >> 15) & 0x01),
    )


def geolith_reference_rgb(word: int) -> tuple[int, int, int]:
    r6, g6, b6 = _six_bit_channels(word)
    red, green, blue = (((level ^ 0x01) * 259 + 33) >> 6 for level in (r6, g6, b6))
    return red, green, blue


def geolith_resnet_levels() -> list[int]:
    resistance = [3900.0, 2200.0, 1000.0, 470.0, 220.0]
    v_raw = []
    for value in range(32):
        r_to_vcc = 0.0
        r_to_gnd = 0.0
        for bit in range(5):
            r = resistance[bit]
            if value & (1 << bit):
                r_to_vcc = r if r_to_vcc == 0.0 else (r_to_vcc * r) / (r_to_vcc + r)
            else:
                r_to_gnd = r if r_to_gnd == 0.0 else (r_to_gnd * r) / (r_to_gnd + r)
        if r_to_vcc == 0.0:
            v_raw.append(0.0)
        elif r_to_gnd == 0.0:
            v_raw.append(1.0)
        else:
            v_raw.append(r_to_gnd / (r_to_vcc + r_to_gnd))

    v_smooth = list(v_raw)
    for i in range(1, 31):
        v_smooth[i] = (v_raw[i - 1] * 1.6 + v_raw[i] + v_raw[i + 1] * 1.6) / 4.2

    lo, hi = v_smooth[0], v_smooth[31]
    return [int((v_smooth[i] - lo) / (hi - lo) * 255.0 + 0.5) for i in range(32)]


def geolith_resnet_rgb(word: int) -> tuple[int, int, int]:
    levels = geolith_resnet_levels()
    channels = _six_bit_channels(word)
    if any(level & 1 for level in channels):
        msg = "the resistor-network oracle only covers words with the dark bit clear"
        raise ValueError(msg)
    red, green, blue = (levels[level >> 1] for level in channels)
    return red, green, blue


class TestResistorNetworkLevels:
    def test_the_default_model_matches_the_emulator_resistor_network(self):
        # Arrange
        expected = geolith_resnet_levels()

        # Act
        levels = [int(v) for v in neocolor.C5_TO_SRGB8]

        # Assert
        assert levels == expected

    def test_the_resistor_network_spans_true_black_to_full_white(self):
        # Arrange
        levels = neocolor.C5_TO_SRGB8

        # Act
        ends = (int(levels[0]), int(levels[31]))

        # Assert
        assert ends == (0, 255)

    def test_the_raw_model_stays_available_for_comparison(self):
        # Arrange
        levels = neocolor.RAW_C5_TO_SRGB8

        # Act
        ends = (int(levels[0]), int(levels[31]))

        # Assert
        assert ends == (4, 255)

    def test_the_two_models_never_disagree_by_more_than_a_step(self):
        # Arrange
        resnet = neocolor.C5_TO_SRGB8.astype(int)

        # Act
        difference = np.abs(resnet - neocolor.RAW_C5_TO_SRGB8.astype(int))

        # Assert
        assert difference.max() <= 12


class TestPaletteWord:
    def test_every_channel_level_decodes_to_the_documented_raw_display_value(self):
        # Arrange
        levels = range(neocolor.C5_LEVELS)

        # Act
        words = [neocolor.pack_palette_word(c5, 0, 0) for c5 in levels]

        # Assert
        decoded = [geolith_reference_rgb(w)[0] for w in words]
        assert decoded == [int(v) for v in neocolor.RAW_C5_TO_SRGB8]

    def test_channels_are_independent_in_the_encoded_word(self):
        # Arrange
        raw = neocolor.RAW_C5_TO_SRGB8

        # Act
        word = neocolor.pack_palette_word(31, 0, 17)

        # Assert
        assert geolith_reference_rgb(word) == (int(raw[31]), int(raw[0]), int(raw[17]))

    @pytest.mark.parametrize(
        ("channels", "dark", "rgb"),
        [
            ((0, 0, 0), False, (4, 4, 4)),
            ((0, 0, 0), True, (0, 0, 0)),
            ((31, 31, 31), False, (255, 255, 255)),
        ],
        ids=["black-without-the-dark-bit", "black-with-the-dark-bit", "full-intensity"],
    )
    def test_the_extremes_decode_to_their_documented_colours(self, channels, dark, rgb):
        # Arrange
        r5, g5, b5 = channels

        # Act
        word = neocolor.pack_palette_word(r5, g5, b5, dark=dark)

        # Assert
        assert geolith_reference_rgb(word) == rgb

    def test_the_word_fits_sixteen_bits_for_every_grid_colour(self):
        # Arrange
        grid = range(0, neocolor.C5_LEVELS, 7)

        # Act
        words = [neocolor.pack_palette_word(r, g, b) for r in grid for g in grid for b in grid]

        # Assert
        assert min(words) >= 0
        assert max(words) <= 0xFFFF

    @pytest.mark.parametrize("channel", ["r5", "g5", "b5"])
    def test_out_of_range_channels_are_rejected(self, channel):
        # Arrange
        args = {"r5": 0, "g5": 0, "b5": 0, channel: neocolor.C5_LEVELS}

        # Act
        with pytest.raises(ValueError, match=channel) as refused:
            neocolor.pack_palette_word(**args)

        # Assert
        assert str(neocolor.C5_LEVELS) in str(refused.value)


class TestChannelQuantization:
    def test_display_levels_increase_strictly(self):
        # Arrange
        levels = neocolor.C5_TO_SRGB8.astype(int)

        # Act
        steps = np.diff(levels)

        # Assert
        assert steps.min() >= 1

    def test_quantizing_a_displayed_level_returns_its_own_index(self):
        # Arrange
        displayed = neocolor.C5_TO_SRGB8

        # Act
        recovered = neocolor.SRGB8_TO_C5[displayed]

        # Assert
        assert np.array_equal(recovered, np.arange(neocolor.C5_LEVELS, dtype=np.uint8))

    def test_quantization_never_exceeds_half_the_widest_step(self):
        # Arrange
        source = np.arange(256)

        # Act
        error = np.abs(neocolor.C5_TO_SRGB8[neocolor.SRGB8_TO_C5[source]].astype(int) - source)

        # Assert
        widest_step = int(np.diff(neocolor.C5_TO_SRGB8.astype(int)).max())
        assert error.max() <= (widest_step + 1) // 2


class TestColourIndex:
    def test_index_packing_round_trips_through_channel_split(self):
        # Arrange
        index = np.arange(neocolor.COLOR_INDEX_COUNT)

        # Act
        channels = neocolor.color_index_to_c5(index)

        # Assert
        repacked = (
            (channels[:, 0].astype(np.uint16) << 10)
            | (channels[:, 1].astype(np.uint16) << 5)
            | channels[:, 2].astype(np.uint16)
        )
        assert np.array_equal(repacked, index.astype(np.uint16))

    def test_a_packed_index_splits_into_its_documented_channels(self):
        # Arrange
        index = np.array([(31 << 10) | 17])

        # Act
        channels = neocolor.color_index_to_c5(index)

        # Assert
        assert channels.tolist() == [[31, 0, 17]]

    def test_displayed_grid_colours_quantize_back_to_themselves(self):
        # Arrange
        index = np.arange(neocolor.COLOR_INDEX_COUNT)

        # Act
        recovered = neocolor.rgb_to_color_index(neocolor.color_index_to_rgb(index))

        # Assert
        assert np.array_equal(recovered, index.astype(np.uint16))

    def test_vectorized_word_encoding_matches_the_scalar_encoder(self):
        # Arrange
        index = np.arange(0, neocolor.COLOR_INDEX_COUNT, 313)

        # Act
        words = neocolor.color_index_to_palette_word(index)

        # Assert
        channels = neocolor.color_index_to_c5(index)
        expected = [neocolor.pack_palette_word(int(r), int(g), int(b)) for r, g, b in channels]
        assert [int(w) for w in words] == expected

    def test_every_grid_word_decodes_to_its_own_displayed_colour(self):
        # Arrange
        index = np.arange(0, neocolor.COLOR_INDEX_COUNT, 97)

        # Act
        words = neocolor.color_index_to_palette_word(index)

        # Assert
        decoded = np.array([geolith_resnet_rgb(int(w)) for w in words], dtype=np.uint8)
        assert np.array_equal(decoded, neocolor.color_index_to_rgb(index))


class TestOklab:
    def test_pure_red_lands_on_its_published_oklab_coordinates(self):
        # Arrange
        red = np.array([[255, 0, 0]], dtype=np.uint8)

        # Act
        lab = colour.srgb_to_oklab(red / colour.BYTE_MAX)[0]

        # Assert
        assert lab.tolist() == pytest.approx([0.627955, 0.224863, 0.125846], abs=1e-5)

    def test_lightness_is_monotonic_along_the_grey_axis(self):
        # Arrange
        greys = np.stack([np.arange(256)] * 3, axis=-1).astype(np.uint8)

        # Act
        lightness = colour.srgb_to_oklab(greys / colour.BYTE_MAX)[:, 0]

        # Assert
        assert np.diff(lightness).min() > 0.0

    def test_grid_table_covers_every_colour_index(self):
        # Arrange
        expected = (neocolor.COLOR_INDEX_COUNT, 3)

        # Act
        grid = neocolor.build_oklab_grid()

        # Assert
        assert grid.shape == expected

    def test_grid_table_agrees_with_direct_conversion(self):
        # Arrange
        index = np.arange(0, neocolor.COLOR_INDEX_COUNT, 521)

        # Act
        grid = neocolor.build_oklab_grid()[index]

        # Assert
        direct = colour.srgb_to_oklab(neocolor.color_index_to_rgb(index) / colour.BYTE_MAX)
        assert np.allclose(grid, direct, atol=1e-6)
