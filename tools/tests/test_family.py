from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLOSING_LINE = "---"


def shared_part(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    return lines[: lines.index(CLOSING_LINE) + 1]


class TestTheFamilyStandard:
    def test_the_shared_part_matches_the_core_copy(self):
        # Arrange
        core = ROOT / "fmv-core-python" / "FAMILY.md"
        if not core.is_file():
            pytest.fail("the fmv-core-python submodule is not checked out")

        # Act
        ours = shared_part(ROOT / "FAMILY.md")

        # Assert
        assert ours == shared_part(core)
