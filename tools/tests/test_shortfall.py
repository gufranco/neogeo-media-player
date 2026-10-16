from __future__ import annotations

import pytest
from fmvcore.testing import seeded

from neogeomedia import shortfall

fake = seeded()


class TestTheDurationThatFits:
    def test_the_refusal_names_the_whole_seconds_that_fit(self):
        # Arrange
        held = fake.random_int(min=61, max=3_599)
        seconds = held + fake.pyfloat(min_value=0.0, max_value=0.99)

        # Act
        message = shortfall.shortfall(seconds=seconds, rung="q17", cheapest=False)

        # Assert
        assert f"--duration {held};" not in message
        assert f"--duration {held} or a cheaper --quality;" in message
        assert f"holds {held // 60}m{held % 60:02d}s" in message

    def test_the_cheapest_rung_offers_no_cheaper_one(self):
        # Arrange
        held = fake.random_int(min=1, max=59)

        # Act
        message = shortfall.shortfall(seconds=float(held), rung="q35", cheapest=True)

        # Assert
        assert f"Re-run with --duration {held}; nothing here will shorten" in message

    def test_under_a_second_names_no_duration(self):
        # Arrange
        seconds = fake.pyfloat(min_value=0.0, max_value=0.99)

        # Act
        message = shortfall.shortfall(seconds=seconds, rung="q35", cheapest=True)

        # Assert
        assert "not even one second of this film fits" in message
        assert "--duration" not in message

    def test_a_negative_reach_is_a_programming_error(self):
        # Arrange
        seconds = -fake.pyfloat(min_value=0.1, max_value=10.0)

        # Act
        with pytest.raises(ValueError, match="negative") as raised:
            shortfall.shortfall(seconds=seconds, rung="q17", cheapest=False)

        # Assert
        assert "q17" not in str(raised.value)
