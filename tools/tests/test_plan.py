from __future__ import annotations

import pytest

from neogeomedia import plan, quality
from tests.bakehelp import lavfi_clip

pytestmark = pytest.mark.ffmpeg


@pytest.fixture(scope="module")
def synthetic_clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("plan") / "source.mp4"
    return lavfi_clip(path, "testsrc=size=640x480:rate=24:duration=8")


def plan_argv(clip) -> list[str]:
    return ["--source", str(clip), "--samples", "2", "--sample-seconds", "1"]


class TestPlanCommand:
    def test_it_succeeds_on_a_real_source(self, synthetic_clip):
        # Arrange
        argv = plan_argv(synthetic_clip)

        # Act
        code = plan.main(argv)

        # Assert
        assert code == 0

    def test_it_prints_the_ladder(self, synthetic_clip, capsys):
        # Arrange
        argv = plan_argv(synthetic_clip)

        # Act
        code = plan.main(argv)

        # Assert
        assert code == 0
        out = capsys.readouterr().out
        assert "Quality ladder" in out
        assert quality.LADDER[0].name in out
        assert quality.LADDER[-1].name in out

    @pytest.mark.parametrize(
        "expected",
        ["tiles per minute", "C-ROM", "source.mp4"],
        ids=["measured-rate", "cartridge-budget", "source-name"],
    )
    def test_it_prints_what_was_measured(self, synthetic_clip, capsys, expected):
        # Arrange
        argv = plan_argv(synthetic_clip)

        # Act
        code = plan.main(argv)

        # Assert
        assert code == 0
        assert expected in capsys.readouterr().out
