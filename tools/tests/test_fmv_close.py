from __future__ import annotations

import numpy as np
import pytest
from fmvcore.testing import SEED

from tests.fmvhelp import (
    EPOCH_PALETTES,
    FIRST_SPRITE,
    FMV_FIX_BOARD,
    GRID_COLS,
    PALETTE_BASE,
    PALETTE_WORDS,
    VRAM_SCB3,
    build,
    movie_for,
    played,
    started,
)

PROM_BANKS = 8


@pytest.fixture(scope="session")
def fmv(tmp_path_factory):
    return build(tmp_path_factory, audio=True)


@pytest.fixture
def movie(fmv):
    return movie_for(fmv)


@pytest.fixture
def rng():
    return np.random.default_rng(SEED)


class TestGivingTheMachineBack:
    def test_it_restores_the_lspc_mode_the_caller_declared(self, fmv, movie, rng):
        # Arrange
        options = fmv.fmv_defaults()
        options.lspc_mode = int(rng.integers(0x0100, 0x10000))
        player = started(fmv, movie, options)

        # Act
        fmv.fmv_close(player)

        # Assert
        assert fmv.fmv_test_lspc_mode() == options.lspc_mode

    def test_it_restores_the_board_fix_rom_when_that_is_what_the_caller_uses(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        options.fix_source = FMV_FIX_BOARD
        player = started(fmv, movie, options)

        # Act
        fmv.fmv_close(player)

        # Assert
        assert fmv.fmv_test_fix_source() == FMV_FIX_BOARD

    def test_it_restores_the_palette_bank_the_caller_declared(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        options.palette_bank = 1
        player = started(fmv, movie, options)

        # Act
        fmv.fmv_close(player)

        # Assert
        assert fmv.fmv_test_palette_bank() == 1

    def test_it_restores_the_program_bank_the_caller_declared(self, fmv, movie, rng):
        # Arrange
        options = fmv.fmv_defaults()
        options.prom_bank = int(rng.integers(1, PROM_BANKS))
        player = started(fmv, movie, options)

        # Act
        fmv.fmv_close(player)

        # Assert
        assert fmv.fmv_test_prom_bank() == options.prom_bank

    def test_it_disables_the_sprites_it_borrowed(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_close(player)

        # Assert
        borrowed = [fmv.fmv_test_vram(VRAM_SCB3 + FIRST_SPRITE + col) for col in range(GRID_COLS)]
        assert borrowed == [0] * GRID_COLS

    def test_it_blanks_the_palettes_it_borrowed(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())
        first = PALETTE_BASE * PALETTE_WORDS
        borrowed = range(first, first + 2 * EPOCH_PALETTES * PALETTE_WORDS)

        # Act
        fmv.fmv_close(player)

        # Assert
        assert [fmv.fmv_test_palram(word) for word in borrowed] == [0] * len(borrowed)

    def test_closing_twice_is_harmless(self, fmv, movie, rng):
        # Arrange
        options = fmv.fmv_defaults()
        player = played(fmv, movie, options)
        options.prom_bank = int(rng.integers(1, PROM_BANKS))

        # Act
        fmv.fmv_close(player)

        # Assert
        assert fmv.fmv_test_prom_bank() == 0

    def test_a_closed_player_says_so(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_close(player)

        # Assert
        assert fmv.fmv_test_player_open(player) == 0
