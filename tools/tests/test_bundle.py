from __future__ import annotations

import pytest

from neogeomedia import bundle


def _library(root):
    source = root / "src-fmv"
    source.mkdir(exist_ok=True)
    for name in (*bundle.LIBRARY_SOURCES, *bundle.AUDIO_SOURCES):
        (source / name).write_text(f"/* {name} */\n")
    return source


def _build(root, *, banks=1, audio=True):
    build = root / "build"
    generated = build / "generated"
    baked = build / "baked"
    generated.mkdir(parents=True, exist_ok=True)
    baked.mkdir(parents=True, exist_ok=True)
    for name in bundle.GENERATED_SOURCES:
        (generated / name).write_text(f"/* {name} */\n")
    for name in bundle.BAKED_ASSETS:
        (baked / name).write_bytes(b"\x00\x01")
    for bank in range(banks):
        (generated / f"fmv_stream__bank{bank}.S").write_text(f".globl fmv_stream_bank{bank}\n")
    if audio:
        (baked / "v2.bin").write_bytes(b"\x00")
        (generated / "audio_params.s").write_text(".equ x, 1\n")
    return build


def _write(root, **overrides):
    banks = overrides.pop("banks", 1)
    audio = overrides.pop("audio", True)
    figures = {
        "stream_banks": 1,
        "max_updates": 280,
        "tick_cycles": 17920,
        "tile_count": 33142,
        "crom_payload": 33142 * 64,
        "crom_size": 4194304,
        "palette_base": 16,
        "first_sprite": 1,
        "frames": 1775,
        "version": (1, 0),
    }
    build_dir = overrides.pop("build_dir", None) or _build(root, banks=banks, audio=audio)
    library_root = overrides.pop("library_root", None) or _library(root)
    return bundle.write_bundle(
        target=root / "out",
        build_dir=build_dir,
        figures=bundle.MovieFigures(**{**figures, **overrides}),
        library_root=library_root,
    )


def _fragment(root, **overrides):
    return _write(root, **overrides).makefile.read_text()


def _guide(root, **overrides):
    return _write(root, **overrides).guide.read_text()


def _script(root):
    layout = _write(root)
    return layout.root / bundle.PACKAGER_DIR_NAME / bundle.PACKAGER_SCRIPT


class TestLibrarySource:
    def test_it_carries_every_library_source(self, tmp_path):
        # Arrange
        names = bundle.LIBRARY_SOURCES

        # Act
        layout = _write(tmp_path)

        # Assert
        assert [name for name in names if not (layout.library / name).is_file()] == []

    def test_it_carries_the_reference_sound_driver(self, tmp_path):
        # Arrange
        driver = "sound.s"

        # Act
        layout = _write(tmp_path)

        # Assert
        assert (layout.library / driver).is_file()

    def test_a_missing_library_source_is_an_error(self, tmp_path):
        # Arrange
        library = _library(tmp_path)
        (library / "fmv.c").unlink()

        # Act
        with pytest.raises(FileNotFoundError) as raised:
            _write(tmp_path, library_root=library)

        # Assert
        assert "fmv.c" in str(raised.value)


class TestMovieData:
    def test_it_carries_the_generated_sources(self, tmp_path):
        # Arrange
        names = bundle.GENERATED_SOURCES

        # Act
        layout = _write(tmp_path)

        # Assert
        assert [name for name in names if not (layout.movie / name).is_file()] == []

    def test_it_carries_one_stub_per_stream_bank(self, tmp_path):
        # Arrange
        banks = 3

        # Act
        layout = _write(tmp_path, banks=banks, stream_banks=banks)

        # Assert
        assert len(sorted(layout.movie.glob(bundle.STREAM_BANK_GLOB))) == banks

    def test_it_carries_every_baked_asset(self, tmp_path):
        # Arrange
        names = bundle.BAKED_ASSETS

        # Act
        layout = _write(tmp_path)

        # Assert
        assert [name for name in names if not (layout.movie / name).is_file()] == []

    def test_a_silent_bake_leaves_the_voice_rom_out(self, tmp_path):
        # Arrange
        audio = False

        # Act
        layout = _write(tmp_path, audio=audio)

        # Assert
        assert not (layout.movie / "v2.bin").exists()
        assert layout.has_audio is False

    def test_a_bake_with_sound_carries_the_voice_rom(self, tmp_path):
        # Arrange
        audio = True

        # Act
        layout = _write(tmp_path, audio=audio)

        # Assert
        assert (layout.movie / "v2.bin").is_file()
        assert layout.has_audio is True

    def test_a_missing_asset_is_an_error(self, tmp_path):
        # Arrange
        build = _build(tmp_path)
        (build / "baked" / "index.bin").unlink()

        # Act
        with pytest.raises(FileNotFoundError) as raised:
            _write(tmp_path, build_dir=build)

        # Assert
        assert "index.bin" in str(raised.value)

    def test_a_bank_count_that_disagrees_with_the_bake_is_an_error(self, tmp_path):
        # Arrange
        emitted, reported = 1, 2

        # Act
        with pytest.raises(ValueError) as raised:
            _write(tmp_path, banks=emitted, stream_banks=reported)

        # Assert
        assert "stream bank" in str(raised.value)


class TestMakeFragment:
    def test_it_writes_a_make_fragment(self, tmp_path):
        # Arrange
        name = "fmv.mk"

        # Act
        layout = _write(tmp_path)

        # Assert
        assert layout.makefile.is_file()
        assert layout.makefile.name == name

    def test_the_fragment_accounts_for_every_bank(self, tmp_path):
        # Arrange
        banks = 2

        # Act
        text = _fragment(tmp_path, banks=banks, stream_banks=banks)

        # Assert
        assert "FMV_BANK_NUMBERS = 0 1" in text
        assert "FMV_STREAM_BANKS = 2" in text

    @pytest.mark.parametrize(
        "line",
        [
            "fmv_stream__bank$(bank).o",
            "fmv_stream__bank%.S",
            "$(M68KGCC) $(NGCFLAGS) $(CFLAGS)",
            "SRCDIRS += $(FMV_SRC) $(FMV_MOVIE)",
            "-DFMV_NO_AUDIO",
            "fmv_audio.o",
            "fmv_stream_base",
            "FMV_FIRST_BANK ?=",
            "FMV_CROM_BYTES = 4194304",
            "FMV_FIRST_FREE_TILE = 33142",
            f"FMV_FREE_TILES = {(4194304 - 33142 * 64) // 64}",
            f"FMV_VROM_BYTES = {1 << 20}",
            "FMV_TOTAL_BANKS = $(shell expr $(FMV_FIRST_BANK) + $(FMV_STREAM_BANKS))",
            "FMV_PROM2_BYTES = $(shell expr $(FMV_TOTAL_BANKS) \\* 1048576)",
        ],
    )
    def test_the_fragment_carries_each_rule_a_project_needs(self, tmp_path, line):
        # Arrange
        expected = line

        # Act
        text = _fragment(tmp_path)

        # Assert
        assert expected in text

    def test_a_silent_bake_asks_for_no_voice_rom(self, tmp_path):
        # Arrange
        audio = False

        # Act
        text = _fragment(tmp_path, audio=audio)

        # Assert
        assert "FMV_VROM_BYTES = 0" in text

    def test_a_dictionary_that_fills_the_rom_leaves_no_slack(self, tmp_path):
        # Arrange
        full = 4194304

        # Act
        text = _fragment(tmp_path, crom_payload=full, crom_size=full)

        # Assert
        assert "FMV_FREE_TILES = 0" in text

    def test_the_fragment_reserves_the_banks_the_caller_owns(self, tmp_path):
        # Arrange
        rule = "$(foreach bank,$(FMV_ALL_BANK_NUMBERS),$(eval $(PROM2): $(PROM2)_bank$(bank)))"

        # Act
        text = _fragment(tmp_path, banks=2, stream_banks=2)

        # Assert
        assert "FMV_ALL_BANK_NUMBERS" in text
        assert rule in text


class TestThePackagers:
    def test_it_carries_a_packager_that_can_express_adpcm_b(self, tmp_path):
        # Arrange
        names = bundle.PACKAGERS

        # Act
        layout = _write(tmp_path)

        # Assert
        folder = layout.root / bundle.PACKAGER_DIR_NAME
        assert [name for name in names if not (folder / name).is_file()] == []

    def test_it_carries_the_script_that_drives_them(self, tmp_path):
        # Arrange
        executable = 0o111

        # Act
        script = _script(tmp_path)

        # Assert
        assert script.is_file()
        assert script.stat().st_mode & executable

    def test_the_script_joins_both_program_roms(self, tmp_path):
        # Arrange
        lines = ("$ROM_DIR/$GAME-p2.p2", '>> "$STAGE/p1.p1"')

        # Act
        text = _script(tmp_path).read_text()

        # Assert
        assert all(line in text for line in lines)

    def test_the_script_finds_the_movie_beside_it(self, tmp_path):
        # Arrange
        expected = f'MOVIE="$HERE/../{bundle.MOVIE_DIR_NAME}"'

        # Act
        text = _script(tmp_path).read_text()

        # Assert
        assert expected in text


class TestRomImageSizes:
    @pytest.mark.parametrize(
        ("payload", "size"),
        [(1, 1 << 20), (833536, 1 << 20), ((1 << 20) + 1, 1 << 21), (1 << 22, 1 << 22)],
    )
    def test_a_payload_takes_the_next_power_of_two_from_a_megabyte(self, payload, size):
        # Arrange
        expected = size

        # Act
        image = bundle.rom_image_size(payload)

        # Assert
        assert image == expected


class TestGuide:
    @pytest.mark.parametrize(
        "phrase",
        [
            "ymsnd:adpcmb",
            "package.sh",
            "$(CROM1): $(FMV_MOVIE)/c1.bin $(BUILDDIR)/assets/my-tiles.c1",
            "CROMSIZE = $(FMV_CROM_BYTES)",
            "fmv_defaults",
            "fmv_play",
            "fmv_open",
            "fmv_close",
            "1.0",
            "280",
            "16",
        ],
    )
    def test_the_guide_states_what_a_caller_needs(self, tmp_path, phrase):
        # Arrange
        expected = phrase

        # Act
        text = _guide(tmp_path)

        # Assert
        assert expected in text

    def test_it_writes_an_integration_guide(self, tmp_path):
        # Arrange
        name = bundle.GUIDE_NAME

        # Act
        layout = _write(tmp_path)

        # Assert
        assert layout.guide.is_file()
        assert layout.guide.name == name

    def test_the_guide_states_which_tiles_the_movie_owns(self, tmp_path):
        # Arrange
        spellings = ("33142", "33,142")

        # Act
        text = _guide(tmp_path)

        # Assert
        assert any(spelling in text for spelling in spellings)
