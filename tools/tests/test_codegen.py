from __future__ import annotations

from importlib.metadata import version

from neogeomedia import bundle, codegen, fixtiles, stream


class TestVersionStamp:
    def test_the_baker_version_is_the_installed_one(self):
        # Arrange
        major, minor = version("neogeomedia").split(".")[:2]

        # Act
        stamped = codegen.baker_version()

        # Assert
        assert stamped == (int(major), int(minor))

    def test_the_baker_version_is_a_pair_of_numbers(self):
        # Arrange
        expected_types = (int, int)

        # Act
        major, minor = codegen.baker_version()

        # Assert
        assert (type(major), type(minor)) == expected_types

    def test_the_library_header_carries_the_same_version_as_the_package(self):
        # Arrange
        header = (bundle.LIBRARY_ROOT / "fmv.h").read_text()

        # Act
        stated = {
            name: int(header.split(f"#define FMV_VERSION_{name} ")[1].split("\n")[0])
            for name in ("MAJOR", "MINOR")
        }

        # Assert
        assert (stated["MAJOR"], stated["MINOR"]) == codegen.baker_version()


class TestBlankingBudget:
    def test_the_blanking_budget_is_39_of_the_40_blank_lines(self):
        # Arrange
        cycles_per_line = 384 * 12_000_000 // 6_000_000

        # Act
        budget = codegen.VBLANK_CYCLES

        # Assert
        assert budget == 39 * cycles_per_line == 29_952


class TestFixDefines:
    def test_every_overlay_glyph_is_named_by_its_tile_number(self):
        # Arrange
        expected = f"#define FIX_TILE_BAR_KNOB {fixtiles.GLYPHS['bar_knob']}"

        # Act
        text = codegen.fix_defines()

        # Assert
        assert expected in text.splitlines()

    def test_one_define_is_emitted_per_glyph_the_player_draws(self):
        # Arrange
        expected_count = 19

        # Act
        lines = codegen.fix_defines().splitlines()

        # Assert
        assert len(lines) == expected_count
        assert all(line.startswith("#define FIX_TILE_") for line in lines)


class TestStreamBanks:
    def test_each_stub_starts_where_the_one_before_it_ended(self, tmp_path):
        # Arrange
        banks = 5

        # Act
        stubs = codegen.write_stream_banks(tmp_path, tmp_path / "stream.bin", banks)

        # Assert
        skips = [int(stub.read_text().split(",")[1]) for stub in stubs]
        assert skips == [bank * stream.PROM_BANK_BYTES for bank in range(banks)]

    def test_the_slices_cover_the_blob_without_a_gap_or_an_overlap(self, tmp_path):
        # Arrange
        banks = 3

        # Act
        stubs = codegen.write_stream_banks(tmp_path, tmp_path / "stream.bin", banks)

        # Assert
        spans = [tuple(int(part) for part in stub.read_text().split(",")[1:]) for stub in stubs]
        assert spans == [
            (0, stream.PROM_BANK_BYTES),
            (stream.PROM_BANK_BYTES, stream.PROM_BANK_BYTES),
            (2 * stream.PROM_BANK_BYTES, stream.PROM_BANK_BYTES),
        ]

    def test_a_stub_names_the_blob_without_a_path(self, tmp_path):
        # Arrange
        blob = tmp_path / "deep" / "stream.bin"

        # Act
        stubs = codegen.write_stream_banks(tmp_path, blob, 1)

        # Assert
        assert '.incbin "stream.bin"' in stubs[0].read_text()
        assert "deep" not in stubs[0].read_text()

    def test_a_stub_lands_in_read_only_data(self, tmp_path):
        # Arrange
        blob = tmp_path / "stream.bin"

        # Act
        stubs = codegen.write_stream_banks(tmp_path, blob, 1)

        # Assert
        assert ".section .rodata" in stubs[0].read_text()
