from __future__ import annotations

import pytest

from tests.scripthelp import load_script

REFERENCE = "q03"


@pytest.fixture(scope="module")
def sweep():
    return load_script("sweep_ladder")


def rung(sweep, name, declared, tiles, error):
    return sweep.Measurement(name=name, declared=declared, tiles=tiles, error=error)


def replaced(rows, index, row):
    return [*rows[:index], row, *rows[index + 1 :]]


@pytest.fixture
def healthy(sweep):
    return [
        rung(sweep, "q01", 1.50, 100, 0.001),
        rung(sweep, "q02", 1.20, 80, 0.002),
        rung(sweep, "q03", 1.00, 60, 0.004),
        rung(sweep, "q04", 0.80, 40, 0.008),
    ]


@pytest.fixture
def costly(sweep, healthy):
    return replaced(healthy, 2, rung(sweep, "q03", 1.00, 95, 0.004))


@pytest.fixture
def beaten(sweep, healthy):
    return replaced(healthy, 1, rung(sweep, "q02", 1.20, 100, 0.005))


class TestMonotonicity:
    def test_a_healthy_ladder_has_no_cost_inversion(self, sweep, healthy):
        # Arrange
        rows = healthy

        # Act
        found = sweep.cost_inversions(rows)

        # Assert
        assert found == []

    def test_a_healthy_ladder_has_no_error_inversion(self, sweep, healthy):
        # Arrange
        rows = healthy

        # Act
        found = sweep.error_inversions(rows)

        # Assert
        assert found == []

    def test_a_rung_that_costs_more_than_the_one_above_is_reported(self, sweep, costly):
        # Arrange
        rows = costly

        # Act
        found = sweep.cost_inversions(rows)

        # Assert
        assert found == [("q02", "q03")]

    def test_a_rung_that_looks_better_than_the_one_above_is_reported(self, sweep, healthy):
        # Arrange
        rows = replaced(healthy, 2, rung(sweep, "q03", 1.00, 60, 0.0015))

        # Act
        found = sweep.error_inversions(rows)

        # Assert
        assert found == [("q02", "q03")]


class TestDominance:
    def test_a_healthy_ladder_has_no_dominated_rung(self, sweep, healthy):
        # Arrange
        rows = healthy

        # Act
        found = sweep.dominated(rows)

        # Assert
        assert found == []

    def test_a_rung_beaten_on_both_axes_is_named_with_its_first_beater(self, sweep, beaten):
        # Arrange
        rows = beaten

        # Act
        found = sweep.dominated(rows)

        # Assert
        assert [entry[:3] for entry in found] == [("q02", "q01", 0)]
        assert found[0][3] == pytest.approx(0.004)

    def test_an_equal_rung_does_not_count_as_dominating(self, sweep):
        # Arrange
        rows = [rung(sweep, "a", 1.0, 50, 0.001), rung(sweep, "b", 0.9, 50, 0.001)]

        # Act
        found = sweep.dominated(rows)

        # Assert
        assert found == []


class TestModelError:
    def test_the_reference_rung_has_no_model_error(self, sweep, healthy):
        # Arrange
        rows = healthy

        # Act
        errors = sweep.model_error(rows, reference=REFERENCE)

        # Assert
        assert errors[REFERENCE] == pytest.approx(0.0)

    def test_a_rung_costing_more_than_declared_reads_positive(self, sweep, healthy):
        # Arrange
        rows = healthy

        # Act
        errors = sweep.model_error(rows, reference=REFERENCE)

        # Assert
        assert errors["q01"] == pytest.approx(1 / 9)

    def test_an_unknown_reference_is_refused(self, sweep, healthy):
        # Arrange
        rows = healthy

        # Act
        with pytest.raises(KeyError) as refused:
            sweep.model_error(rows, reference="nope")

        # Assert
        assert refused.value.args == ("no measurement for the reference rung 'nope'",)


class TestReport:
    def test_the_heading_names_the_reference_and_its_tiles(self, sweep, healthy):
        # Arrange
        rows = healthy

        # Act
        text = sweep.format_report(rows, reference=REFERENCE)

        # Assert
        assert text.splitlines()[0] == "4 rungs measured, reference q03 = 60 tiles"

    def test_every_rung_appears_with_its_measured_cost(self, sweep, healthy):
        # Arrange
        rows = healthy

        # Act
        text = sweep.format_report(rows, reference=REFERENCE)

        # Assert
        assert [line[:6].strip() for line in text.splitlines()[4:8]] == [
            "q01",
            "q02",
            "q03",
            "q04",
        ]
        assert text.splitlines()[4] == "q01        1.500     1.667   +11.1%      100   0.001000"

    def test_a_clean_ladder_says_so(self, sweep, healthy):
        # Arrange
        rows = healthy

        # Act
        text = sweep.format_report(rows, reference=REFERENCE)

        # Assert
        assert text.splitlines()[-3:] == [
            "cost rises as quality falls: nowhere",
            "error falls as quality falls: nowhere",
            "every rung is on the frontier",
        ]

    def test_a_dominated_rung_is_called_out(self, sweep, beaten):
        # Arrange
        rows = beaten

        # Act
        text = sweep.format_report(rows, reference=REFERENCE)

        # Assert
        assert "  q02 is beaten by q01: +0 tiles, +0.004000 error" in text.splitlines()


class TestExitCode:
    def test_a_clean_ladder_passes(self, sweep, healthy):
        # Arrange
        rows = healthy

        # Act
        code = sweep.verdict(rows)

        # Assert
        assert code == 0

    def test_a_dominated_rung_fails(self, sweep, beaten):
        # Arrange
        rows = beaten

        # Act
        code = sweep.verdict(rows)

        # Assert
        assert code == 1

    def test_a_cost_inversion_fails(self, sweep, costly):
        # Arrange
        rows = costly

        # Act
        code = sweep.verdict(rows)

        # Assert
        assert code == 1
