from __future__ import annotations

import pytest

from neogeomedia import integrate

STOCK_ROM_MK = """PROMSIZE=1048576
PROM1=$(ROM)/$(GAMEROM)-p1.p1
# PROM2=$(ROM)/$(GAMEROM)-p2.p2
CROMSIZE=2097152
SROMSIZE=131072
"""

STOCK_MAKEFILE = """GAMEROM=ngdevkit
include rom.mk

include build.mk

include emu.mk

ELF=$(BUILDDIR)/rom.elf
$(ELF):	$(BUILDDIR)/main.o
$(PROM1): $(ELF)

$(SROM1): $(BUILDDIR)/assets/base-srom-text-shadow.fix

$(CROM1): $(BUILDDIR)/assets/base-crom-logo.c1
$(CROM2): $(BUILDDIR)/assets/base-crom-logo.c2

SOUND_DRIVER=$(BUILDDIR)/assets/base-sound-driver.ihx
$(MROM1): $(SOUND_DRIVER)
"""

STOCK_SPRITE_LINES = (
    "$(CROM1): $(BUILDDIR)/assets/base-crom-logo.c1\n$(CROM2): $(BUILDDIR)/assets/base-crom-logo.c2"
)


def project_at(root):
    (root / "rom.mk").write_text(STOCK_ROM_MK)
    (root / "Makefile").write_text(STOCK_MAKEFILE)
    return root


class TestCartridgeDeclaration:
    def test_it_declares_the_second_program_rom(self):
        # Arrange
        stock = STOCK_ROM_MK

        # Act
        text = integrate.cartridge_edits(stock)

        # Assert
        assert "PROM2=$(ROM)/$(GAMEROM)-p2.p2" in text
        assert "# PROM2=" not in text

    def test_it_sizes_the_sprite_rom_from_the_fragment(self):
        # Arrange
        stock = STOCK_ROM_MK

        # Act
        text = integrate.cartridge_edits(stock)

        # Assert
        assert "CROMSIZE=$(FMV_CROM_BYTES)" in text

    def test_it_leaves_the_rest_of_the_declaration_alone(self):
        # Arrange
        stock = STOCK_ROM_MK

        # Act
        text = integrate.cartridge_edits(stock)

        # Assert
        assert "PROMSIZE=1048576" in text
        assert "SROMSIZE=131072" in text

    def test_a_declaration_the_guide_does_not_recognise_is_an_error(self):
        # Arrange
        unknown = "PROMSIZE=1048576\n"

        # Act
        with pytest.raises(SystemExit) as raised:
            integrate.cartridge_edits(unknown)

        # Assert
        assert raised.value.code == "the stock rom.mk no longer looks the way the guide describes"


class TestMakefile:
    def test_the_fragment_sits_between_the_declaration_and_the_build_rules(self):
        # Arrange
        stock = STOCK_MAKEFILE

        # Act
        text = integrate.makefile_edits(stock)

        # Assert
        assert text.index("include rom.mk") < text.index("include fmv/fmv.mk")
        assert text.index("include fmv/fmv.mk") < text.index("include build.mk")

    def test_it_names_the_projects_own_objects_before_the_include(self):
        # Arrange
        stock = STOCK_MAKEFILE

        # Act
        text = integrate.makefile_edits(stock)

        # Assert
        assert text.index("FMV_GAME_OBJS") < text.index("include fmv/fmv.mk")

    def test_it_sizes_the_second_program_rom_from_the_fragment(self):
        # Arrange
        stock = STOCK_MAKEFILE

        # Act
        text = integrate.makefile_edits(stock)

        # Assert
        assert "PROM2SIZE = $(FMV_PROM2_BYTES)" in text

    def test_it_points_the_cartridge_at_the_movies_rom_images(self):
        # Arrange
        wanted = {
            "$(CROM1): $(FMV_MOVIE)/c1.bin",
            "$(CROM2): $(FMV_MOVIE)/c2.bin",
            "$(SROM1): $(FMV_MOVIE)/fix.s1",
        }

        # Act
        text = integrate.makefile_edits(STOCK_MAKEFILE)

        # Assert
        assert wanted <= set(text.splitlines())

    def test_it_builds_the_program_rom_from_the_first_bank_elf(self):
        # Arrange
        stock = STOCK_MAKEFILE

        # Act
        text = integrate.makefile_edits(stock)

        # Assert
        assert "$(PROM1): $(BUILDDIR)/rom-fmv-bank0.elf" in text

    def test_a_silent_build_asks_for_video_only_and_ngdevkit_s_empty_driver(self):
        # Arrange
        stock = STOCK_MAKEFILE

        # Act
        text = integrate.makefile_edits(stock)

        # Assert
        assert "FMV_AUDIO = no" in text
        assert "SOUND_DRIVER=$(NGSHAREDIR)/nullsound_driver.ihx" in text

    def test_a_makefile_without_the_build_rules_is_an_error(self):
        # Arrange
        stripped = "include rom.mk\n"

        # Act
        with pytest.raises(SystemExit) as raised:
            integrate.makefile_edits(stripped)

        # Assert
        assert raised.value.code == "the stock Makefile no longer carries 'include build.mk'"

    def test_the_stock_program_rom_wiring_is_replaced_not_added_to(self):
        # Arrange
        stock = STOCK_MAKEFILE

        # Act
        text = integrate.makefile_edits(stock)

        # Assert
        assert "$(PROM1): $(ELF)" not in text
        assert "ELF=$(BUILDDIR)/rom.elf" not in text

    def test_the_demo_assets_stop_being_prerequisites(self):
        # Arrange
        stock = STOCK_MAKEFILE

        # Act
        text = integrate.makefile_edits(stock)

        # Assert
        assert "base-crom-logo" not in text
        assert "base-srom-text-shadow" not in text

    def test_a_build_with_sound_takes_the_movie_s_driver_not_romtool(self):
        # Arrange
        stock = STOCK_MAKEFILE

        # Act
        text = integrate.makefile_edits(stock, audio=True)

        # Assert
        assert "SOUND_DRIVER=$(FMV_SOUND_DRIVER)" in text
        assert "FMV_AUDIO = yes" in text
        assert "$(VROM1): $(FMV_MOVIE)/v2.bin" not in text

    def test_a_makefile_missing_the_stock_asset_lines_is_an_error(self):
        # Arrange
        stripped = STOCK_MAKEFILE.replace(STOCK_SPRITE_LINES, "")

        # Act
        with pytest.raises(SystemExit) as raised:
            integrate.makefile_edits(stripped)

        # Assert
        assert raised.value.code == (
            "the stock Makefile no longer carries '$(CROM1): $(BUILDDIR)/assets/base-crom-logo.c1"
            "\\n$(CROM2): $(BUILDDIR)/assets/base-crom-logo.c2'"
        )

    def test_it_edits_nothing_the_baker_emitted(self):
        # Arrange
        stock = STOCK_MAKEFILE

        # Act
        text = integrate.makefile_edits(stock)

        # Assert
        assert "fmv/movie/" not in text
        assert "fmv/src/" not in text


class TestApplyingToAProject:
    def test_it_rewrites_both_editable_files(self, tmp_path):
        # Arrange
        project = project_at(tmp_path)

        # Act
        integrate.apply(project)

        # Assert
        assert "CROMSIZE=$(FMV_CROM_BYTES)" in (project / "rom.mk").read_text()
        assert "include fmv/fmv.mk" in (project / "Makefile").read_text()

    def test_it_leaves_every_other_file_alone(self, tmp_path):
        # Arrange
        project = project_at(tmp_path)
        (project / "build.mk").write_text("untouched\n")

        # Act
        integrate.apply(project)

        # Assert
        assert (project / "build.mk").read_text() == "untouched\n"

    def test_the_command_line_applies_the_same_edits(self, tmp_path):
        # Arrange
        project = project_at(tmp_path)

        # Act
        code = integrate.main([str(project)])

        # Assert
        assert code == 0
        assert "PROM2SIZE = $(FMV_PROM2_BYTES)" in (project / "Makefile").read_text()

    def test_the_command_line_wires_sound_when_asked(self, tmp_path):
        # Arrange
        project = project_at(tmp_path)

        # Act
        code = integrate.main([str(project), "--audio"])

        # Assert
        assert code == 0
        assert "FMV_AUDIO = yes" in (project / "Makefile").read_text()
