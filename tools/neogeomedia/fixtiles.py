from __future__ import annotations

import string
from typing import Final

from fmvcore import font

from neogeomedia.neocolor import pack_palette_word

TILE_PX: Final = 8
TILE_BYTES: Final = 32
COLUMN_PAIR_OFFSETS: Final = (0x10, 0x18, 0x00, 0x08)
MAX_TILE_INDEX: Final = 0x1000
MAX_PIXEL_INDEX: Final = 0x0F

TRANSPARENT: Final = 0
INK: Final = 1
PANEL: Final = 2
ACCENT: Final = 3
DIM: Final = 4
EDGE: Final = 5

_PIXEL_CODES: Final = {
    font.PANEL: PANEL,
    font.INK: INK,
    font.ACCENT: ACCENT,
    font.DIM: DIM,
    font.EDGE: EDGE,
    " ": TRANSPARENT,
}

_BAR_TRACK: Final = "C"


def _resolve(row: str) -> list[int]:
    return [PANEL if code == _BAR_TRACK else _PIXEL_CODES[code] for code in row]


GLYPH_ORDER: Final = (
    "blank",
    "panel",
    *string.digits,
    "colon",
    "slash",
    "play",
    "pause",
    "forward",
    "rewind",
    "bar_empty",
    "bar_filled",
    "panel_top",
    "bar_cap_left",
    "bar_cap_right",
    "bar_knob",
    *string.ascii_uppercase,
    *string.ascii_lowercase,
    "percent",
    "dot",
    "dash",
    "comma",
    "apostrophe",
    "question",
    "bang",
)

GLYPHS: Final[dict[str, int]] = {name: index for index, name in enumerate(GLYPH_ORDER)}


def pack_tile(pixels: list[list[int]]) -> bytes:
    if len(pixels) != TILE_PX or any(len(row) != TILE_PX for row in pixels):
        msg = f"fix tile must be 8x8, got {len(pixels)} rows"
        raise ValueError(msg)
    out = bytearray(TILE_BYTES)
    for y in range(TILE_PX):
        for pair, offset in enumerate(COLUMN_PAIR_OFFSETS):
            left = pixels[y][pair * 2]
            right = pixels[y][pair * 2 + 1]
            for value in (left, right):
                if not 0 <= value <= MAX_PIXEL_INDEX:
                    msg = "fix pixels must be 4-bit palette indices in the range 0 to 15"
                    raise ValueError(msg)
            out[offset + y] = (left & 0x0F) | ((right & 0x0F) << 4)
    return bytes(out)


def build_rom(*, pad_to: int | None = None) -> bytes:
    art = font.glyph_art()
    out = bytearray()
    for name in GLYPH_ORDER:
        out += pack_tile([_resolve(row) for row in art[name]])
    if pad_to is not None:
        if pad_to < len(out):
            msg = f"pad_to {pad_to} is smaller than the {len(out)} byte glyph set"
            raise ValueError(msg)
        out = bytearray(bytes(out).ljust(pad_to, b"\x00"))
    return bytes(out)


def palette_words() -> list[int]:
    words = [0] * 16
    for code, colour in font.MENU_COLOURS.items():
        words[_PIXEL_CODES[code]] = pack_palette_word(*colour)
    return words
