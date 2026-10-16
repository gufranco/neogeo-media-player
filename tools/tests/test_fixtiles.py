from __future__ import annotations

import pytest
from fmvcore import font

from neogeomedia import fixtiles


def geolith_fix_pixel(tile: bytes, x: int, y: int) -> int:
    offsets = (0x10, 0x18, 0x00, 0x08)
    byte = tile[offsets[x >> 1] + y]
    return (byte & 0x0F) if (x & 1) == 0 else ((byte >> 4) & 0x0F)


def decode(tile: bytes) -> list[list[int]]:
    return [[geolith_fix_pixel(tile, x, y) for x in range(8)] for y in range(8)]


def glyph(name: str) -> list[list[int]]:
    index = fixtiles.GLYPHS[name]
    rom = fixtiles.build_rom()
    return decode(rom[index * fixtiles.TILE_BYTES : (index + 1) * fixtiles.TILE_BYTES])


def blank_pattern() -> list[list[int]]:
    return [[0] * 8 for _ in range(8)]


def tile_bytes(rom: bytes, name: str) -> bytes:
    index = fixtiles.GLYPHS[name]
    return bytes(rom[index * fixtiles.TILE_BYTES : (index + 1) * fixtiles.TILE_BYTES])


class TestPacking:
    def test_a_tile_is_thirty_two_bytes(self):
        # Arrange
        pattern = blank_pattern()

        # Act
        packed = fixtiles.pack_tile(pattern)

        # Assert
        assert len(packed) == 32

    def test_a_drawn_tile_reads_back_through_the_emulator_decode(self):
        # Arrange
        pattern = [[(x + y) % 16 for x in range(8)] for y in range(8)]

        # Act
        packed = fixtiles.pack_tile(pattern)

        # Assert
        assert decode(packed) == pattern

    def test_the_left_pixel_of_a_pair_is_the_low_nibble(self):
        # Arrange
        pattern = blank_pattern()
        pattern[0][0] = 0x0F

        # Act
        packed = fixtiles.pack_tile(pattern)

        # Assert
        assert packed[0x10] == 0x0F

    def test_the_right_pixel_of_a_pair_is_the_high_nibble(self):
        # Arrange
        pattern = blank_pattern()
        pattern[0][1] = 0x0F

        # Act
        packed = fixtiles.pack_tile(pattern)

        # Assert
        assert packed[0x10] == 0xF0

    def test_a_pixel_above_the_nibble_range_is_rejected(self):
        # Arrange
        pattern = blank_pattern()
        pattern[0][0] = 16

        # Act
        with pytest.raises(ValueError) as raised:
            fixtiles.pack_tile(pattern)

        # Assert
        assert "4-bit" in str(raised.value)

    def test_a_wrongly_shaped_tile_is_rejected(self):
        # Arrange
        pattern = [[0] * 4 for _ in range(8)]

        # Act
        with pytest.raises(ValueError) as raised:
            fixtiles.pack_tile(pattern)

        # Assert
        assert "8x8" in str(raised.value)


class TestGlyphSet:
    def test_the_blank_tile_is_index_zero(self):
        # Arrange
        name = "blank"

        # Act
        index = fixtiles.GLYPHS[name]

        # Assert
        assert index == 0

    def test_digits_occupy_ten_consecutive_indices(self):
        # Arrange
        digits = [str(d) for d in range(10)]

        # Act
        indices = [fixtiles.GLYPHS[digit] for digit in digits]

        # Assert
        assert indices == list(range(indices[0], indices[0] + 10))

    def test_every_transport_and_scrubber_glyph_is_present(self):
        # Arrange
        names = ("play", "pause", "forward", "rewind", "bar_empty", "bar_filled", "panel")

        # Act
        missing = [name for name in names if name not in fixtiles.GLYPHS]

        # Assert
        assert missing == []

    def test_the_bar_pieces_all_exist(self):
        # Arrange
        names = ("bar_empty", "bar_filled", "bar_cap_left", "bar_cap_right", "bar_knob")

        # Act
        missing = [name for name in names if name not in fixtiles.GLYPHS]

        # Assert
        assert missing == []

    def test_glyph_indices_are_unique(self):
        # Arrange
        glyphs = fixtiles.GLYPHS

        # Act
        indices = list(glyphs.values())

        # Assert
        assert len(indices) == len(set(indices))

    def test_glyph_indices_fit_the_twelve_bit_map_field(self):
        # Arrange
        limit = fixtiles.MAX_TILE_INDEX

        # Act
        highest = max(fixtiles.GLYPHS.values())

        # Assert
        assert highest < limit == 0x1000


class TestRom:
    def test_the_rom_holds_every_glyph(self):
        # Arrange
        needed = (max(fixtiles.GLYPHS.values()) + 1) * 32

        # Act
        rom = fixtiles.build_rom()

        # Assert
        assert len(rom) >= needed

    def test_the_rom_pads_to_the_requested_size(self):
        # Arrange
        size = 131072

        # Act
        rom = fixtiles.build_rom(pad_to=size)

        # Assert
        assert len(rom) == size

    def test_the_blank_tile_is_fully_transparent(self):
        # Arrange
        transparent = bytes(32)

        # Act
        rom = fixtiles.build_rom()

        # Assert
        assert tile_bytes(rom, "blank") == transparent

    def test_the_panel_tile_is_fully_opaque(self):
        # Arrange
        name = "panel"

        # Act
        rom = fixtiles.build_rom()

        # Assert
        assert all(value != 0 for row in decode(tile_bytes(rom, name)) for value in row)

    def test_the_filled_bar_differs_from_the_empty_bar(self):
        # Arrange
        names = ("bar_empty", "bar_filled")

        # Act
        rom = fixtiles.build_rom()

        # Assert
        assert tile_bytes(rom, names[0]) != tile_bytes(rom, names[1])

    def test_digits_are_visually_distinct(self):
        # Arrange
        digits = [str(d) for d in range(10)]

        # Act
        rom = fixtiles.build_rom()

        # Assert
        assert len({tile_bytes(rom, digit) for digit in digits}) == 10

    def test_padding_smaller_than_the_glyphs_is_rejected(self):
        # Arrange
        size = 32

        # Act
        with pytest.raises(ValueError) as raised:
            fixtiles.build_rom(pad_to=size)

        # Assert
        assert "pad_to" in str(raised.value)


class TestPalette:
    def test_the_overlay_palette_has_sixteen_entries_transparent_first(self):
        # Arrange
        expected_length = 16

        # Act
        words = fixtiles.palette_words()

        # Assert
        assert len(words) == expected_length
        assert words[0] == 0

    def test_the_ink_slot_is_brighter_than_the_panel_slot(self):
        # Arrange
        slots = (fixtiles.INK, fixtiles.PANEL)

        # Act
        words = fixtiles.palette_words()

        # Assert
        assert words[slots[0]] > words[slots[1]]

    def test_the_palette_defines_every_shade_it_uses(self):
        # Arrange
        slots = (fixtiles.INK, fixtiles.PANEL, fixtiles.ACCENT, fixtiles.DIM, fixtiles.EDGE)

        # Act
        words = fixtiles.palette_words()

        # Assert
        assert all(words[slot] != 0 for slot in slots)


class TestOverlayStyling:
    def test_the_track_is_dimmer_than_the_played_portion(self):
        # Arrange
        empty = {pixel for row in glyph("bar_empty") for pixel in row}

        # Act
        filled = {pixel for row in glyph("bar_filled") for pixel in row}

        # Assert
        assert fixtiles.DIM in empty
        assert fixtiles.ACCENT in filled

    def test_the_knob_stands_above_the_track(self):
        # Arrange
        name = "bar_knob"

        # Act
        knob = glyph(name)

        # Assert
        assert any(fixtiles.INK in row for row in knob)

    def test_the_caps_leave_their_outer_edge_clear(self):
        # Arrange
        left = glyph("bar_cap_left")

        # Act
        right = glyph("bar_cap_right")

        # Assert
        assert all(row[0] != fixtiles.DIM for row in left)
        assert all(row[-1] != fixtiles.DIM for row in right)

    def test_the_panel_top_carries_a_highlight_line(self):
        # Arrange
        name = "panel_top"

        # Act
        top = glyph(name)

        # Assert
        assert all(pixel == fixtiles.EDGE for pixel in top[0])
        assert all(pixel == fixtiles.PANEL for pixel in top[1])


class TestGlyphArtResource:
    def test_every_glyph_in_the_rom_order_has_art(self):
        # Arrange
        expected = set(fixtiles.GLYPH_ORDER)

        # Act
        art = font.glyph_art()

        # Assert
        assert set(art) == expected

    def test_every_glyph_is_drawn_on_an_eight_by_eight_grid(self):
        # Arrange
        side = fixtiles.TILE_PX

        # Act
        art = font.glyph_art()

        # Assert
        assert all(len(rows) == side for rows in art.values())
        assert all(len(row) == side for rows in art.values() for row in rows)

    def test_the_rom_holds_one_tile_per_glyph_in_order(self):
        # Arrange
        count = len(fixtiles.GLYPH_ORDER)

        # Act
        rom = fixtiles.build_rom()

        # Assert
        assert len(rom) == count * fixtiles.TILE_BYTES
        assert decode(rom[: fixtiles.TILE_BYTES]) == [[fixtiles.TRANSPARENT] * 8] * 8
