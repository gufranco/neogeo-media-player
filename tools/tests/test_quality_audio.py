from __future__ import annotations

import pytest

from neogeomedia import quality

PAGE_COUNTER_RUNTIMES = (1.0, 10.0, 25.0, 25.4, 26.0, 30.0, 40.0, 90.0)


def soundtrack_bytes(minutes: float, rate: float) -> float:
    return minutes * quality.SECONDS_PER_MINUTE * rate * quality.ADPCM_B_BYTES_PER_SAMPLE


class TestAudioRate:
    @pytest.mark.parametrize("minutes", [1.0, 2.0, 5.0, 10.0])
    def test_a_short_movie_keeps_the_chip_maximum(self, minutes):
        # Arrange
        runtime = minutes

        # Act
        rate = quality.audio_hz_for(runtime)

        # Assert
        assert rate == quality.DEFAULT_AUDIO_HZ
        assert rate == pytest.approx(quality.MAX_AUDIO_HZ, rel=0.01)

    @pytest.mark.parametrize(
        ("minutes", "expected"),
        [(40.0, 13980.441623), (60.0, 9319.729275)],
        ids=["forty minutes", "an hour"],
    )
    def test_a_long_movie_drops_the_rate_to_fit(self, minutes, expected):
        # Arrange
        runtime = minutes

        # Act
        rate = quality.audio_hz_for(runtime)

        # Assert
        assert rate == pytest.approx(expected, abs=1e-6)
        assert rate < quality.DEFAULT_AUDIO_HZ

    def test_a_ten_minute_movie_still_beats_the_old_ceiling(self):
        # Arrange
        old_ceiling = 22050.0

        # Act
        rate = quality.audio_hz_for(10.0)

        # Assert
        assert rate > old_ceiling


class TestAudioFitsThePageCounter:
    @pytest.mark.parametrize("minutes", PAGE_COUNTER_RUNTIMES)
    def test_the_last_page_is_addressable(self, minutes):
        # Arrange
        runtime = minutes

        # Act
        rate = quality.audio_hz_for(runtime)

        # Assert
        assert soundtrack_bytes(minutes, rate) / 256 <= quality.ADPCM_B_MAX_PAGES

    @pytest.mark.parametrize("minutes", PAGE_COUNTER_RUNTIMES)
    def test_the_soundtrack_still_fits_the_voice_rom(self, minutes):
        # Arrange
        runtime = minutes

        # Act
        rate = quality.audio_hz_for(runtime)

        # Assert
        assert soundtrack_bytes(minutes, rate) <= quality.ADPCM_B_BYTES

    @pytest.mark.parametrize("minutes", [1.0, 10.0, 25.0, 40.0, 90.0])
    def test_it_always_fits_the_page_counter(self, minutes):
        # Arrange
        runtime = minutes

        # Act
        rate = quality.audio_hz_for(runtime)

        # Assert
        assert soundtrack_bytes(minutes, rate) / quality.ADPCM_B_PAGE_BYTES <= (
            quality.ADPCM_B_MAX_PAGES
        )


class TestAudioGrade:
    @pytest.mark.parametrize(
        ("rate", "grade"),
        [
            (55555.0, 1),
            (44100.0, 5),
            (22050.0, 17),
            (11025.0, 29),
            (8000.0, 35),
            (4000.0, 35),
        ],
    )
    def test_a_lower_rate_gives_a_worse_grade_inside_the_ladder(self, rate, grade):
        # Arrange
        sample_rate = rate

        # Act
        graded = quality.audio_grade(sample_rate)

        # Assert
        assert graded == grade
        assert 1 <= graded <= len(quality.LADDER)

    def test_the_chip_maximum_is_the_top_grade(self):
        # Arrange
        rate = quality.MAX_AUDIO_HZ

        # Act
        grade = quality.audio_grade(rate)

        # Assert
        assert grade == 1

    def test_a_short_movie_is_graded_top(self):
        # Arrange
        rate = quality.audio_hz_for(2.0)

        # Act
        grade = quality.audio_grade(rate)

        # Assert
        assert grade == 1
