from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

from neogeomedia import crom, palettes, stream
from neogeomedia.dictionary import TileRef

GRID_COLS: Final = stream.GRID_COLS
GRID_ROWS: Final = stream.GRID_ROWS
TILE_PX: Final = crom.TILE_PX
EMPTY_TILE: Final = -1


class Screen:
    def __init__(self, palette_set: palettes.PaletteSet) -> None:
        self._palette_set = palette_set
        self.tile = np.full((GRID_ROWS, GRID_COLS), EMPTY_TILE, dtype=np.int64)
        self.palette = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.int64)
        self.hflip = np.zeros((GRID_ROWS, GRID_COLS), dtype=bool)
        self.vflip = np.zeros((GRID_ROWS, GRID_COLS), dtype=bool)
        self.render = np.zeros((GRID_ROWS, GRID_COLS, TILE_PX, TILE_PX), dtype=np.uint16)

    def drift(
        self, source: npt.NDArray[np.uint16], targets: npt.NDArray[np.bool_]
    ) -> npt.NDArray[np.float32]:
        grid = palettes.oklab_grid(self._palette_set.chroma_weight)
        source_lab = grid[source[targets]]
        screen_lab = grid[self.render[targets]]
        return ((source_lab - screen_lab) ** 2).sum(axis=3).mean(axis=(1, 2))

    def retarget(self, palette_set: palettes.PaletteSet) -> None:
        self._palette_set = palette_set

    def fidelity(self, source: npt.NDArray[np.uint16]) -> float:
        grid = palettes.oklab_grid(palettes.DEFAULT_CHROMA_WEIGHT)
        error: float = float(((grid[source] - grid[self.render]) ** 2).sum(axis=4).mean())
        return error

    def _shows(self, row: int, col: int, ref: TileRef, bank: int) -> bool:
        return bool(
            self.tile[row, col] == ref.index
            and self.palette[row, col] == bank
            and self.hflip[row, col] == ref.hflip
            and self.vflip[row, col] == ref.vflip
        )

    def _place(self, row: int, col: int, ref: TileRef, bank: int) -> stream.SlotUpdate:
        self.tile[row, col] = ref.index
        self.palette[row, col] = bank
        self.hflip[row, col] = ref.hflip
        self.vflip[row, col] = ref.vflip
        return stream.SlotUpdate(
            col=int(col),
            row=int(row),
            tile=ref.index,
            palette=bank,
            hflip=ref.hflip,
            vflip=ref.vflip,
        )

    def commit(
        self,
        rows: npt.NDArray[np.int64],
        cols: npt.NDArray[np.int64],
        refs: list[TileRef | None],
        assignment: palettes.Assignment,
        *,
        force: bool,
    ) -> list[stream.SlotUpdate]:
        display = assignment.rendered(self._palette_set)
        updates: list[stream.SlotUpdate] = []
        for slot, (row, col) in enumerate(zip(rows, cols, strict=True)):
            ref = refs[slot]
            if ref is None:
                continue
            bank = self._palette_set.bank_of(int(assignment.palette_ids[slot]))
            already = self._shows(row, col, ref, bank)
            self.render[row, col] = display[slot]
            if already and not force:
                continue
            updates.append(self._place(row, col, ref, bank))
        return updates
