from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import colour

C5_LEVELS: Final = 32
COLOR_INDEX_COUNT: Final = C5_LEVELS**3
PALETTE_COLORS: Final = 16
PALETTE_USABLE_COLORS: Final = PALETTE_COLORS - 1
TRANSPARENT_INDEX: Final = 0

_LADDER_OHMS: Final = (3900.0, 2200.0, 1000.0, 470.0, 220.0)
_SMOOTHING_WEIGHT: Final = 1.6
_SMOOTHING_DIVISOR: Final = 4.2


def _raw_c5_to_srgb8(c5: npt.NDArray[np.integer]) -> npt.NDArray[np.uint8]:
    level6 = (c5.astype(np.int32) << 1) | 1
    return ((level6 * 259 + 33) >> 6).astype(np.uint8)


def _resistor_ladder_voltages() -> npt.NDArray[np.float64]:
    voltage = np.zeros(C5_LEVELS, dtype=np.float64)
    for level in range(C5_LEVELS):
        to_vcc = 0.0
        to_gnd = 0.0
        for bit, ohms in enumerate(_LADDER_OHMS):
            if level & (1 << bit):
                to_vcc = ohms if to_vcc == 0.0 else (to_vcc * ohms) / (to_vcc + ohms)
            else:
                to_gnd = ohms if to_gnd == 0.0 else (to_gnd * ohms) / (to_gnd + ohms)
        if to_vcc == 0.0:
            voltage[level] = 0.0
        elif to_gnd == 0.0:
            voltage[level] = 1.0
        else:
            voltage[level] = to_gnd / (to_vcc + to_gnd)
    return voltage


def _resnet_c5_to_srgb8() -> npt.NDArray[np.uint8]:
    raw = _resistor_ladder_voltages()
    smooth = raw.copy()
    smooth[1:-1] = (
        raw[:-2] * _SMOOTHING_WEIGHT + raw[1:-1] + raw[2:] * _SMOOTHING_WEIGHT
    ) / _SMOOTHING_DIVISOR
    normalized = (smooth - smooth[0]) / (smooth[-1] - smooth[0])
    levels: npt.NDArray[np.uint8] = (normalized * 255.0 + 0.5).astype(np.uint8)
    return levels


RAW_C5_TO_SRGB8: Final[npt.NDArray[np.uint8]] = _raw_c5_to_srgb8(np.arange(C5_LEVELS))
C5_TO_SRGB8: Final[npt.NDArray[np.uint8]] = _resnet_c5_to_srgb8()


def _srgb8_to_c5(value: npt.NDArray[np.integer]) -> npt.NDArray[np.uint8]:
    table = C5_TO_SRGB8.astype(np.int32)
    distance = np.abs(value.astype(np.int32)[..., None] - table)
    return np.argmin(distance, axis=-1).astype(np.uint8)


SRGB8_TO_C5: Final[npt.NDArray[np.uint8]] = _srgb8_to_c5(np.arange(256))


def pack_palette_word(r5: int, g5: int, b5: int, *, dark: bool = False) -> int:
    for name, value in (("r5", r5), ("g5", g5), ("b5", b5)):
        if not 0 <= value < C5_LEVELS:
            msg = f"{name} out of range: {value}"
            raise ValueError(msg)
    return (
        (0x8000 if dark else 0)
        | ((r5 & 1) << 14)
        | ((g5 & 1) << 13)
        | ((b5 & 1) << 12)
        | ((r5 >> 1) << 8)
        | ((g5 >> 1) << 4)
        | (b5 >> 1)
    )


def rgb_to_color_index(rgb: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint16]:
    c5 = SRGB8_TO_C5[rgb].astype(np.uint16)
    packed = (c5[..., 0] << 10) | (c5[..., 1] << 5) | c5[..., 2]
    return packed.astype(np.uint16)


def color_index_to_c5(index: npt.NDArray[np.integer]) -> npt.NDArray[np.uint8]:
    idx = index.astype(np.int32)
    return np.stack(
        [(idx >> 10) & 0x1F, (idx >> 5) & 0x1F, idx & 0x1F],
        axis=-1,
    ).astype(np.uint8)


def color_index_to_rgb(index: npt.NDArray[np.integer]) -> npt.NDArray[np.uint8]:
    return C5_TO_SRGB8[color_index_to_c5(index)]


def color_index_to_palette_word(index: npt.NDArray[np.integer]) -> npt.NDArray[np.uint16]:
    c5 = color_index_to_c5(index).astype(np.uint16)
    r5, g5, b5 = c5[..., 0], c5[..., 1], c5[..., 2]
    return (
        ((r5 & 1) << 14)
        | ((g5 & 1) << 13)
        | ((b5 & 1) << 12)
        | ((r5 >> 1) << 8)
        | ((g5 >> 1) << 4)
        | (b5 >> 1)
    ).astype(np.uint16)


def build_oklab_grid() -> npt.NDArray[np.float32]:
    index = np.arange(COLOR_INDEX_COUNT)
    return colour.srgb_to_oklab(color_index_to_rgb(index) / colour.BYTE_MAX)
