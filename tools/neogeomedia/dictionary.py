from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from neogeomedia import crom

TILE_PX: Final = 16
MAX_TILES: Final = 1 << 20
DIGEST_BYTES: Final = 16
_HFLIP: Final = 1
_VFLIP: Final = 2
_INDEX_SHIFT: Final = 2


@dataclass(frozen=True, slots=True)
class TileRef:
    index: int
    hflip: bool
    vflip: bool


class TileDictionary:
    def __init__(self, *, allow_flip: bool = False, capacity: int = MAX_TILES) -> None:
        self._allow_flip = allow_flip
        self.capacity = min(capacity, MAX_TILES)
        self._count = 0
        self._first = bytearray()
        self._second = bytearray()
        self._lookup: dict[bytes, int] = {}
        self._salt = b"\x00\x00\x00\x00"

    def __len__(self) -> int:
        return self._count

    def is_full(self) -> bool:
        return self._count >= self.capacity

    def reseed(self, epoch: int) -> None:
        self._salt = epoch.to_bytes(4, "big")

    def _digest(self, first: bytes, second: bytes) -> bytes:
        return hashlib.blake2b(self._salt + first + second, digest_size=DIGEST_BYTES).digest()

    def _reference(self, packed: int) -> TileRef:
        return TileRef(
            index=packed >> _INDEX_SHIFT,
            hflip=bool(packed & _HFLIP),
            vflip=bool(packed & _VFLIP),
        )

    def intern_batch(self, tiles: npt.NDArray[np.uint8]) -> list[TileRef | None]:
        if tiles.shape[0] == 0:
            return []
        first, second = crom.pack_tiles(tiles)
        mirrors = self._mirror_bytes(tiles) if self._allow_flip else None

        refs: list[TileRef | None] = []
        for position in range(tiles.shape[0]):
            head = first[position].tobytes()
            tail = second[position].tobytes()
            key = self._digest(head, tail)
            existing = self._lookup.get(key)
            if existing is not None:
                refs.append(self._reference(existing))
                continue
            if self.is_full():
                refs.append(None)
                continue

            index = self._count
            self._first += head
            self._second += tail
            self._count += 1
            self._lookup[key] = index << _INDEX_SHIFT
            if mirrors is not None:
                self._register_mirrors(mirrors, position, index)
            refs.append(TileRef(index=index, hflip=False, vflip=False))
        return refs

    def intern(self, tile: npt.NDArray[np.uint8]) -> TileRef:
        if tile.shape != (TILE_PX, TILE_PX):
            msg = f"tile must be 16x16, got shape {tile.shape}"
            raise ValueError(msg)
        reference = self.intern_batch(tile[None])[0]
        if reference is None:
            msg = f"dictionary is full at {self.capacity} tiles"
            raise ValueError(msg)
        return reference

    def _mirror_bytes(
        self, tiles: npt.NDArray[np.uint8]
    ) -> list[tuple[npt.NDArray[np.uint8], npt.NDArray[np.uint8], int]]:
        variants = (
            (np.ascontiguousarray(tiles[:, :, ::-1]), _HFLIP),
            (np.ascontiguousarray(tiles[:, ::-1, :]), _VFLIP),
            (np.ascontiguousarray(tiles[:, ::-1, ::-1]), _HFLIP | _VFLIP),
        )
        return [(*crom.pack_tiles(variant), flags) for variant, flags in variants]

    def _register_mirrors(
        self,
        mirrors: list[tuple[npt.NDArray[np.uint8], npt.NDArray[np.uint8], int]],
        position: int,
        index: int,
    ) -> None:
        for head, tail, flags in mirrors:
            key = self._digest(head[position].tobytes(), tail[position].tobytes())
            self._lookup.setdefault(key, (index << _INDEX_SHIFT) | flags)

    def payload_bytes(self) -> int:
        return self._count * crom.TILE_BYTES_PER_ROM

    def rom_images(self, *, pad_to: int | None = None) -> tuple[bytes, bytes]:
        target = crom.rom_size_for(self._count) if pad_to is None else pad_to
        payload = self._count * crom.TILE_BYTES_PER_ROM
        if target < payload:
            msg = f"pad_to {target} is smaller than the {payload} byte payload"
            raise ValueError(msg)
        return (
            bytes(self._first).ljust(target, b"\x00"),
            bytes(self._second).ljust(target, b"\x00"),
        )

    def tiles(self) -> npt.NDArray[np.uint8]:
        if self._count == 0:
            return np.zeros((0, TILE_PX, TILE_PX), dtype=np.uint8)
        first = np.frombuffer(bytes(self._first), dtype=np.uint8).reshape(self._count, -1)
        second = np.frombuffer(bytes(self._second), dtype=np.uint8).reshape(self._count, -1)
        return crom.unpack_tiles(first, second)
