from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

GRID_COLS: Final = 20
GRID_ROWS: Final = 14
SLOT_COUNT: Final = GRID_COLS * GRID_ROWS
VRAM_SCB1: Final = 0x0000
SCB1_WORDS_PER_SPRITE: Final = 64
FIRST_SPRITE: Final = 1
MAX_TILE_NUMBER: Final = 1 << 20
MAX_PALETTE: Final = 1 << 8
PROM_BANK_BYTES: Final = 1 << 20
PROM_BANK_LIMIT: Final = 8


@dataclass(frozen=True, slots=True)
class SlotUpdate:
    col: int
    row: int
    tile: int
    palette: int
    hflip: bool
    vflip: bool


def vram_address(col: int, row: int) -> int:
    if not (0 <= col < GRID_COLS and 0 <= row < GRID_ROWS):
        msg = f"slot ({col}, {row}) falls outside the {GRID_COLS}x{GRID_ROWS} grid"
        raise ValueError(msg)
    return VRAM_SCB1 + (col + FIRST_SPRITE) * SCB1_WORDS_PER_SPRITE + row * 2


def attribute_word(*, palette: int, tile: int, hflip: bool, vflip: bool) -> int:
    if not 0 <= palette < MAX_PALETTE:
        msg = f"palette {palette} does not fit the 8-bit attribute field"
        raise ValueError(msg)
    if not 0 <= tile < MAX_TILE_NUMBER:
        msg = f"tile {tile} does not fit the 20-bit tile number"
        raise ValueError(msg)
    return (palette << 8) | (((tile >> 16) & 0x0F) << 4) | (int(vflip) << 1) | int(hflip)


def pack_frame(updates: list[SlotUpdate]) -> bytes:
    ordered = sorted(updates, key=lambda u: (u.col, u.row))
    seen: set[tuple[int, int]] = set()
    for item in ordered:
        slot = (item.col, item.row)
        if slot in seen:
            msg = f"duplicate update for slot {slot} in one frame"
            raise ValueError(msg)
        seen.add(slot)

    runs: list[list[SlotUpdate]] = []
    for item in ordered:
        if runs:
            last = runs[-1][-1]
            if last.col == item.col and last.row + 1 == item.row:
                runs[-1].append(item)
                continue
        runs.append([item])

    out = bytearray(struct.pack(">H", len(runs)))
    for run in runs:
        head = run[0]
        out += struct.pack(">HH", vram_address(head.col, head.row), len(run))
        for item in run:
            out += struct.pack(
                ">HH",
                item.tile & 0xFFFF,
                attribute_word(
                    palette=item.palette, tile=item.tile, hflip=item.hflip, vflip=item.vflip
                ),
            )
    return bytes(out)


class MovieStream:
    def __init__(self, *, bank_size: int = PROM_BANK_BYTES) -> None:
        self._bank_size = bank_size
        self._blob = bytearray()
        self._offsets: list[int] = []
        self._keyframes: list[int] = []

    def __len__(self) -> int:
        return len(self._offsets)

    def append(self, updates: list[SlotUpdate], *, keyframe: bool = False) -> None:
        record = pack_frame(updates)
        if len(record) > self._bank_size:
            msg = f"frame record of {len(record)} bytes exceeds the {self._bank_size} byte bank"
            raise ValueError(msg)
        start = len(self._blob)
        if start // self._bank_size != (start + len(record) - 1) // self._bank_size:
            start = (start // self._bank_size + 1) * self._bank_size
            self._blob += bytes(start - len(self._blob))
        if keyframe:
            self._keyframes.append(len(self._offsets))
        self._offsets.append(start)
        self._blob += record

    def payload_size(self) -> int:
        return len(self._blob)

    def bank_count(self) -> int:
        banks = max(1, (len(self._blob) + self._bank_size - 1) // self._bank_size)
        if banks > PROM_BANK_LIMIT:
            msg = (
                f"stream needs {banks} banks but the hardware bank register holds only "
                f"{PROM_BANK_LIMIT}; shorten the clip or compress the stream"
            )
            raise ValueError(msg)
        return banks

    def blob(self) -> bytes:
        return bytes(self._blob).ljust(self.bank_count() * self._bank_size, b"\x00")

    def frame_offsets(self) -> npt.NDArray[np.uint32]:
        return np.array(self._offsets, dtype=np.uint32)

    def keyframes(self) -> npt.NDArray[np.uint32]:
        return np.array(self._keyframes, dtype=np.uint32)

    def index_blob(self) -> bytes:
        return self.frame_offsets().astype(">u4").tobytes()

    def keyframe_blob(self) -> bytes:
        return self.keyframes().astype(">u4").tobytes()
