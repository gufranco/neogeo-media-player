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


LANGUAGES = ("", ".ja", ".zh-Hans", ".zh-HK")
FEATURE_SECTION = 1


def feature_section(readme: Path) -> str:
    text = readme.read_text()
    starts = [
        index for index, line in enumerate(text.splitlines(keepends=True)) if line.startswith("## ")
    ]
    lines = text.splitlines(keepends=True)
    body = "".join(lines[starts[FEATURE_SECTION] + 1 : starts[FEATURE_SECTION + 1]])
    return body.strip("\n").replace("[FAMILY.md](FAMILY.md)", "[FAMILY.md](../FAMILY.md)") + "\n"


class TestTheSharedFeatureTable:
    @pytest.mark.parametrize("tag", LANGUAGES)
    def test_the_readme_carries_the_cores_feature_table(self, tag):
        # Arrange
        core = ROOT / "fmv-core-python" / "features" / f"README{tag}.md"
        if not core.is_file():
            pytest.fail("the fmv-core-python submodule is not checked out")

        # Act
        ours = feature_section(ROOT / f"README{tag}.md")

        # Assert
        assert ours == core.read_text()
