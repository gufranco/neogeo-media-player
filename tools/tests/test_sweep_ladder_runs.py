from __future__ import annotations

import json
from pathlib import Path

import pytest
from fmvcore.testing import seeded

from tests.bakehelp import SYNTHETIC_FILM
from tests.scripthelp import load_script

SKIPPED = ("q31", "q32", "q33")
REACHABLE = tuple(
    name for name in (f"q{index:02d}" for index in range(1, 36)) if name not in SKIPPED
)
TILE_STEP = 10
ERROR_STEP = 0.001
SHORT_WINDOW = ("--start", "0", "--duration", "0.2")
PAST_THE_END = ("--start", "100", "--duration", "0.2")


@pytest.fixture(scope="module")
def sweep():
    return load_script("sweep_ladder")


def cached_ladder(out: Path, *, base: int, missing: tuple[str, ...] = ()) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(REACHABLE):
        if name in missing:
            continue
        report = {
            "tile_count": base - TILE_STEP * index,
            "displayed_error": ERROR_STEP * (index + 1),
        }
        (out / f"{name}.json").write_text(json.dumps(report))
    return out


def sweep_argv(out: Path, *extra: str, source: Path = SYNTHETIC_FILM) -> list[str]:
    return ["--source", str(source), "--out", str(out), *extra]


def table_row(text: str, name: str) -> list[str]:
    return next(line.split() for line in text.splitlines() if line.startswith(f"{name} "))


class TestCachedReports:
    def test_a_frontier_read_from_cache_passes(self, sweep, tmp_path, capsys):
        # Arrange
        base = seeded().random_int(1000, 5000)
        out = cached_ladder(tmp_path / "sweep", base=base)

        # Act
        code = sweep.main(sweep_argv(out))

        # Assert
        lines = capsys.readouterr().out.splitlines()
        assert code == 0
        assert lines[0] == f"32 rungs measured, reference q17 = {base - 160} tiles"
        assert lines[-1] == "every rung is on the frontier"
        assert sorted(path.name for path in out.iterdir()) == [f"{n}.json" for n in REACHABLE]

    def test_a_hold_that_drops_no_frame_of_the_source_is_skipped(self, sweep, tmp_path, capsys):
        # Arrange
        out = cached_ladder(tmp_path / "sweep", base=seeded().random_int(1000, 5000))

        # Act
        sweep.main(sweep_argv(out))

        # Assert
        assert capsys.readouterr().err.splitlines() == [
            f"skip {name}, its hold drops no frame of this source" for name in SKIPPED
        ]

    def test_a_dominated_rung_fails_the_run_and_is_named(self, sweep, tmp_path, capsys):
        # Arrange
        out = cached_ladder(tmp_path / "sweep", base=seeded().random_int(1000, 5000))
        q04 = json.loads((out / "q04.json").read_text())
        worse = {"tile_count": q04["tile_count"] + 5, "displayed_error": 0.0045}
        (out / "q05.json").write_text(json.dumps(worse))

        # Act
        code = sweep.main(sweep_argv(out))

        # Assert
        lines = capsys.readouterr().out.splitlines()
        assert code == 1
        assert "  q05 is beaten by q04: +5 tiles, +0.000500 error" in lines


class TestBaking:
    def test_a_missing_tier_is_baked_and_its_build_removed(self, sweep, tmp_path, capsys):
        # Arrange
        out = cached_ladder(tmp_path / "sweep", base=50_000, missing=("q01",))

        # Act
        sweep.main(sweep_argv(out, *SHORT_WINDOW))

        # Assert
        captured = capsys.readouterr()
        baked = json.loads((out / "q01.json").read_text())
        assert table_row(captured.out, "q01")[4] == str(baked["tile_count"])
        assert "baking q01" in captured.err.splitlines()
        assert not (out / "work-q01").exists()

    def test_keeping_builds_leaves_the_build_directory(self, sweep, tmp_path):
        # Arrange
        out = cached_ladder(tmp_path / "sweep", base=50_000, missing=("q01",))

        # Act
        sweep.main(sweep_argv(out, *SHORT_WINDOW, "--keep-builds"))

        # Assert
        assert (out / "work-q01" / "generated").is_dir()

    def test_a_failed_bake_is_named_and_left_out(self, sweep, tmp_path, capsys):
        # Arrange
        out = cached_ladder(tmp_path / "sweep", base=50_000, missing=("q05",))

        # Act
        sweep.main(sweep_argv(out, *PAST_THE_END))

        # Assert
        captured = capsys.readouterr()
        assert captured.out.splitlines()[0] == "31 rungs measured, reference q17 = 49840 tiles"
        assert (
            "  q05 failed: ['ValueError: cannot build a palette set from an empty tile batch']"
            in captured.err.splitlines()
        )


class TestRefusals:
    def test_a_missing_source_exits_two_and_is_named(self, sweep, tmp_path, capsys):
        # Arrange
        absent = tmp_path / "absent.mp4"

        # Act
        code = sweep.main(sweep_argv(tmp_path / "sweep", source=absent))

        # Assert
        assert code == 2
        assert capsys.readouterr().err == f"source not found: {absent}\n"

    def test_a_sweep_where_every_bake_fails_exits_two(self, sweep, tmp_path, capsys):
        # Arrange
        out = tmp_path / "sweep"

        # Act
        code = sweep.main(sweep_argv(out, *PAST_THE_END))

        # Assert
        assert code == 2
        assert capsys.readouterr().err.splitlines()[-1] == "no tier produced a report"
