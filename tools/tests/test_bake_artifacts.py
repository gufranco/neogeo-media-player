from __future__ import annotations

from neogeomedia import codegen, crom, stream
from tests.bakehelp import baked_size, generated


class TestCharacterRom:
    def test_it_writes_both_c_rom_halves(self, baked):
        # Arrange
        folder = baked.build_dir / "baked"

        # Act
        present = [(folder / name).is_file() for name in ("c1.bin", "c2.bin")]

        # Assert
        assert present == [True, True]

    def test_the_c_rom_halves_are_the_same_size(self, baked):
        # Arrange
        first = baked_size(baked, "c1.bin")

        # Act
        second = baked_size(baked, "c2.bin")

        # Assert
        assert first == second

    def test_the_dictionary_is_written_at_its_own_length(self, baked):
        # Arrange
        expected = baked.result.stats.tile_count * crom.TILE_BYTES_PER_ROM

        # Act
        size = baked_size(baked, "c1.bin")

        # Assert
        assert size == expected

    def test_it_carries_no_padding_a_caller_would_have_to_skip(self, baked):
        # Arrange
        tiles = baked.result.stats.tile_count

        # Act
        size = baked_size(baked, "c1.bin")

        # Assert
        assert divmod(size, crom.TILE_BYTES_PER_ROM) == (tiles, 0)

    def test_the_cartridge_size_it_reports_is_a_power_of_two(self, baked):
        # Arrange
        written = baked_size(baked, "c1.bin")

        # Act
        size = crom.rom_size_for(baked.result.stats.tile_count)

        # Assert
        assert size & (size - 1) == 0
        assert size >= written


class TestStreamBlobs:
    def test_it_writes_the_command_stream(self, baked):
        # Arrange
        expected = baked.result.stats.stream_rom_bytes

        # Act
        size = baked_size(baked, "stream.bin")

        # Assert
        assert size == expected

    def test_it_writes_one_index_entry_per_frame(self, baked):
        # Arrange
        expected = 4 * baked.result.stats.frames

        # Act
        size = baked_size(baked, "index.bin")

        # Assert
        assert size == expected

    def test_it_writes_the_palette_blob(self, baked):
        # Arrange
        expected = 8 * 32

        # Act
        size = baked_size(baked, "palettes.bin")

        # Assert
        assert size == expected

    def test_every_blob_is_word_aligned(self, baked):
        # Arrange
        names = ("stream.bin", "index.bin", "keyframes.bin", "palettes.bin")

        # Act
        sizes = {name: baked_size(baked, name) for name in names}

        # Assert
        assert {name: size % 2 for name, size in sizes.items()} == dict.fromkeys(names, 0)

    def test_the_stream_blob_is_a_whole_number_of_banks(self, baked):
        # Arrange
        bank = stream.PROM_BANK_BYTES

        # Act
        size = baked_size(baked, "stream.bin")

        # Assert
        assert size % bank == 0


class TestAssemblyStub:
    def test_it_links_the_small_blobs(self, baked):
        # Arrange
        names = ("index.bin", "keyframes.bin", "palettes.bin")

        # Act
        text = generated(baked, "movie_data.S")

        # Assert
        assert all(name in text for name in names)

    def test_the_stub_names_blobs_without_a_path(self, baked):
        # Arrange
        folder = str(baked.build_dir)

        # Act
        text = generated(baked, "movie_data.S")

        # Assert
        assert '.incbin "index.bin"' in text
        assert folder not in text
        assert "/" not in text.split(".incbin")[1].split("\n")[0]

    def test_the_stream_is_not_linked_into_the_image(self, baked):
        # Arrange
        name = "stream.bin"

        # Act
        text = generated(baked, "movie_data.S")

        # Assert
        assert name not in text

    def test_the_assembly_stub_exports_the_player_symbols(self, baked):
        # Arrange
        symbols = ("movie_index", "movie_keyframes", "movie_palettes")

        # Act
        text = generated(baked, "movie_data.S")

        # Assert
        assert all(f".globl {symbol}" in text for symbol in symbols)


class TestStreamBankStubs:
    def test_it_emits_one_stub_per_switchable_bank(self, baked):
        # Arrange
        expected = baked.result.stream.bank_count()

        # Act
        stubs = sorted((baked.build_dir / "generated").glob("fmv_stream__bank*.S"))

        # Assert
        assert len(stubs) == expected

    def test_a_stub_exports_the_symbol_the_linker_places(self, baked):
        # Arrange
        expected = ".globl fmv_stream_bank0"

        # Act
        text = generated(baked, "fmv_stream__bank0.S")

        # Assert
        assert expected in text

    def test_a_stub_takes_its_slice_from_the_stream_blob(self, baked):
        # Arrange
        expected = f'.incbin "stream.bin", 0, {stream.PROM_BANK_BYTES}'

        # Act
        text = generated(baked, "fmv_stream__bank0.S")

        # Assert
        assert expected in text

    def test_the_stream_base_comes_from_a_linker_symbol(self, baked):
        # Arrange
        symbol = codegen.STREAM_BASE_SYMBOL

        # Act
        text = generated(baked, "movie_data_value.c")

        # Assert
        assert f"extern const unsigned char {symbol}[];" in text
        assert f".stream_base = (uint32_t){symbol}," in text
