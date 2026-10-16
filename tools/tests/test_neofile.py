from __future__ import annotations

import struct

import pytest
from fmvcore.testing import seeded

from neogeomedia import neofile

HEADER_BYTES = 4096
fake = seeded()


def write_regions(directory, *, p=b"", s=b"", m=b"", v1=b"", v2=None, c1=b"", c2=b""):
    (directory / "p1.p1").write_bytes(p)
    (directory / "s1.s1").write_bytes(s)
    (directory / "m1.m1").write_bytes(m)
    (directory / "v11.v1").write_bytes(v1)
    if v2 is not None:
        (directory / "v21.v2").write_bytes(v2)
    (directory / "c1.c1").write_bytes(c1)
    (directory / "c2.c2").write_bytes(c2)
    return directory


def read_header(path):
    data = path.read_bytes()[:HEADER_BYTES]
    sizes = struct.unpack_from("<6I", data, 4)
    year, genre, screenshot, ngh = struct.unpack_from("<4I", data, 28)
    return {
        "tag": data[:4],
        "psz": sizes[0],
        "ssz": sizes[1],
        "msz": sizes[2],
        "v1sz": sizes[3],
        "v2sz": sizes[4],
        "csz": sizes[5],
        "year": year,
        "genre": genre,
        "screenshot": screenshot,
        "ngh": ngh,
        "name": data[44:77].rstrip(b"\x00").decode(),
        "manufacturer": data[77:94].rstrip(b"\x00").decode(),
    }


def sample_regions():
    return {
        "p": fake.binary(length=64),
        "s": fake.binary(length=32),
        "m": fake.binary(length=16),
        "v1": fake.binary(length=8),
        "c1": fake.binary(length=4),
        "c2": fake.binary(length=4),
    }


def metadata():
    return {
        "name": fake.pystr(min_chars=1, max_chars=32),
        "manufacturer": fake.pystr(min_chars=1, max_chars=16),
        "year": fake.random_int(1990, 2099),
        "ngh": fake.random_int(0, 0xFFFF),
    }


@pytest.fixture
def regions():
    return sample_regions()


@pytest.fixture
def rom_dir(tmp_path, regions):
    directory = tmp_path / "rom"
    directory.mkdir()
    return write_regions(directory, **regions)


class TestHeader:
    def test_the_magic_identifies_a_neo_container(self, rom_dir, tmp_path):
        # Arrange
        output = tmp_path / "cart.neo"

        # Act
        out = neofile.write_neo(rom_dir=rom_dir, output=output)

        # Assert
        assert read_header(out)["tag"] == b"NEO\x01"

    def test_the_region_sizes_match_the_inputs(self, rom_dir, tmp_path):
        # Arrange
        output = tmp_path / "cart.neo"

        # Act
        out = neofile.write_neo(rom_dir=rom_dir, output=output)

        # Assert
        header = read_header(out)
        sizes = (header["psz"], header["ssz"], header["msz"], header["v1sz"], header["v2sz"])
        assert sizes == (64, 32, 16, 8, 0)

    def test_the_character_region_is_both_halves_together(self, rom_dir, tmp_path):
        # Arrange
        output = tmp_path / "cart.neo"

        # Act
        out = neofile.write_neo(rom_dir=rom_dir, output=output)

        # Assert
        assert read_header(out)["csz"] == 8

    def test_metadata_round_trips(self, rom_dir, tmp_path):
        # Arrange
        given = metadata()

        # Act
        out = neofile.write_neo(rom_dir=rom_dir, output=tmp_path / "cart.neo", **given)

        # Assert
        header = read_header(out)
        assert {key: header[key] for key in given} == given

    def test_the_header_occupies_exactly_four_kibibytes(self, rom_dir, tmp_path):
        # Arrange
        output = tmp_path / "cart.neo"

        # Act
        out = neofile.write_neo(rom_dir=rom_dir, output=output)

        # Assert
        assert out.stat().st_size == HEADER_BYTES + 64 + 32 + 16 + 8 + 8


class TestPayload:
    def test_regions_follow_the_documented_order(self, rom_dir, regions, tmp_path):
        # Arrange
        output = tmp_path / "cart.neo"

        # Act
        out = neofile.write_neo(rom_dir=rom_dir, output=output)

        # Assert
        payload = out.read_bytes()[HEADER_BYTES : HEADER_BYTES + 120]
        assert payload == regions["p"] + regions["s"] + regions["m"] + regions["v1"]

    def test_the_character_region_interleaves_the_two_halves(self, tmp_path):
        # Arrange
        rom = write_regions(tmp_path, c1=bytes([0x11, 0x22, 0x33, 0x44]), c2=b"\xaa\xbb\xcc\xdd")

        # Act
        out = neofile.write_neo(rom_dir=rom, output=tmp_path / "cart.neo")

        # Assert
        assert out.read_bytes()[HEADER_BYTES:] == bytes(
            [0x11, 0xAA, 0x22, 0xBB, 0x33, 0xCC, 0x44, 0xDD]
        )


class TestValidation:
    def test_mismatched_character_halves_are_rejected(self, tmp_path):
        # Arrange
        rom = write_regions(tmp_path, c1=fake.binary(length=3), c2=fake.binary(length=2))

        # Act
        with pytest.raises(ValueError, match="same size") as refused:
            neofile.write_neo(rom_dir=rom, output=tmp_path / "x.neo")

        # Assert
        assert str(refused.value) == "character halves must be the same size, got 3 and 2"

    def test_a_missing_region_file_is_rejected(self, tmp_path):
        # Arrange
        (tmp_path / "p1.p1").write_bytes(fake.binary(length=1))

        # Act
        with pytest.raises(FileNotFoundError, match=r"s1\.s1") as refused:
            neofile.write_neo(rom_dir=tmp_path, output=tmp_path / "x.neo")

        # Assert
        assert str(refused.value) == f"missing cart region s1.s1 in {tmp_path}"

    @pytest.mark.parametrize(
        ("field", "limit"),
        [("name", 33), ("manufacturer", 17)],
    )
    def test_an_overlong_text_field_is_rejected(self, tmp_path, field, limit):
        # Arrange
        rom = write_regions(tmp_path, c1=fake.binary(length=1), c2=fake.binary(length=1))
        text = fake.pystr(min_chars=limit, max_chars=limit + 8)

        # Act
        with pytest.raises(ValueError, match=field) as refused:
            neofile.write_neo(rom_dir=rom, output=tmp_path / "x.neo", **{field: text})

        # Assert
        assert str(refused.value).startswith(f"{field} must be shorter than {limit} bytes")


class TestStreaming:
    def test_a_large_character_region_is_written_without_holding_it_all(self, tmp_path):
        # Arrange
        half = bytes(256) * 4096
        rom = write_regions(tmp_path, c1=half, c2=half)

        # Act
        out = neofile.write_neo(rom_dir=rom, output=tmp_path / "big.neo", chunk_bytes=4096)

        # Assert
        assert read_header(out)["csz"] == 2 * 1024 * 1024

    def test_chunked_interleaving_matches_a_direct_interleave(self, tmp_path):
        # Arrange
        c1 = fake.binary(length=2048)
        c2 = fake.binary(length=2048)
        rom = write_regions(tmp_path, c1=c1, c2=c2)

        # Act
        out = neofile.write_neo(rom_dir=rom, output=tmp_path / "chunked.neo", chunk_bytes=7)

        # Assert
        written = out.read_bytes()[HEADER_BYTES:]
        assert (written[0::2], written[1::2]) == (c1, c2)


class TestSecondVoiceRegion:
    def test_the_second_voice_region_is_declared_when_present(self, tmp_path):
        # Arrange
        rom = write_regions(tmp_path, v1=b"\x01\x02", v2=b"\x0a\x0b\x0c", c1=b"\x01", c2=b"\x02")

        # Act
        out = neofile.write_neo(rom_dir=rom, output=tmp_path / "voice.neo")

        # Assert
        assert read_header(out)["v2sz"] == 3

    def test_the_second_voice_region_follows_the_first(self, tmp_path):
        # Arrange
        rom = write_regions(tmp_path, v1=b"\x01\x02", v2=b"\x0a\x0b\x0c", c1=b"\x01", c2=b"\x02")

        # Act
        out = neofile.write_neo(rom_dir=rom, output=tmp_path / "voice.neo")

        # Assert
        assert out.read_bytes()[HEADER_BYTES : HEADER_BYTES + 5] == b"\x01\x02\x0a\x0b\x0c"

    def test_the_character_region_still_follows_both_voices(self, tmp_path):
        # Arrange
        rom = write_regions(tmp_path, v1=b"\x01", v2=b"\x0a", c1=b"\xf0", c2=b"\x0f")

        # Act
        out = neofile.write_neo(rom_dir=rom, output=tmp_path / "voice.neo")

        # Assert
        assert out.read_bytes()[HEADER_BYTES:] == b"\x01\x0a\xf0\x0f"


class TestTheCommandLine:
    def test_it_writes_the_container_the_build_script_asks_for(self, rom_dir, tmp_path, capsys):
        # Arrange
        output = tmp_path / "out" / "cart.neo"

        # Act
        code = neofile.main(["--rom-dir", str(rom_dir), "--output", str(output)])

        # Assert
        assert code == 0
        assert read_header(output)["tag"] == b"NEO\x01"
        assert f"wrote {output} ({HEADER_BYTES + 128} bytes)" in capsys.readouterr().out

    def test_the_name_reaches_the_header(self, rom_dir, tmp_path):
        # Arrange
        output = tmp_path / "cart.neo"
        name = fake.pystr(min_chars=1, max_chars=32)

        # Act
        neofile.main(["--rom-dir", str(rom_dir), "--output", str(output), "--name", name])

        # Assert
        assert read_header(output)["name"] == name

    def test_the_ngh_accepts_hexadecimal(self, rom_dir, tmp_path):
        # Arrange
        output = tmp_path / "cart.neo"

        # Act
        code = neofile.main(["--rom-dir", str(rom_dir), "--output", str(output), "--ngh", "0x1234"])

        # Assert
        assert code == 0
        assert read_header(output)["ngh"] == 4660

    def test_a_missing_region_stops_it_rather_than_writing_half_a_cart(self, tmp_path):
        # Arrange
        empty = tmp_path / "empty"
        empty.mkdir()
        output = tmp_path / "cart.neo"

        # Act
        with pytest.raises(FileNotFoundError) as refused:
            neofile.main(["--rom-dir", str(empty), "--output", str(output)])

        # Assert
        assert str(refused.value) == f"missing cart region p1.p1 in {empty}"
        assert not output.exists()
