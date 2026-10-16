from __future__ import annotations

import ctypes

import numpy as np
import pytest
from fmvcore.testing import SEED

from tests.fmvhelp import (
    FMV_FINISHED,
    FMV_PAD_A,
    FMV_SKIPPED,
    FMV_START,
    FRAMES,
    GRID_ROWS,
    PAD_RELEASED,
    PROM_BANK_BYTES,
    SKIP_FN,
    build,
    movie_for,
    opened,
    started,
)

STREAM_BANKS = 8


@pytest.fixture(scope="session")
def fmv(tmp_path_factory):
    return build(tmp_path_factory, audio=True)


@pytest.fixture
def movie(fmv):
    return movie_for(fmv)


@pytest.fixture
def bank_number():
    return int(np.random.default_rng(SEED).integers(1, STREAM_BANKS))


def run_to_the_end(fmv, player) -> None:
    for _ in range(FRAMES):
        fmv.fmv_tick(player)


def play(fmv, movie, options) -> int:
    return fmv.fmv_play(ctypes.byref(movie), ctypes.byref(options))


class TestAdvancing:
    def test_the_first_frame_is_drawn_by_start(self, fmv, movie):
        # Arrange
        player = opened(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_start(player)

        # Assert
        assert fmv.fmv_position(player) == 1

    def test_a_tick_advances_one_frame(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_tick(player)

        # Assert
        assert fmv.fmv_position(player) == 2

    def test_a_frame_reports_what_it_wrote(self, fmv, movie):
        # Arrange
        player = opened(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_start(player)

        # Assert
        assert fmv.fmv_last_updates(player) == GRID_ROWS

    def test_it_ends_after_the_last_frame(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())

        # Act
        run_to_the_end(fmv, player)

        # Assert
        assert fmv.fmv_ended(player) == 1

    def test_a_tick_past_the_end_does_nothing(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())
        run_to_the_end(fmv, player)

        # Act
        fmv.fmv_tick(player)

        # Assert
        assert fmv.fmv_position(player) == FRAMES

    def test_a_seek_lands_on_the_keyframe_at_or_before_the_target(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_seek(player, 2)

        # Assert
        assert fmv.fmv_position(player) == 1

    def test_the_stream_bank_follows_the_base_the_linker_gave_it(self, fmv, movie, bank_number):
        # Arrange
        movie.stream_base = bank_number * PROM_BANK_BYTES
        player = opened(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_start(player)

        # Assert
        assert fmv.fmv_test_player_stream_bank(player) == bank_number


class TestReadingTheState:
    def test_the_epoch_is_readable_without_touching_the_struct(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())

        # Act
        epoch = fmv.fmv_epoch(player)

        # Assert
        assert epoch == fmv.fmv_test_player_epoch(player)
        assert epoch == 0

    def test_the_stream_bank_is_readable_without_touching_the_struct(self, fmv, movie, bank_number):
        # Arrange
        movie.stream_base = bank_number * PROM_BANK_BYTES
        player = started(fmv, movie, fmv.fmv_defaults())

        # Act
        bank = fmv.fmv_stream_bank(player)

        # Assert
        assert bank == bank_number


class TestSkipping:
    @pytest.mark.parametrize(
        ("pad", "system", "outcome"),
        [
            (PAD_RELEASED, PAD_RELEASED, FMV_FINISHED),
            (PAD_RELEASED & ~FMV_PAD_A, PAD_RELEASED, FMV_SKIPPED),
            (PAD_RELEASED, PAD_RELEASED & ~FMV_START, FMV_SKIPPED),
        ],
        ids=[
            "a movie left alone runs to the end",
            "a masked button ends it early",
            "start ends it early",
        ],
    )
    def test_the_pad_decides_whether_the_movie_runs_out(self, fmv, movie, pad, system, outcome):
        # Arrange
        options = fmv.fmv_defaults()
        fmv.fmv_test_set_pad(pad, system)

        # Act
        result = play(fmv, movie, options)

        # Assert
        assert result == outcome

    @pytest.mark.parametrize(
        ("verdict", "pad", "outcome"),
        [(1, PAD_RELEASED, FMV_SKIPPED), (0, 0x00, FMV_FINISHED)],
        ids=[
            "a caller predicate replaces the pad entirely",
            "a predicate that never fires lets the movie finish",
        ],
    )
    def test_a_caller_predicate_overrides_the_pad(self, fmv, movie, verdict, pad, outcome):
        # Arrange
        options = fmv.fmv_defaults()
        predicate = SKIP_FN(lambda _user: verdict)
        options.skip = predicate
        fmv.fmv_test_set_pad(pad, pad)

        # Act
        result = play(fmv, movie, options)

        # Assert
        assert result == outcome

    def test_a_skipped_movie_still_gives_the_machine_back(self, fmv, movie, bank_number):
        # Arrange
        options = fmv.fmv_defaults()
        options.palette_bank = 1
        options.prom_bank = bank_number
        fmv.fmv_test_set_pad(PAD_RELEASED & ~FMV_PAD_A, PAD_RELEASED)

        # Act
        result = play(fmv, movie, options)

        # Assert
        assert result == FMV_SKIPPED
        assert fmv.fmv_test_palette_bank() == 1
        assert fmv.fmv_test_prom_bank() == bank_number
