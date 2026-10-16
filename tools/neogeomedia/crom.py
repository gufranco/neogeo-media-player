from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

TILE_PX: Final = 16
TILE_BYTES_PER_ROM: Final = 64
TILE_BYTES: Final = TILE_BYTES_PER_ROM * 2
MIN_ROM_BYTES: Final = 1 << 20
TILE_BATCH_DIMS: Final = 3
MAX_PIXEL_INDEX: Final = 0x0F

_BIT_POSITIONS: Final = np.arange(8, dtype=np.uint8)


def pack_tiles(tiles: npt.NDArray[np.uint8]) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.uint8]]:
    if tiles.ndim != TILE_BATCH_DIMS or tiles.shape[1:] != (TILE_PX, TILE_PX):
        msg = f"tiles must be a batch of 16x16 arrays, got shape {tiles.shape}"
        raise ValueError(msg)
    if tiles.size and int(tiles.max()) > MAX_PIXEL_INDEX:
        msg = "tile pixels must be 4-bit palette indices in the range 0 to 15"
        raise ValueError(msg)

    count = tiles.shape[0]
    c1 = np.zeros((count, TILE_BYTES_PER_ROM), dtype=np.uint8)
    c2 = np.zeros((count, TILE_BYTES_PER_ROM), dtype=np.uint8)
    if count == 0:
        return c1, c2

    for row in range(TILE_PX):
        for half_offset, columns in ((0, slice(8, 16)), (32, slice(0, 8))):
            block = tiles[:, row, columns].astype(np.uint8)
            byte = half_offset + (row << 1)
            c1[:, byte] = np.bitwise_or.reduce((block & 1) << _BIT_POSITIONS, axis=1)
            c1[:, byte + 1] = np.bitwise_or.reduce(((block >> 1) & 1) << _BIT_POSITIONS, axis=1)
            c2[:, byte] = np.bitwise_or.reduce(((block >> 2) & 1) << _BIT_POSITIONS, axis=1)
            c2[:, byte + 1] = np.bitwise_or.reduce(((block >> 3) & 1) << _BIT_POSITIONS, axis=1)

    return c1, c2


def rom_size_for(tile_count: int) -> int:
    payload = tile_count * TILE_BYTES_PER_ROM
    size = MIN_ROM_BYTES
    while size < payload:
        size <<= 1
    return size


def build_rom_images(
    tiles: npt.NDArray[np.uint8], *, pad_to: int | None = None
) -> tuple[bytes, bytes]:
    c1, c2 = pack_tiles(tiles)
    target = rom_size_for(tiles.shape[0]) if pad_to is None else pad_to
    payload = tiles.shape[0] * TILE_BYTES_PER_ROM
    if target < payload:
        msg = f"pad_to {target} is smaller than the {payload} byte payload"
        raise ValueError(msg)
    return c1.tobytes().ljust(target, b"\x00"), c2.tobytes().ljust(target, b"\x00")


def unpack_tiles(
    first: npt.NDArray[np.uint8], second: npt.NDArray[np.uint8]
) -> npt.NDArray[np.uint8]:
    count = first.shape[0]
    tiles = np.zeros((count, TILE_PX, TILE_PX), dtype=np.uint8)
    for row in range(TILE_PX):
        for half_offset, columns in ((0, slice(8, 16)), (32, slice(0, 8))):
            byte = half_offset + (row << 1)
            plane0 = (first[:, byte, None] >> _BIT_POSITIONS) & 1
            plane1 = (first[:, byte + 1, None] >> _BIT_POSITIONS) & 1
            plane2 = (second[:, byte, None] >> _BIT_POSITIONS) & 1
            plane3 = (second[:, byte + 1, None] >> _BIT_POSITIONS) & 1
            tiles[:, row, columns] = plane0 | (plane1 << 1) | (plane2 << 2) | (plane3 << 3)
    return tiles
