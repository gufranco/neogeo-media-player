from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pytest
from fmvcore.testing import SEED

from neogeomedia import mamecart

PROGRAM = bytes(range(256)) * 8
PROGRAM_SHA1 = "f10ccfde60c17db26e7d85d35665c7661dbbeb2c"
PROGRAM_CRC = "9f5edd58"
FILLER_SIZES = {
    "s1.s1": 64,
    "m1.m1": 32,
    "v11.v1": 16,
    "v21.v2": 48,
    "c1.c1": 128,
    "c2.c2": 128,
}


@pytest.fixture
def rom_dir(tmp_path):
    rng = np.random.default_rng(SEED)
    (tmp_path / "p1.p1").write_bytes(PROGRAM)
    for name, size in FILLER_SIZES.items():
        (tmp_path / name).write_bytes(rng.integers(0, 256, size=size, dtype=np.uint8).tobytes())
    return tmp_path


def listing(result: mamecart.CartPackage) -> ElementTree.Element:
    return ElementTree.parse(result.software_list).getroot()


def area(root: ElementTree.Element, name: str) -> ElementTree.Element:
    return next(found for found in root.iter("dataarea") if found.get("name") == name)


def archived(path: Path) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(path) as archive:
        return archive.infolist()


class TestArchive:
    def test_it_writes_a_zip_of_the_rom_files(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        names = {info.filename for info in archived(out)}
        assert names == {"p1.p1", "s1.s1", "m1.m1", "v11.v1", "v21.v2", "c1.c1", "c2.c2"}

    def test_the_archive_stores_files_uncompressed_by_default(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        assert {info.compress_type for info in archived(out)} == {zipfile.ZIP_STORED}


class TestSoftwareList:
    def test_it_writes_a_software_list_named_neogeo(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        result = mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        assert result.software_list == tmp_path / "mame-hash" / "neogeo.xml"
        assert listing(result).get("name") == "neogeo"

    def test_the_part_uses_the_cart_interface(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        result = mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        assert listing(result).find("software/part").get("interface") == "neo_cart"

    def test_every_region_uses_the_name_mame_looks_for(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        result = mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        names = {found.get("name") for found in listing(result).iter("dataarea")}
        assert names == {"maincpu", "fixed", "audiocpu", "ymsnd:adpcma", "ymsnd:adpcmb", "sprites"}

    def test_the_program_rom_is_word_swapped_on_load(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        result = mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        assert area(listing(result), "maincpu").find("rom").get("loadflag") == "load16_word_swap"

    def test_the_character_halves_interleave_into_one_sprite_area(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        result = mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        sprites = area(listing(result), "sprites")
        assert [rom.get("loadflag") for rom in sprites.findall("rom")] == [
            "load16_byte",
            "load16_byte",
        ]
        assert sprites.get("size") == "256"

    def test_every_rom_carries_a_checksum(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        result = mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        roms = list(listing(result).iter("rom"))
        assert {len(rom.get("sha1")) for rom in roms} == {40}
        assert {len(rom.get("crc")) for rom in roms} == {8}

    def test_the_checksums_match_the_archived_files(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        result = mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        program = area(listing(result), "maincpu").find("rom")
        assert (program.get("sha1"), program.get("crc")) == (PROGRAM_SHA1, PROGRAM_CRC)

    def test_the_voice_region_is_omitted_when_absent(self, rom_dir, tmp_path):
        # Arrange
        (rom_dir / "v21.v2").unlink()

        # Act
        result = mamecart.write_cart(rom_dir=rom_dir, output=tmp_path / "cart.zip")

        # Assert
        names = {found.get("name") for found in listing(result).iter("dataarea")}
        assert "ymsnd:adpcmb" not in names
        assert "v21.v2" not in {info.filename for info in archived(result.archive)}


class TestValidation:
    def test_a_missing_region_is_rejected(self, tmp_path):
        # Arrange
        (tmp_path / "p1.p1").write_bytes(PROGRAM)

        # Act
        with pytest.raises(FileNotFoundError) as raised:
            mamecart.write_cart(rom_dir=tmp_path, output=tmp_path / "x.zip")

        # Assert
        assert str(raised.value) == f"missing cart region s1.s1 in {tmp_path}"

    def test_a_program_rom_beyond_the_bank_register_is_rejected(self, tmp_path, rom_dir):
        # Arrange
        (rom_dir / "p1.p1").write_bytes(bytes(10 << 20))

        # Act
        with pytest.raises(ValueError) as raised:
            mamecart.write_cart(rom_dir=rom_dir, output=tmp_path / "x.zip")

        # Assert
        assert str(raised.value) == (
            "program ROM is 10485760 bytes, beyond the 9437184 the three-bit "
            "bank register can reach"
        )


class TestRomOffsets:
    def test_the_character_halves_land_on_alternating_bytes(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        result = mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        sprites = area(listing(result), "sprites")
        assert [rom.get("offset") for rom in sprites.findall("rom")] == ["0x000000", "0x000001"]

    def test_single_rom_regions_start_at_zero(self, rom_dir, tmp_path):
        # Arrange
        out = tmp_path / "cart.zip"

        # Act
        result = mamecart.write_cart(rom_dir=rom_dir, output=out)

        # Assert
        offsets = {
            found.get("name"): found.find("rom").get("offset")
            for found in listing(result).iter("dataarea")
            if found.get("name") != "sprites"
        }
        assert offsets == dict.fromkeys(
            ("maincpu", "fixed", "audiocpu", "ymsnd:adpcma", "ymsnd:adpcmb"), "0x000000"
        )


class TestTheCommandLine:
    def test_it_writes_the_archive_and_names_both_outputs(self, rom_dir, tmp_path, capsys):
        # Arrange
        output = tmp_path / "out" / "cart.zip"

        # Act
        code = mamecart.main(["--rom-dir", str(rom_dir), "--output", str(output)])

        # Assert
        listed = tmp_path / "out" / "mame-hash" / "neogeo.xml"
        assert code == 0
        assert output.is_file()
        assert capsys.readouterr().out == f"wrote {output} and {listed}\n"

    def test_a_missing_region_stops_it_rather_than_writing_half_a_cart(self, tmp_path):
        # Arrange
        empty = tmp_path / "empty"
        empty.mkdir()
        output = tmp_path / "cart.zip"

        # Act
        with pytest.raises(FileNotFoundError) as raised:
            mamecart.main(["--rom-dir", str(empty), "--output", str(output)])

        # Assert
        assert str(raised.value) == f"missing cart region p1.p1 in {empty}"
        assert not output.exists()
