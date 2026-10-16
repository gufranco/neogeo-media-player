from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from neogeomedia import neocolor

TILE_PX: Final = 16
TILE_PIXELS: Final = TILE_PX * TILE_PX
PALETTE_SLOTS: Final = neocolor.PALETTE_USABLE_COLORS
CRAM_BANKS: Final = 256
DESCRIPTOR_DIMS: Final = 9
_KMEANS_ITERATIONS: Final = 24
_ASSIGN_CHUNK_BYTES: Final = 64 << 20
_MIX_SCALE: Final = 255.0

DEFAULT_CHROMA_WEIGHT: Final = 1.0

_BAYER_ORDER: Final = 8
_BAYER_8 = np.array(
    [
        [0, 32, 8, 40, 2, 34, 10, 42],
        [48, 16, 56, 24, 50, 18, 58, 26],
        [12, 44, 4, 36, 14, 46, 6, 38],
        [60, 28, 52, 20, 62, 30, 54, 22],
        [3, 35, 11, 43, 1, 33, 9, 41],
        [51, 19, 59, 27, 49, 17, 57, 25],
        [15, 47, 7, 39, 13, 45, 5, 37],
        [63, 31, 55, 23, 61, 29, 53, 21],
    ],
    dtype=np.float32,
)


def bayer_thresholds() -> npt.NDArray[np.float32]:
    unit = (_BAYER_8 + 0.5) / float(_BAYER_ORDER * _BAYER_ORDER)
    repeat = TILE_PX // _BAYER_ORDER
    return np.tile(unit, (repeat, repeat)).astype(np.float32)


_OKLAB_GRIDS: dict[float, npt.NDArray[np.float32]] = {}


def oklab_grid(chroma_weight: float = DEFAULT_CHROMA_WEIGHT) -> npt.NDArray[np.float32]:
    if chroma_weight <= 0.0:
        msg = f"chroma weight must be positive, got {chroma_weight}"
        raise ValueError(msg)
    cached = _OKLAB_GRIDS.get(chroma_weight)
    if cached is None:
        grid = neocolor.build_oklab_grid()
        if chroma_weight != 1.0:
            grid = grid * np.array(
                [1.0, np.sqrt(chroma_weight), np.sqrt(chroma_weight)], dtype=np.float32
            )
        cached = grid.astype(np.float32)
        _OKLAB_GRIDS[chroma_weight] = cached
    return cached


@dataclass(frozen=True, slots=True)
class PaletteSet:
    colors: npt.NDArray[np.uint16]
    base_bank: int
    descriptors: npt.NDArray[np.float32] | None = None
    chroma_weight: float = DEFAULT_CHROMA_WEIGHT

    def __post_init__(self) -> None:
        if self.colors.ndim != 2 or self.colors.shape[1] != PALETTE_SLOTS:
            msg = f"palette table must be (count, {PALETTE_SLOTS}), got {self.colors.shape}"
            raise ValueError(msg)
        if self.base_bank + self.colors.shape[0] > CRAM_BANKS:
            msg = (
                f"{self.colors.shape[0]} palettes at base bank {self.base_bank} "
                f"overflow the {CRAM_BANKS} CRAM banks"
            )
            raise ValueError(msg)

    def __len__(self) -> int:
        return int(self.colors.shape[0])

    def bank_of(self, palette_id: int) -> int:
        return self.base_bank + palette_id

    def cram_blob(self) -> bytes:
        words = np.zeros((len(self), neocolor.PALETTE_COLORS), dtype=">u2")
        words[:, 1:] = neocolor.color_index_to_palette_word(self.colors).astype(">u2")
        return words.tobytes()


@dataclass(frozen=True, slots=True)
class Assignment:
    palette_ids: npt.NDArray[np.uint8]
    nibbles: npt.NDArray[np.uint8]
    error: npt.NDArray[np.float32]

    def rendered(self, palette_set: PaletteSet) -> npt.NDArray[np.uint16]:
        if self.palette_ids.size == 0:
            return np.zeros((0, TILE_PX, TILE_PX), dtype=np.uint16)
        return palette_set.colors[self.palette_ids[:, None, None], self.nibbles - 1]


def _two_nearest(
    distance: npt.NDArray[np.float32],
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.uint8], npt.NDArray[np.uint8]]:
    pair = np.argpartition(distance, 1, axis=1)[:, :2]
    picked = np.take_along_axis(distance, pair, axis=1)
    swapped = picked[:, 0] > picked[:, 1]
    nearest = np.where(swapped, pair[:, 1], pair[:, 0])
    runner = np.where(swapped, pair[:, 0], pair[:, 1])
    near = np.sqrt(np.minimum(picked[:, 0], picked[:, 1]))
    far = np.sqrt(np.maximum(picked[:, 0], picked[:, 1]))
    total = near + far
    share = np.divide(near, total, out=np.zeros_like(near), where=total > 0.0)
    return (
        nearest.astype(np.uint8),
        runner.astype(np.uint8),
        np.rint(share * _MIX_SCALE).astype(np.uint8),
    )


def _sqdist(
    points: npt.NDArray[np.float32], centres: npt.NDArray[np.float32]
) -> npt.NDArray[np.float32]:
    gram = points @ centres.T
    distance: npt.NDArray[np.float32] = (
        (points * points).sum(axis=1)[:, None]
        - 2.0 * gram
        + (centres * centres).sum(axis=1)[None, :]
    ).astype(np.float32)
    return distance


def _tile_descriptors(
    tiles: npt.NDArray[np.uint16], chroma_weight: float = DEFAULT_CHROMA_WEIGHT
) -> npt.NDArray[np.float32]:
    grid = oklab_grid(chroma_weight)
    lab = grid[tiles.reshape(tiles.shape[0], TILE_PIXELS)]
    lightness = lab[:, :, 0]
    darkest = lab[np.arange(lab.shape[0]), np.argmin(lightness, axis=1)]
    brightest = lab[np.arange(lab.shape[0]), np.argmax(lightness, axis=1)]
    return np.concatenate([lab.mean(axis=1), darkest, brightest], axis=1).astype(np.float32)


def _kmeans(
    points: npt.NDArray[np.float32], count: int, seed: int
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.float32]]:
    rng = np.random.default_rng(seed)
    unique = np.unique(points, axis=0)
    if unique.shape[0] <= count:
        centroids = np.concatenate(
            [unique, unique[rng.integers(0, unique.shape[0], count - unique.shape[0])]]
        ).astype(np.float32)
    else:
        centroids = unique[rng.choice(unique.shape[0], count, replace=False)].astype(np.float32)

    labels = np.zeros(points.shape[0], dtype=np.int64)
    for _ in range(_KMEANS_ITERATIONS):
        labels = np.argmin(_sqdist(points, centroids), axis=1)
        moved = False
        for index in range(count):
            members = points[labels == index]
            if members.shape[0] == 0:
                continue
            mean = members.mean(axis=0).astype(np.float32)
            if not np.allclose(mean, centroids[index]):
                centroids[index] = mean
                moved = True
        if not moved:
            break
    return labels, centroids


def _refine(
    lab: npt.NDArray[np.float32],
    weight: npt.NDArray[np.float64],
    centroids: npt.NDArray[np.float32],
    rng: np.random.Generator,
) -> bool:
    labels = np.argmin(_sqdist(lab, centroids), axis=1)
    moved = False
    for index in range(PALETTE_SLOTS):
        mask = labels == index
        if not mask.any():
            centroids[index] = lab[rng.integers(0, lab.shape[0])]
            moved = True
            continue
        total = weight[mask].sum()
        mean = (lab[mask] * weight[mask, None]).sum(axis=0) / total
        if not np.allclose(mean, centroids[index]):
            centroids[index] = mean.astype(np.float32)
            moved = True
    return moved


def _fit_palette(
    colors: npt.NDArray[np.uint16],
    counts: npt.NDArray[np.int64],
    seed: int,
    chroma_weight: float = DEFAULT_CHROMA_WEIGHT,
) -> npt.NDArray[np.uint16]:
    grid = oklab_grid(chroma_weight)
    if colors.shape[0] <= PALETTE_SLOTS:
        padded = np.resize(colors, PALETTE_SLOTS)
        return padded.astype(np.uint16)

    lab = grid[colors]
    weight = counts.astype(np.float64)
    rng = np.random.default_rng(seed)
    order = np.argsort(-weight)
    centroids = lab[order[:PALETTE_SLOTS]].astype(np.float32)
    for _ in range(_KMEANS_ITERATIONS):
        if not _refine(lab, weight, centroids, rng):
            break

    chosen = colors[np.argmin(_sqdist(lab, centroids), axis=0)]
    return chosen.astype(np.uint16)


def _cluster_palettes(
    flat: npt.NDArray[np.uint16],
    labels: npt.NDArray[np.int64],
    count: int,
    seed: int,
    chroma_weight: float,
) -> npt.NDArray[np.uint16]:
    palettes = np.zeros((count, PALETTE_SLOTS), dtype=np.uint16)
    for index in range(count):
        members = flat[labels == index]
        if members.size == 0:
            members = flat
        colors, counts = np.unique(members.reshape(-1), return_counts=True)
        palettes[index] = _fit_palette(colors, counts, seed + index, chroma_weight)
    return palettes


def build_palette_set(
    tiles: npt.NDArray[np.uint16],
    *,
    count: int,
    base_bank: int,
    seed: int,
    chroma_weight: float = DEFAULT_CHROMA_WEIGHT,
) -> PaletteSet:
    if tiles.shape[0] == 0:
        msg = "cannot build a palette set from an empty tile batch"
        raise ValueError(msg)
    if base_bank + count > CRAM_BANKS:
        msg = f"{count} palettes at base bank {base_bank} overflow the {CRAM_BANKS} CRAM banks"
        raise ValueError(msg)

    descriptors = _tile_descriptors(tiles, chroma_weight)
    labels, centroids = _kmeans(descriptors, count, seed)

    flat = tiles.reshape(tiles.shape[0], TILE_PIXELS)
    return PaletteSet(
        colors=_cluster_palettes(flat, labels, count, seed, chroma_weight),
        base_bank=base_bank,
        descriptors=centroids,
        chroma_weight=chroma_weight,
    )


class PaletteAssigner:
    def __init__(
        self, palette_set: PaletteSet, *, candidates: int = 0, dither: bool = False
    ) -> None:
        self._palette_set = palette_set
        self._candidates = min(candidates if candidates > 0 else len(palette_set), len(palette_set))
        grid = oklab_grid(palette_set.chroma_weight)
        total = len(palette_set)
        self._slot = np.zeros((total, grid.shape[0]), dtype=np.uint8)
        self._error = np.zeros((total, grid.shape[0]), dtype=np.float32)
        self._second = np.zeros((total, grid.shape[0]), dtype=np.uint8) if dither else None
        self._mix = np.zeros((total, grid.shape[0]), dtype=np.uint8) if dither else None
        for index in range(total):
            palette_lab = grid[palette_set.colors[index]]
            distance = ((grid[:, None, :] - palette_lab[None, :, :]) ** 2).sum(axis=2)
            self._slot[index] = np.argmin(distance, axis=1).astype(np.uint8)
            self._error[index] = np.min(distance, axis=1).astype(np.float32)
            if self._second is not None and self._mix is not None:
                nearest, runner, share = _two_nearest(distance)
                self._slot[index] = nearest
                self._second[index] = runner
                self._mix[index] = share
        self._threshold = (bayer_thresholds().reshape(TILE_PIXELS) * _MIX_SCALE).astype(np.float32)
        self._chunk = max(1, _ASSIGN_CHUNK_BYTES // (self._candidates * TILE_PIXELS * 4))

    def assign(self, tiles: npt.NDArray[np.uint16]) -> Assignment:
        count = tiles.shape[0]
        if count == 0:
            return Assignment(
                palette_ids=np.zeros(0, dtype=np.uint8),
                nibbles=np.zeros((0, TILE_PX, TILE_PX), dtype=np.uint8),
                error=np.zeros(0, dtype=np.float32),
            )

        flat = tiles.reshape(count, TILE_PIXELS)
        palette_ids = np.zeros(count, dtype=np.uint8)
        best_error = np.zeros(count, dtype=np.float32)
        nibbles = np.zeros((count, TILE_PIXELS), dtype=np.uint8)

        shortlist = self._shortlist(tiles)
        for start in range(0, count, self._chunk):
            stop = min(start + self._chunk, count)
            chosen, error, quantised = self._assign_span(flat[start:stop], shortlist[start:stop])
            palette_ids[start:stop] = chosen.astype(np.uint8)
            best_error[start:stop] = error
            nibbles[start:stop] = quantised

        return Assignment(
            palette_ids=palette_ids,
            nibbles=nibbles.reshape(count, TILE_PX, TILE_PX),
            error=best_error,
        )

    def _assign_span(
        self, pixels: npt.NDArray[np.uint16], picks: npt.NDArray[np.int64]
    ) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.float32], npt.NDArray[np.uint8]]:
        errors = self._error[picks[:, :, None], pixels[:, None, :]].sum(axis=2)
        winner = np.argmin(errors, axis=1)
        rows = np.arange(pixels.shape[0])
        chosen = picks[rows, winner]
        return chosen, errors[rows, winner], self._quantise(chosen, pixels) + 1

    def _quantise(
        self, chosen: npt.NDArray[np.int64], pixels: npt.NDArray[np.uint16]
    ) -> npt.NDArray[np.uint8]:
        nearest = self._slot[chosen[:, None], pixels]
        if self._second is None or self._mix is None:
            return nearest
        share = self._mix[chosen[:, None], pixels]
        runner = self._second[chosen[:, None], pixels]
        return np.where(share > self._threshold[None, :], runner, nearest).astype(np.uint8)

    def _shortlist(self, tiles: npt.NDArray[np.uint16]) -> npt.NDArray[np.int64]:
        total = len(self._palette_set)
        if self._candidates >= total or self._palette_set.descriptors is None:
            return np.tile(np.arange(total), (tiles.shape[0], 1))
        descriptors = _tile_descriptors(tiles)
        centroids = self._palette_set.descriptors
        distance = _sqdist(descriptors, centroids)
        return np.argpartition(distance, self._candidates - 1, axis=1)[:, : self._candidates]
