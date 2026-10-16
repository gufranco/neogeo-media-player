from __future__ import annotations

import pytest

from neogeomedia import probe, quality

BUDGET = 1_048_576
MINUTES = 10.0
DOUBLING_BRACKET = ("q01", "q02", "q03", "q05", "q09", "q17", "q33", "q35")


class Measurer:
    def __init__(self, tiles_per_minute: float, *, exhausted_above: int | None = None) -> None:
        self.tiles_per_minute = tiles_per_minute
        self.exhausted_above = exhausted_above
        self.calls: tuple[str, ...] = ()

    def __call__(self, tier: quality.Tier) -> probe.Reading:
        self.calls = (*self.calls, tier.name)
        tiles = self.tiles_per_minute * tier.relative_cost * MINUTES
        strained = self.exhausted_above is not None and tiles > self.exhausted_above
        if tiles > BUDGET:
            return probe.Reading(tier=tier, tiles=BUDGET, capped=True)
        return probe.Reading(tier=tier, tiles=int(tiles), capped=False, exhausted=strained)


def search(measure: Measurer, known: dict[str, float | None] | None = None) -> probe.Outcome:
    return probe.search(measure=measure, minutes=MINUTES, budget=BUDGET, known=known or {})


class TestSearching:
    @pytest.mark.parametrize(
        ("rate", "expected"),
        [
            (60_000.0, "q01"),
            (100_000.0, "q16"),
            (140_000.0, "q25"),
            (250_000.0, "q33"),
            (400_000.0, None),
        ],
    )
    def test_it_finds_the_best_rung_a_plain_walk_down_the_ladder_would(self, rate, expected):
        # Arrange
        measure = Measurer(rate)

        # Act
        found = search(measure)

        # Assert
        assert (found.tier.name if found.tier else None) == expected

    def test_a_source_that_can_afford_the_best_rung_costs_one_bake(self):
        # Arrange
        measure = Measurer(60_000.0)

        # Act
        found = search(measure)

        # Assert
        assert found.tier == quality.tier_by_name("q01")
        assert measure.calls == ("q01",)

    def test_a_source_that_settles_deep_brackets_by_doubling_instead_of_walking(self):
        # Arrange
        measure = Measurer(400_000.0)

        # Act
        search(measure)

        # Assert
        assert measure.calls == DOUBLING_BRACKET
        assert len(measure.calls) < len(quality.LADDER) // 2

    @pytest.mark.parametrize("rate", [60_000.0, 250_000.0, 400_000.0])
    def test_it_always_tries_the_richest_rung_first(self, rate):
        # Arrange
        measure = Measurer(rate)

        # Act
        search(measure)

        # Assert
        assert measure.calls[0] == "q01"

    def test_it_never_bakes_the_same_rung_twice(self):
        # Arrange
        measure = Measurer(250_000.0)

        # Act
        search(measure)

        # Assert
        assert len(measure.calls) == len(set(measure.calls))

    def test_a_rung_that_overran_is_remembered_as_such(self):
        # Arrange
        measure = Measurer(400_000.0)

        # Act
        found = search(measure)

        # Assert
        assert found.too_expensive == list(DOUBLING_BRACKET)
        assert found.rates == dict.fromkeys(DOUBLING_BRACKET)

    def test_a_capped_bake_never_becomes_a_rate(self):
        # Arrange
        measure = Measurer(100_000.0)

        # Act
        found = search(measure)

        # Assert
        assert {name: rate for name, rate in found.rates.items() if rate is not None} == {
            "q17": pytest.approx(100_000.0),
            "q16": pytest.approx(103_000.0),
        }

    def test_a_fully_settled_source_bakes_nothing(self):
        # Arrange
        measure = Measurer(100_000.0)
        known: dict[str, float | None] = {
            t.name: (None if t.relative_cost > 1.0 else 100_000.0 * t.relative_cost)
            for t in quality.LADDER
        }

        # Act
        found = search(measure, known)

        # Assert
        assert measure.calls == ()
        assert found.tier == quality.tier_by_name("q17")

    def test_settled_failures_are_not_baked_again(self):
        # Arrange
        measure = Measurer(100_000.0)
        settled = {t.name for t in quality.LADDER[:10]}

        # Act
        search(measure, dict.fromkeys(settled))

        # Assert
        assert set(measure.calls) & settled == set()

    def test_every_bake_it_ran_is_reported(self):
        # Arrange
        measure = Measurer(100_000.0)

        # Act
        found = search(measure)

        # Assert
        assert found.baked == list(measure.calls)

    def test_a_tier_the_baker_would_refuse_is_never_measured(self):
        # Arrange
        measure = Measurer(3_000_000.0)

        # Act
        probe.search(
            measure=measure,
            minutes=MINUTES,
            budget=BUDGET,
            known={},
            source_fps=24.0,
            vblank_fps=59.185,
        )

        # Assert
        assert "q31" not in measure.calls
        assert measure.calls[-2:] == ("q34", "q35")


class TestItNeverTrims:
    def test_it_reports_no_fit_rather_than_shortening_the_source(self):
        # Arrange
        measure = Measurer(50_000_000.0)

        # Act
        found = search(measure)

        # Assert
        assert found.tier is None
        assert found.minutes == MINUTES


class TestARescuedRungDoesNotCount:
    def test_a_rung_that_only_fits_because_rate_control_gave_up_is_refused(self):
        # Arrange
        measure = Measurer(100_000.0, exhausted_above=700_000)

        # Act
        found = search(measure)

        # Assert
        assert found.tier == quality.tier_by_name("q27")

    def test_an_exhausted_reading_never_becomes_a_rate(self):
        # Arrange
        measure = Measurer(100_000.0, exhausted_above=700_000)

        # Act
        found = search(measure)

        # Assert
        assert {name: rate for name, rate in found.rates.items() if rate is not None} == {
            "q33": pytest.approx(35_700.0),
            "q29": pytest.approx(61_300.0),
            "q27": pytest.approx(68_000.0),
        }

    @pytest.mark.parametrize(
        ("capped", "exhausted", "fits"),
        [(False, False, True), (True, False, False), (False, True, False)],
        ids=["clean", "capped", "exhausted"],
    )
    def test_only_a_reading_that_finished_cleanly_fits(self, capped, exhausted, fits):
        # Arrange
        reading = probe.Reading(
            tier=quality.tier_by_name("q17"), tiles=10, capped=capped, exhausted=exhausted
        )

        # Act
        verdict = reading.fits(100)

        # Assert
        assert verdict is fits

    def test_a_reading_over_the_budget_does_not_fit(self):
        # Arrange
        reading = probe.Reading(tier=quality.tier_by_name("q17"), tiles=101, capped=False)

        # Act
        verdict = reading.fits(100)

        # Assert
        assert verdict is False
