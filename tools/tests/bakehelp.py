from __future__ import annotations

import subprocess
from pathlib import Path

from neogeomedia import bake

TOOLS = Path(__file__).resolve().parents[1]
SYNTHETIC_FILM = TOOLS.parent / "fmv-core-python" / "fixtures" / "synthetic.mp4"
SMALL_FLAGS = ("--palette-count", "4", "--candidates", "0", "--sample-stride", "1")


def lavfi_clip(path: Path, *sources: str, extra: tuple[str, ...] = ()) -> Path:
    inputs = [part for source in sources for part in ("-f", "lavfi", "-i", source)]
    command = ["ffmpeg", "-v", "error", "-y", *inputs, *extra, "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(command, check=True)
    return path


def tone_clip(path: Path) -> Path:
    return lavfi_clip(
        path,
        "testsrc=size=320x240:rate=24:duration=1",
        "sine=frequency=440:duration=1",
        extra=("-shortest",),
    )


def small_request(source: Path, build_dir: Path, **overrides: object) -> bake.BakeRequest:
    settings: dict[str, object] = {
        "start": 0.0,
        "duration": 0.2,
        "palette_count": 4,
        "candidates": 0,
        "sample_stride": 1,
        **overrides,
    }
    return bake.BakeRequest(source=source, build_dir=build_dir, **settings)


def small_argv(source: Path, build_dir: Path, *extra: str, duration: str = "0.2") -> list[str]:
    return [
        "--source",
        str(source),
        "--duration",
        duration,
        "--build-dir",
        str(build_dir),
        *SMALL_FLAGS,
        *extra,
    ]


def generated(outcome: bake.BakeOutcome, name: str) -> str:
    return (outcome.build_dir / "generated" / name).read_text()


def baked_size(outcome: bake.BakeOutcome, name: str) -> int:
    return (outcome.build_dir / "baked" / name).stat().st_size
