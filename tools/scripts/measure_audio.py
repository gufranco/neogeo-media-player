from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import numpy.typing as npt

from neogeomedia import adpcmb, soundtrack

FULL_SCALE = 32767.0
EPS = 1e-12
DEFAULT_WINDOW = 441
DEFAULT_RATE = 18000.0
SNR_MAX = 120.0
SEGMENT_FLOOR = 1e-7
FLOOR_DBFS = 20.0 * math.log10(EPS)


def _float(samples: npt.NDArray[np.integer]) -> npt.NDArray[np.float64]:
    return np.asarray(samples, dtype=np.float64) / FULL_SCALE


def _rms(signal: npt.NDArray[np.float64]) -> float:
    if signal.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(signal**2)))


def loudness_dbfs(samples: npt.NDArray[np.integer]) -> float:
    rms = _rms(_float(samples))
    return 20.0 * math.log10(max(rms, EPS))


def _segment_snr(reference: npt.NDArray[np.float64], test: npt.NDArray[np.float64]) -> float | None:
    signal = float(np.sum(reference**2))
    if signal <= SEGMENT_FLOOR * reference.size:
        return None
    error = float(np.sum((reference - test) ** 2))
    if error <= EPS:
        return SNR_MAX
    return min(SNR_MAX, 10.0 * math.log10(signal / error))


def segmental_snr_db(
    reference: npt.NDArray[np.integer],
    test: npt.NDArray[np.integer],
    *,
    window: int = DEFAULT_WINDOW,
) -> float:
    count = min(reference.size, test.size)
    if count == 0:
        return 0.0
    ref = _float(reference[:count])
    probe = _float(test[:count])
    ref_rms, probe_rms = _rms(ref), _rms(probe)
    if probe_rms > EPS:
        probe = probe * (ref_rms / probe_rms)
    scores = [
        snr
        for start in range(0, count, window)
        if (snr := _segment_snr(ref[start : start + window], probe[start : start + window]))
        is not None
    ]
    return SNR_MAX if not scores else float(np.mean(scores))


def measure(
    output: npt.NDArray[np.integer],
    source: npt.NDArray[np.integer],
    *,
    window: int = DEFAULT_WINDOW,
) -> dict[str, float | int]:
    output_dbfs = loudness_dbfs(output)
    source_dbfs = loudness_dbfs(source)
    return {
        "output_dbfs": round(output_dbfs, 3),
        "source_dbfs": round(source_dbfs, 3),
        "gain_db": round(output_dbfs - source_dbfs, 3),
        "snr_db": round(segmental_snr_db(source, output, window=window), 3),
        "samples": int(min(output.size, source.size)),
    }


def decode_rom(path: Path, *, sample_count: int) -> npt.NDArray[np.int16]:
    return adpcmb.decode(path.read_bytes(), sample_count=sample_count)


def measure_files(
    rom: Path,
    source: Path,
    *,
    start: float,
    duration: float,
    rate: float,
    window: int = DEFAULT_WINDOW,
) -> dict[str, float | int]:
    reference = soundtrack.decode_audio(source, start, duration, rate)
    output = decode_rom(rom, sample_count=reference.size)
    return measure(output, reference, window=window)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Measure a baked ADPCM-B voice against its source."
    )
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    args = parser.parse_args(argv)
    report = measure_files(
        args.rom,
        args.source,
        start=args.start,
        duration=args.duration,
        rate=args.rate,
        window=args.window,
    )
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
