from __future__ import annotations

from typing import Final

from fmvcore import font
from fmvcore import subtitles as srt

from neogeomedia import fixtiles

COLUMNS: Final = 40
MAX_LINES: Final = 2
RECORD_BYTES: Final = 8 + COLUMNS * MAX_LINES


def layout(text: str) -> tuple[str, ...]:
    return srt.layout(text, columns=COLUMNS, max_lines=MAX_LINES)


def _glyph(character: str) -> int:
    if character in font.PUNCTUATION:
        return fixtiles.GLYPHS.get(font.PUNCTUATION[character], fixtiles.GLYPHS["blank"])
    if character in fixtiles.GLYPHS:
        return fixtiles.GLYPHS[character]
    return fixtiles.GLYPHS.get(character.upper(), fixtiles.GLYPHS["blank"])


def _row(line: str) -> bytes:
    blank = fixtiles.GLYPHS["blank"]
    cells = [blank] * COLUMNS
    start = max(0, (COLUMNS - len(line)) // 2)
    for offset, character in enumerate(line[:COLUMNS]):
        cells[start + offset] = _glyph(character)
    return bytes(cells)


def frame_span(cue: srt.Cue, *, fps: float) -> tuple[int, int]:
    return round(cue.start * fps), round(cue.end * fps)


def encode(cues: list[srt.Cue], *, fps: float) -> bytes:
    blob = bytearray()
    blank_row = bytes([fixtiles.GLYPHS["blank"]] * COLUMNS)
    for cue in srt.trimmed(cues):
        start, end = frame_span(cue, fps=fps)
        blob += start.to_bytes(4, "big") + end.to_bytes(4, "big")
        rows = layout(" ".join(cue.lines))
        for index in range(MAX_LINES):
            blob += _row(rows[index]) if index < len(rows) else blank_row
    return bytes(blob)
