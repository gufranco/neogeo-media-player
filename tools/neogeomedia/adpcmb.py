from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

import numpy as np
import numpy.typing as npt

STEP_SCALE: Final = (57, 57, 57, 57, 77, 102, 128, 153)
STEP_MIN: Final = 127
STEP_MAX: Final = 24576
SAMPLE_MIN: Final = -32768
SAMPLE_MAX: Final = 32767

CHIP_CLOCK_HZ: Final = 8_000_000
CHIP_DIVIDER: Final = 144
CHIP_RATE_HZ: Final = Fraction(CHIP_CLOCK_HZ, CHIP_DIVIDER)
DELTA_N_UNITY: Final = 0x10000
DELTA_N_MAX: Final = 0xFFFF
BASE_RATE_HZ: Final = float(CHIP_RATE_HZ)
PAGE_BYTES: Final = 256
SILENT_BYTE: Final = 0x08
ADPCM_B_MAX_BYTES: Final = 16 << 20


@dataclass(frozen=True, slots=True)
class EncodedAudio:
    payload: bytes
    sample_count: int
    delta_n: int

    @property
    def start_address(self) -> int:
        return 0

    @property
    def end_address(self) -> int:
        return (len(self.payload) - 1) >> 8


def delta_n_for(rate_hz: float) -> int:
    if not 0 < rate_hz <= BASE_RATE_HZ:
        msg = f"rate {rate_hz} must be above 0 and at most {BASE_RATE_HZ} Hz"
        raise ValueError(msg)
    return min(DELTA_N_MAX, round(rate_hz * DELTA_N_UNITY / CHIP_RATE_HZ))


def exact_rate(delta_n: int) -> Fraction:
    return CHIP_RATE_HZ * delta_n / DELTA_N_UNITY


def rate_below(rate_hz: float) -> float:
    delta_n = max(1, math.floor(rate_hz * DELTA_N_UNITY / CHIP_RATE_HZ))
    return rate_for(min(DELTA_N_MAX, delta_n))


def rate_for(delta_n: int) -> float:
    return float(exact_rate(delta_n))


def encode(samples: npt.NDArray[np.integer], *, rate_hz: float = 22050.0) -> EncodedAudio:
    if samples.ndim != 1:
        msg = f"audio must be mono, got shape {samples.shape}"
        raise ValueError(msg)
    if samples.size == 0:
        msg = "cannot encode an empty signal"
        raise ValueError(msg)

    targets = np.clip(samples.astype(np.int32), SAMPLE_MIN, SAMPLE_MAX).tolist()
    accumulator = 0
    step = STEP_MIN
    nibbles: list[int] = []

    for target in targets:
        best_nibble = 0
        best_error = None
        best_accumulator = accumulator
        for candidate in range(16):
            delta = (2 * (candidate & 7) + 1) * step // 8
            if candidate & 8:
                delta = -delta
            landed = accumulator + delta
            if landed < SAMPLE_MIN:
                landed = SAMPLE_MIN
            elif landed > SAMPLE_MAX:
                landed = SAMPLE_MAX
            error = abs(landed - target)
            if best_error is None or error < best_error:
                best_error = error
                best_nibble = candidate
                best_accumulator = landed
        accumulator = best_accumulator
        scaled = (step * STEP_SCALE[best_nibble & 7]) // 64
        step = STEP_MIN if scaled < STEP_MIN else (STEP_MAX if scaled > STEP_MAX else scaled)
        nibbles.append(best_nibble)

    if len(nibbles) % 2:
        nibbles.append(0x08)

    payload = bytearray(len(nibbles) // 2)
    for index in range(0, len(nibbles), 2):
        payload[index // 2] = (nibbles[index] << 4) | nibbles[index + 1]

    remainder = len(payload) % PAGE_BYTES
    if remainder:
        payload += bytes([SILENT_BYTE]) * (PAGE_BYTES - remainder)

    return EncodedAudio(
        payload=bytes(payload), sample_count=samples.size, delta_n=delta_n_for(rate_hz)
    )


def build_rom(encoded: EncodedAudio, *, pad_to: int | None = None) -> bytes:
    target = len(encoded.payload) if pad_to is None else pad_to
    if target < len(encoded.payload):
        msg = f"pad_to {target} is smaller than the {len(encoded.payload)} byte payload"
        raise ValueError(msg)
    if target > ADPCM_B_MAX_BYTES:
        msg = f"ADPCM-B holds at most 16 MiB, asked for {target} bytes"
        raise ValueError(msg)
    return encoded.payload.ljust(target, bytes([SILENT_BYTE]))
