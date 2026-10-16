from __future__ import annotations

import ctypes

import pytest

from tests.fmvhelp import (
    FIRST_SPRITE,
    FMV_CORRUPT,
    GRID_ROWS,
    SCB1_WORDS_PER_SPRITE,
    build,
    corrupt,
    movie_for,
    new_player,
    opened,
    started,
)

OVERSIZED_GRID_COLS = 400


@pytest.fixture(scope="session")
def fmv(tmp_path_factory):
    return build(tmp_path_factory, audio=True)


@pytest.fixture
def movie(fmv):
    return movie_for(fmv)


class TestACorruptStream:
    def test_a_frame_claiming_more_runs_than_the_movie_allows_stops_play(self, fmv, movie):
        # Arrange
        corrupt(movie, 1, runs=GRID_ROWS + 1)
        options = fmv.fmv_defaults()
        options.skip_pad = 0
        options.skip_start = 0

        # Act
        outcome = fmv.fmv_play(ctypes.byref(movie), ctypes.byref(options))

        # Assert
        assert outcome == FMV_CORRUPT

    def test_a_run_below_the_grid_writes_nothing(self, fmv, movie):
        # Arrange
        corrupt(movie, 0, address=0)
        player = opened(fmv, movie, fmv.fmv_defaults())
        grid_start = FIRST_SPRITE * SCB1_WORDS_PER_SPRITE

        # Act
        fmv.fmv_start(player)

        # Assert
        assert fmv.fmv_faulted(player) == 1
        assert fmv.fmv_test_vram(0) == 0
        assert fmv.fmv_test_vram(grid_start) == 0

    def test_a_layout_the_board_cannot_hold_fails_before_any_register(self, fmv, movie):
        # Arrange
        movie.grid_cols = OVERSIZED_GRID_COLS
        options = fmv.fmv_defaults()
        player = new_player()

        # Act
        fmv.fmv_open(player, ctypes.byref(movie), ctypes.byref(options))

        # Assert
        assert fmv.fmv_faulted(player) == 1
        assert fmv.fmv_test_lspc_mode() == 0

    def test_prepare_finds_a_bad_frame_before_the_tick_draws_it(self, fmv, movie):
        # Arrange
        corrupt(movie, 1, runs=GRID_ROWS + 1)
        player = started(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_prepare(player)

        # Assert
        assert fmv.fmv_faulted(player) == 1
        assert fmv.fmv_ended(player) == 1

    def test_a_clean_stream_never_faults(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_prepare(player)

        # Assert
        assert fmv.fmv_faulted(player) == 0
