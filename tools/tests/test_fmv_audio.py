from __future__ import annotations

import numpy as np
import pytest
from fmvcore.testing import SEED

from tests.fmvhelp import (
    GRID_ROWS,
    SOUND_PLAY,
    SOUND_STOP,
    build,
    movie_for,
    opened,
    started,
)

PROM_BANKS = 8


@pytest.fixture(scope="session")
def fmv(tmp_path_factory):
    return build(tmp_path_factory, audio=True)


@pytest.fixture(scope="session")
def silent_fmv(tmp_path_factory):
    return build(tmp_path_factory, audio=False)


@pytest.fixture
def movie(fmv):
    return movie_for(fmv)


@pytest.fixture
def silent_movie(silent_fmv):
    return movie_for(silent_fmv)


class TestTheAudioSwitch:
    def test_a_build_with_audio_cues_the_soundtrack(self, fmv, movie):
        # Arrange
        player = opened(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_start(player)

        # Assert
        assert fmv.fmv_test_last_sound_command() == SOUND_PLAY

    def test_a_caller_that_asks_for_silence_sends_nothing(self, fmv, movie):
        # Arrange
        options = fmv.fmv_defaults()
        options.audio = 0
        player = opened(fmv, movie, options)

        # Act
        fmv.fmv_start(player)

        # Assert
        assert fmv.fmv_test_last_sound_command() == 0

    def test_a_video_only_build_sends_nothing_at_all(self, silent_fmv, silent_movie):
        # Arrange
        player = opened(silent_fmv, silent_movie, silent_fmv.fmv_defaults())

        # Act
        silent_fmv.fmv_start(player)

        # Assert
        assert silent_fmv.fmv_test_last_sound_command() == 0

    def test_a_video_only_build_still_draws_the_movie(self, silent_fmv, silent_movie):
        # Arrange
        player = opened(silent_fmv, silent_movie, silent_fmv.fmv_defaults())

        # Act
        silent_fmv.fmv_start(player)

        # Assert
        assert silent_fmv.fmv_last_updates(player) == GRID_ROWS

    def test_a_video_only_build_still_gives_the_machine_back(self, silent_fmv, silent_movie):
        # Arrange
        options = silent_fmv.fmv_defaults()
        options.prom_bank = int(np.random.default_rng(SEED).integers(1, PROM_BANKS))
        player = started(silent_fmv, silent_movie, options)

        # Act
        silent_fmv.fmv_close(player)

        # Assert
        assert silent_fmv.fmv_test_prom_bank() == options.prom_bank


class TestSoundOnAndOff:
    def test_turning_sound_off_stops_the_soundtrack(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())

        # Act
        fmv.fmv_set_audio(player, 0)

        # Assert
        assert fmv.fmv_test_last_sound_command() == SOUND_STOP

    def test_with_sound_off_a_resume_sends_no_play_command(self, fmv, movie):
        # Arrange
        player = started(fmv, movie, fmv.fmv_defaults())
        fmv.fmv_set_audio(player, 0)

        # Act
        fmv.fmv_resume(player)

        # Assert
        assert fmv.fmv_test_last_sound_command() == SOUND_STOP
