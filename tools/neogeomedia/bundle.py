from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from neogeomedia import crom
from neogeomedia import stream as stream_mod

LIBRARY_DIR_NAME: Final = "src"
MOVIE_DIR_NAME: Final = "movie"
MAKEFILE_NAME: Final = "fmv.mk"
GUIDE_NAME: Final = "README.md"

LIBRARY_SOURCES: Final = (
    "fmv.h",
    "fmv.c",
    "fmv_audio.h",
    "fmv_audio.c",
    "guard.h",
    "guard.c",
    "hw.h",
    "timeline.h",
    "timeline.c",
)

AUDIO_SOURCES: Final = ("sound.s",)

GENERATED_SOURCES: Final = ("movie_data.S", "movie_data.h", "movie_data_value.c")

GENERATED_OPTIONAL: Final = ("audio_params.s",)

PACKAGERS: Final = ("neofile.py", "mamecart.py")

PACKAGER_DIR_NAME: Final = "package"
PACKAGER_SCRIPT: Final = "package.sh"

BAKED_ASSETS: Final = (
    "index.bin",
    "keyframes.bin",
    "palettes.bin",
    "epochs.bin",
    "fixpal.bin",
    "subtitles.bin",
    "stream.bin",
    "c1.bin",
    "c2.bin",
    "fix.s1",
)

BAKED_OPTIONAL: Final = ("v2.bin",)

STREAM_BANK_GLOB: Final = "fmv_stream__bank*.S"
SCRIPT_MODE: Final = 0o755

_TEMPLATES: Final = Path(__file__).resolve().parent / "templates"
LIBRARY_ROOT: Final = Path(__file__).resolve().parents[2] / "src" / "fmv"
PACKAGER_ROOT: Final = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class BundleLayout:
    root: Path
    library: Path
    movie: Path
    makefile: Path
    guide: Path
    stream_banks: int
    has_audio: bool


def rom_image_size(payload: int) -> int:
    size = 1 << 20
    while size < payload:
        size <<= 1
    return size


def _copy_all(names: tuple[str, ...], source: Path, target: Path, *, required: bool) -> list[Path]:
    copied: list[Path] = []
    for name in names:
        origin = source / name
        if not origin.is_file():
            if required:
                msg = f"the bundle needs {name}, which is not in {source}"
                raise FileNotFoundError(msg)
            continue
        shutil.copy2(origin, target / name)
        copied.append(target / name)
    return copied


def _render(name: str, fields: dict[str, object]) -> str:
    return (_TEMPLATES / name).read_text(encoding="utf-8").format(**fields)


@dataclass(frozen=True, slots=True)
class MovieFigures:
    stream_banks: int
    max_updates: int
    tick_cycles: int
    tile_count: int
    crom_payload: int
    crom_size: int
    palette_base: int
    first_sprite: int
    frames: int
    version: tuple[int, int]


def _make_dirs(target: Path) -> tuple[Path, Path]:
    library = target / LIBRARY_DIR_NAME
    movie = target / MOVIE_DIR_NAME
    for directory in (target, library, movie):
        directory.mkdir(parents=True, exist_ok=True)
    return library, movie


def _copy_movie_data(build_dir: Path, movie: Path) -> list[Path]:
    generated = build_dir / "generated"
    baked = build_dir / "baked"
    _copy_all(GENERATED_SOURCES, generated, movie, required=True)
    _copy_all(GENERATED_OPTIONAL, generated, movie, required=False)
    _copy_all(BAKED_ASSETS, baked, movie, required=True)
    return _copy_all(BAKED_OPTIONAL, baked, movie, required=False)


def _write_packagers(target: Path) -> None:
    packagers = target / PACKAGER_DIR_NAME
    packagers.mkdir(parents=True, exist_ok=True)
    _copy_all(PACKAGERS, PACKAGER_ROOT, packagers, required=True)
    script = packagers / PACKAGER_SCRIPT
    script.write_text(_render(PACKAGER_SCRIPT, {"movie_dir": MOVIE_DIR_NAME}), encoding="utf-8")
    script.chmod(SCRIPT_MODE)


def _copy_stream_banks(generated: Path, movie: Path, stream_banks: int) -> None:
    banks = sorted(generated.glob(STREAM_BANK_GLOB))
    if len(banks) != stream_banks:
        msg = (
            f"the bake reports {stream_banks} stream bank(s) but emitted {len(banks)} stub(s); "
            f"the bundle would carry a stream with a hole in it"
        )
        raise ValueError(msg)
    for stub in banks:
        shutil.copy2(stub, movie / stub.name)


def _fields(figures: MovieFigures, voice: list[Path]) -> dict[str, object]:
    major, minor = figures.version
    return {
        "version": f"{major}.{minor}",
        "library_dir": LIBRARY_DIR_NAME,
        "movie_dir": MOVIE_DIR_NAME,
        "packager_dir": PACKAGER_DIR_NAME,
        "stream_banks": figures.stream_banks,
        "last_bank": figures.stream_banks - 1,
        "bank_numbers": " ".join(str(bank) for bank in range(figures.stream_banks)),
        "max_updates": figures.max_updates,
        "tick_cycles": figures.tick_cycles,
        "tile_count": figures.tile_count,
        "last_tile": figures.tile_count - 1,
        "crom_payload": figures.crom_payload,
        "crom_size": figures.crom_size,
        "vrom_size": rom_image_size(voice[0].stat().st_size) if voice else 0,
        "free_tiles": (figures.crom_size - figures.crom_payload) // crom.TILE_BYTES_PER_ROM,
        "palette_base": figures.palette_base,
        "first_sprite": figures.first_sprite,
        "last_sprite": figures.first_sprite + stream_mod.GRID_COLS - 1,
        "frames": figures.frames,
        "audio": "yes" if voice else "no",
    }


def write_bundle(
    *,
    target: Path,
    build_dir: Path,
    figures: MovieFigures,
    library_root: Path = LIBRARY_ROOT,
) -> BundleLayout:
    root = Path(target)
    library, movie = _make_dirs(root)
    _copy_all(LIBRARY_SOURCES, Path(library_root), library, required=True)
    audio_sources = _copy_all(AUDIO_SOURCES, Path(library_root), library, required=False)
    voice = _copy_movie_data(Path(build_dir), movie)
    _write_packagers(root)
    _copy_stream_banks(Path(build_dir) / "generated", movie, figures.stream_banks)
    fields = _fields(figures, voice)
    makefile = root / MAKEFILE_NAME
    makefile.write_text(_render(MAKEFILE_NAME, fields), encoding="utf-8")
    guide = root / GUIDE_NAME
    guide.write_text(_render("bundle_readme.md", fields), encoding="utf-8")
    return BundleLayout(
        root=root,
        library=library,
        movie=movie,
        makefile=makefile,
        guide=guide,
        stream_banks=figures.stream_banks,
        has_audio=bool(voice and audio_sources),
    )
