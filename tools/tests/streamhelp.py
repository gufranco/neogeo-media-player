from __future__ import annotations

import struct

from neogeomedia import stream

SINGLE_UPDATE_RECORD = b"\x00\x01\x00\x40\x00\x01\x00\x00\x10\x00"
EMPTY_RECORD = b"\x00\x00"


def update(
    col: int,
    row: int,
    *,
    tile: int = 0,
    palette: int = 16,
    hflip: bool = False,
    vflip: bool = False,
) -> stream.SlotUpdate:
    return stream.SlotUpdate(col=col, row=row, tile=tile, palette=palette, hflip=hflip, vflip=vflip)


def row_of(columns: int) -> list[stream.SlotUpdate]:
    return [update(col, 0) for col in range(columns)]


def filled_stream(*, bank_size: int, records: int, columns: int) -> stream.MovieStream:
    movie = stream.MovieStream(bank_size=bank_size)
    for _ in range(records):
        movie.append(row_of(columns))
    return movie


def read_runs(blob: bytes) -> list[tuple[int, list[tuple[int, int]]]]:
    count = struct.unpack_from(">H", blob, 0)[0]
    offset = 2
    runs = []
    for _ in range(count):
        addr, tiles = struct.unpack_from(">HH", blob, offset)
        offset += 4
        entries = []
        for _ in range(tiles):
            entries.append(struct.unpack_from(">HH", blob, offset))
            offset += 4
        runs.append((addr, entries))
    if offset != len(blob):
        msg = f"record carries {len(blob) - offset} trailing bytes"
        raise ValueError(msg)
    return runs
