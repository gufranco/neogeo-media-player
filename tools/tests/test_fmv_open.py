from __future__ import annotations

import ctypes

import pytest

from tests.fmvhelp import (
    FIRST_SPRITE,
    FMV_FIX_CART,
    FMV_PAD_A,
    GRID_COLS,
    LSPC_DISABLE_AUTOANIM,
    PALETTE_BASE,
    PALETTE_WORDS,
    PLAYER_BYTES,
    SCB1_WORDS_PER_SPRITE,
    SCB3_GRID_HEAD,
    SCB3_GRID_STICKY,
    VRAM_SCB3,
    Movie,
    Options,
    build,
    movie_for,
    new_player,
    opened,
)

MOVED_FIRST_SPRITE = 8


@pytest.fixture(scope="session")
def fmv(tmp_path_factory):
    return build(tmp_path_factory, audio=True)


@pytest.fixture
def movie(fmv):
    return movie_for(fmv)


def scb3_words(fmv, first_sprite: int) -> list[int]:
    return [fmv.fmv_test_vram(VRAM_SCB3 + first_sprite + column) for column in range(GRID_COLS)]


class TestLayoutAgreement:
    def test_the_options_mirror_matches_the_compiled_struct(self, fmv):
        # Arrange
        mirrored = ctypes.sizeof(Options)

        # Act
        compiled = fmv.fmv_test_sizeof_options()

        # Assert
        assert compiled == mirrored

    def test_the_movie_mirror_matches_the_compiled_struct(self, fmv):
        # Arrange
        mirrored = ctypes.sizeof(Movie)

        # Act
        compiled = fmv.fmv_test_sizeof_movie()

        # Assert
        assert compiled == mirrored

    def test_the_skip_hook_sits_where_the_compiled_struct_puts_it(self, fmv):
        # Arrange
        mirrored = Options.skip.offset

        # Act
        compiled = fmv.fmv_test_offsetof_options_skip()

        # Assert
        assert compiled == mirrored

    def test_the_player_fits_the_buffer_the_tests_hand_it(self, fmv):
        # Arrange
        handed = PLAYER_BYTES

        # Act
        compiled = fmv.fmv_test_sizeof_player()

        # Assert
        assert compiled <= handed


class TestDefaults:
    def test_the_grid_starts_at_the_origin_on_the_first_drawn_sprite(self, fmv):
        # Arrange
        library = fmv

        # Act
        options = library.fmv_defaults()

        # Assert
        assert (options.first_sprite, options.top_line, options.left_pixel) == (1, 0, 0)

    def test_the_machine_it_hands_back_is_a_plain_cartridge(self, fmv):
        # Arrange
        library = fmv

        # Act
        options = library.fmv_defaults()

        # Assert
        assert options.lspc_mode == 0
        assert options.fix_source == FMV_FIX_CART
        assert options.palette_bank == 0
        assert options.prom_bank == 0

    def test_a_button_and_start_both_skip_by_default(self, fmv):
        # Arrange
        library = fmv

        # Act
        options = library.fmv_defaults()

        # Assert
        assert options.skip_pad == FMV_PAD_A
        assert options.skip_start == 1

    def test_no_skip_predicate_is_installed(self, fmv):
        # Arrange
        library = fmv

        # Act
        options = library.fmv_defaults()

        # Assert
        assert ctypes.cast(options.skip, ctypes.c_void_p).value is None


class TestOpening:
    def test_it_takes_the_fix_rom_and_palette_bank_it_needs(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        player = new_player()

        # Act
        fmv.fmv_open(player, ctypes.byref(movie), ctypes.byref(options))

        # Assert
        assert fmv.fmv_test_fix_source() == FMV_FIX_CART
        assert fmv.fmv_test_palette_bank() == 0

    def test_it_disables_auto_animation_while_it_owns_the_screen(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        player = new_player()

        # Act
        fmv.fmv_open(player, ctypes.byref(movie), ctypes.byref(options))

        # Assert
        assert fmv.fmv_test_lspc_mode() == LSPC_DISABLE_AUTOANIM

    def test_it_lays_out_one_sprite_per_column(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        player = new_player()

        # Act
        fmv.fmv_open(player, ctypes.byref(movie), ctypes.byref(options))

        # Assert
        assert scb3_words(fmv, FIRST_SPRITE) == [SCB3_GRID_HEAD] + [SCB3_GRID_STICKY] * 19

    def test_a_caller_that_owns_the_low_sprites_gets_the_grid_moved_up(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        options.first_sprite = MOVED_FIRST_SPRITE
        player = new_player()

        # Act
        fmv.fmv_open(player, ctypes.byref(movie), ctypes.byref(options))

        # Assert
        assert fmv.fmv_test_vram(VRAM_SCB3 + MOVED_FIRST_SPRITE) == SCB3_GRID_HEAD
        assert fmv.fmv_test_vram(VRAM_SCB3 + FIRST_SPRITE) == 0

    def test_moving_the_grid_offsets_every_stream_address(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        options.first_sprite = MOVED_FIRST_SPRITE

        # Act
        player = opened(fmv, movie, options)

        # Assert
        assert fmv.fmv_test_player_sprite_offset(player) == 7 * SCB1_WORDS_PER_SPRITE

    def test_it_uploads_the_first_epoch_into_the_bank_it_was_given(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        player = new_player()

        # Act
        fmv.fmv_open(player, ctypes.byref(movie), ctypes.byref(options))

        # Assert
        assert fmv.fmv_test_palram(PALETTE_BASE * PALETTE_WORDS) == 0x8000

    def test_it_leaves_the_callers_own_palettes_untouched(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        player = new_player()
        owned = range(PALETTE_BASE * PALETTE_WORDS)

        # Act
        fmv.fmv_open(player, ctypes.byref(movie), ctypes.byref(options))

        # Assert
        assert [fmv.fmv_test_palram(word) for word in owned] == [0] * len(owned)

    def test_it_kicks_the_watchdog_while_it_sets_up(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        player = new_player()

        # Act
        fmv.fmv_open(player, ctypes.byref(movie), ctypes.byref(options))

        # Assert
        assert fmv.fmv_test_watchdog_kicks() >= 2
