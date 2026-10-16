from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

from neogeomedia import bake, clips

FILMS = clips.load()


def absent(clip: clips.Clip) -> None:
    reason = f"{clip.key} is not on this machine; fetch it with {clips.FETCH_COMMAND}"
    if clips.required():
        pytest.fail(reason)
    pytest.skip(reason)


def baked(clip: clips.Clip, build_dir: Path) -> dict[str, Any]:
    path = clips.resolve(clip)
    if path is None:
        absent(clip)
        return {}
    verdict = clips.verify(path, clip)
    assert verdict.ok, verdict.diagnosis
    report = build_dir / "report.json"
    argv = ["--source", str(path), "--start", str(clip.start), "--duration", str(clip.duration)]
    argv += ["--quality", clip.quality, "--build-dir", str(build_dir), "--report-json", str(report)]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        code = bake.main(argv)
    assert code == 0, f"{clip.key} overran its rung"
    return dict(json.loads(report.read_text()))


@pytest.fixture(scope="module", params=FILMS, ids=[clip.key for clip in FILMS])
def outcome(request, tmp_path_factory) -> tuple[clips.Clip, dict[str, Any]]:
    clip = request.param
    return clip, baked(clip, tmp_path_factory.mktemp(clip.key))


class TestEveryFilmHoldsItsCeilings:
    def test_the_picture_error_stays_under_the_films_ceiling(self, outcome):
        # Arrange
        clip, report = outcome

        # Act
        error = report["displayed_error"]

        # Assert
        assert error <= clip.max_error

    def test_the_tile_cost_stays_under_the_films_ceiling(self, outcome):
        # Arrange
        clip, report = outcome

        # Act
        per_second = report["tile_count"] / clip.duration

        # Assert
        assert per_second <= clip.max_tiles_per_second
