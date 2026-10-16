from __future__ import annotations

import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt

from neogeomedia import adpcmb, frames

V_ROM_MIN_BYTES: Final = 1 << 19
SAMPLES_PER_PAGE: Final = 512
BYTE_MASK: Final = 0xFF
BYTE_BITS: Final = 8
VOICE_FILE: Final = "v2.bin"


@dataclass(frozen=True, slots=True)
class Voice:
    path: Path | None
    pages: Fraction


def has_audio_stream(source: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(source),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _decode_command(source: Path, start: float, duration: float, rate_hz: float) -> list[str]:
    return [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        f"{start:.6f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.6f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(int(rate_hz)),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-",
    ]


def decode_audio(
    source: Path, start: float, duration: float, rate_hz: float
) -> npt.NDArray[np.int16]:
    if not has_audio_stream(source):
        return np.zeros(0, dtype=np.int16)
    command = _decode_command(source, start, duration, rate_hz)
    result = subprocess.run(command, capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype="<i2")


def audio_pages_per_frame(delta_n: int) -> Fraction:
    if delta_n <= 0:
        return Fraction(0)
    return adpcmb.exact_rate(delta_n) / (SAMPLES_PER_PAGE * frames.VBLANK_FPS)


def _register_pair(name: str, value: int) -> list[str]:
    return [
        f"    {name}_LO = 0x{value & BYTE_MASK:02x}",
        f"    {name}_HI = 0x{(value >> BYTE_BITS) & BYTE_MASK:02x}",
    ]


def write_audio_params(build_dir: Path, encoded: adpcmb.EncodedAudio) -> Path:
    generated = build_dir / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    path = generated / "audio_params.s"
    lines = [
        *_register_pair("ADPCM_B_START", encoded.start_address),
        *_register_pair("ADPCM_B_END", encoded.end_address),
        *_register_pair("ADPCM_B_DELTA", encoded.delta_n),
        "",
    ]
    path.write_text("\n".join(lines))
    return path


def bake_voice(
    *, source: Path, start: float, duration: float, rate_hz: float, baked: Path, build_dir: Path
) -> Voice:
    samples = decode_audio(source, start, duration, rate_hz)
    if not samples.size:
        return Voice(path=None, pages=Fraction(0))
    encoded = adpcmb.encode(samples, rate_hz=rate_hz)
    voice = adpcmb.build_rom(encoded, pad_to=max(V_ROM_MIN_BYTES, len(encoded.payload)))
    path = baked / VOICE_FILE
    path.write_bytes(voice)
    write_audio_params(build_dir, encoded)
    return Voice(path=path, pages=audio_pages_per_frame(encoded.delta_n))
