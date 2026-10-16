from __future__ import annotations

import pytest
from faker import Faker
from fmvcore.testing import SEED

from neogeomedia import quality

RATE = 100_000.0
PLAN_VBLANK = 59.1856
VBLANK = 59.185
SHORTFALL = "this source does not fit at any quality tier; trim 9:23:28 and bake again"


@pytest.fixture
def source_name() -> str:
    fake = Faker()
    fake.seed_instance(SEED)
    return fake.file_name(extension="mkv")


def plan(source: str, minutes: float, anchors: dict[float, float] | None = None) -> str:
    return quality.format_plan(
        source=source,
        minutes=minutes,
        width=1920,
        height=1080,
        source_fps=24.0,
        has_audio=True,
        reference_rate=RATE,
        vblank_fps=PLAN_VBLANK if anchors is None else VBLANK,
        anchors=anchors,
    )


def listed_tiers(text: str) -> list[str]:
    return [line.split()[0] for line in text.splitlines() if line.startswith("  q")]


class TestPlanReport:
    def test_it_names_every_tier_the_source_can_use(self, source_name):
        # Arrange
        reachable = [f"q{number:02d}" for number in range(1, 36) if number != 31]

        # Act
        text = plan(source_name, 12.0)

        # Assert
        assert listed_tiers(text) == reachable

    def test_it_names_the_source(self, source_name):
        # Arrange
        minutes = 12.0

        # Act
        text = plan(source_name, minutes)

        # Assert
        assert f"  {source_name}\n" in text

    def test_it_states_the_selected_tier(self, source_name):
        # Arrange
        minutes = 12.0

        # Act
        text = plan(source_name, minutes)

        # Assert
        assert "\nSelected: q24\n" in text

    def test_it_reports_the_measured_rate(self, source_name):
        # Arrange
        minutes = 12.0

        # Act
        text = plan(source_name, minutes)

        # Assert
        assert "  measured 100,000 tiles per minute at 'q17'" in text

    def test_it_tells_the_user_how_much_to_trim_for_a_better_tier(self, source_name):
        # Arrange
        minutes = 12.0

        # Act
        text = plan(source_name, minutes)

        # Assert
        assert "  Trim 0:09, bringing the source to 11:52 or shorter." in text

    def test_it_says_plainly_when_nothing_fits(self, source_name):
        # Arrange
        minutes = 600.0

        # Act
        text = plan(source_name, minutes)

        # Assert
        assert "This source does not fit the cartridge at any quality tier." in text

    def test_a_source_that_fits_the_best_tier_needs_no_trim_advice(self, source_name):
        # Arrange
        minutes = 0.5

        # Act
        text = plan(source_name, minutes)

        # Assert
        assert "\nSelected: q01\n" in text
        assert "Trim" not in text

    def test_it_reports_the_budget_of_the_selected_tier(self, source_name):
        # Arrange
        minutes = 12.0

        # Act
        text = plan(source_name, minutes)

        # Assert
        assert "  C-ROM    114.3 MiB of 128.0 MiB     89%   936,000 tiles" in text
        assert "at 46.6 kHz, grade 4 of 35" in text


class TestPlanAgreesWithTheBake:
    def test_the_printed_choice_is_the_one_the_anchors_imply(self, source_name):
        # Arrange
        anchors = {1.529: 1.9, 1.0: 1.0, 0.581: 0.5, 0.437: 0.4}

        # Act
        text = plan(source_name, 20.0, anchors)

        # Assert
        assert "\nSelected: q32\n" in text

    def test_a_tier_the_baker_would_refuse_is_not_printed(self, source_name):
        # Arrange
        minutes = 20.0

        # Act
        text = plan(source_name, minutes)

        # Assert
        assert "q31" not in listed_tiers(text)
        assert "  q31 " not in text


class TestShortfallMessage:
    def test_a_source_that_fits_has_no_message(self):
        # Arrange
        minutes = 1.0

        # Act
        message = quality.shortfall_message(minutes, RATE)

        # Assert
        assert message is None

    def test_a_source_beyond_every_tier_is_told_how_much_to_cut(self):
        # Arrange
        minutes = 600.0

        # Act
        message = quality.shortfall_message(minutes, RATE)

        # Assert
        assert message == SHORTFALL

    def test_the_amount_named_is_enough_to_make_it_fit(self):
        # Arrange
        trimmed = 600.0 - quality.survey(600.0, RATE)[-1].trim_minutes

        # Act
        fit = quality.select(trimmed, RATE)

        # Assert
        assert fit is not None
        assert fit.tier.name == "q35"


class TestTheCodeNeverTrims:
    def test_a_source_that_fits_nowhere_is_refused_rather_than_shortened(self):
        # Arrange
        minutes = 600.0

        # Act
        fit = quality.select(minutes, RATE)

        # Assert
        assert fit is None

    def test_the_refusal_names_the_trim_for_the_owner_to_make(self):
        # Arrange
        minutes = 600.0

        # Act
        message = quality.shortfall_message(minutes, RATE)

        # Assert
        assert message is not None
        assert "trim 9:23:28" in message

    def test_a_long_source_gives_up_sample_rate_and_keeps_its_runtime(self):
        # Arrange
        full_rate = quality.DEFAULT_AUDIO_HZ

        # Act
        rate = quality.audio_hz_for(60.0)

        # Assert
        assert rate < full_rate
        assert rate == pytest.approx(9319.729275, abs=1e-6)

    def test_the_advice_is_reported_and_never_applied(self):
        # Arrange
        minutes = 600.0

        # Act
        fit = quality.survey(minutes, RATE)[-1]

        # Assert
        assert fit.trim_minutes == pytest.approx(563.466667, abs=1e-6)
        assert fit.minutes == 600.0
