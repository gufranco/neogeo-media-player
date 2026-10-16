from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np

from neogeomedia import encode, fixtiles, frames, subtitles

S_ROM_BYTES: Final = 131072
WORD_BYTES: Final = 2
FPS: Final = float(frames.VBLANK_FPS)

Payload = dict[str, tuple[Path, bytes]]


def palette_blob(result: encode.EncodeResult) -> bytes:
    return b"".join(palette_set.cram_blob() for palette_set in result.palette_sets)


def epoch_blob(result: encode.EncodeResult) -> bytes:
    return np.asarray(result.epoch_starts, dtype=">u4").tobytes()


def fix_palette_blob() -> bytes:
    return b"".join(word.to_bytes(WORD_BYTES, "big") for word in fixtiles.palette_words())


def _sidecar(source: Path, explicit: Path | None) -> Path | None:
    if explicit is None:
        return subtitles.sidecar_for(source)
    sidecar = Path(explicit)
    if not sidecar.is_file():
        raise FileNotFoundError(f"subtitle file not found: {sidecar}")
    return sidecar


def _windowed(cues: list[subtitles.Cue], start: float, duration: float) -> list[subtitles.Cue]:
    end = start + duration
    shifted = [
        subtitles.Cue(start=cue.start - start, end=min(cue.end, end) - start, lines=cue.lines)
        for cue in cues
        if cue.end > start and cue.start < end
    ]
    return [
        subtitles.Cue(start=max(0.0, cue.start), end=cue.end, lines=cue.lines)
        for cue in shifted
        if cue.end > 0.0
    ]


def subtitle_blob(*, source: Path, explicit: Path | None, start: float, duration: float) -> bytes:
    sidecar = _sidecar(source, explicit)
    if sidecar is None:
        return b""
    cues = subtitles.parse(sidecar.read_text(encoding="utf-8", errors="replace"))
    return subtitles.encode(_windowed(cues, start, duration), fps=FPS)


def cart_payload(baked: Path, result: encode.EncodeResult, subtitle: bytes) -> Payload:
    c1, c2 = result.dictionary.rom_images(pad_to=result.dictionary.payload_bytes())
    return {
        "c1": (baked / "c1.bin", c1),
        "c2": (baked / "c2.bin", c2),
        "stream": (baked / "stream.bin", result.stream.blob()),
        "index": (baked / "index.bin", result.stream.index_blob()),
        "keyframes": (baked / "keyframes.bin", result.stream.keyframe_blob()),
        "palettes": (baked / "palettes.bin", palette_blob(result)),
        "epochs": (baked / "epochs.bin", epoch_blob(result)),
        "subtitles": (baked / "subtitles.bin", subtitle),
        "fix": (baked / "fix.s1", fixtiles.build_rom(pad_to=S_ROM_BYTES)),
        "fixpal": (baked / "fixpal.bin", fix_palette_blob()),
    }


def write_payload(payload: Payload) -> dict[str, Path]:
    for path, blob in payload.values():
        path.write_bytes(blob if len(blob) % WORD_BYTES == 0 else blob + b"\x00")
    return {key: path for key, (path, _) in payload.items()}
