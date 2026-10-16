from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
from fmvcore.testing import seeded

from neogeomedia import clips

FAKE = seeded()
PRETEND_FILM = FAKE.binary(length=12)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "scripts" / "fetch_clips.py"


def load():
    spec = importlib.util.spec_from_file_location("fetch_clips", SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"cannot import {SCRIPT}"
        raise AssertionError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_clips"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fetcher():
    return load()


class TestTheScript:
    def test_it_exists(self):
        # Arrange
        script = SCRIPT

        # Act
        exists = script.is_file()

        # Assert
        assert exists is True

    def test_it_skips_a_committed_clip(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("synthetic")

        # Act
        outcome = fetcher.acquire(clip, download=_never)

        # Assert
        assert outcome.action == "committed"
        assert outcome.ok is True

    def test_an_absent_clip_lands_in_the_clips_directory(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("sintel-trailer")
        payload = PRETEND_FILM
        pinned = dataclasses.replace(
            clip, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()
        )

        # Act
        outcome = fetcher.acquire(
            pinned, download=lambda _url, target, _limit: target.write_bytes(payload)
        )

        # Assert
        assert (outcome.action, outcome.ok) == ("fetched", True)
        assert (tmp_path / clip.file).read_bytes() == payload

    def test_a_committed_clip_that_has_changed_is_refused(self, fetcher):
        # Arrange
        altered = dataclasses.replace(clips.by_key("synthetic"), sha256="0" * 64)

        # Act
        outcome = fetcher.acquire(altered, download=_never)

        # Assert
        assert outcome.ok is False

    def test_an_unknown_key_is_refused_by_name(self, fetcher, capsys):
        # Arrange
        argv = ["sintel-trailer", "no-such-film"]

        # Act
        code = fetcher.main(argv)

        # Assert
        assert code == 2
        assert "no-such-film" in capsys.readouterr().err


def _never(_url: str, _target: Path, _limit: int | None) -> None:
    msg = "this case must not download"
    raise AssertionError(msg)


class TestTheCommand:
    def test_a_committed_clip_is_ready_without_a_download(self, fetcher, capsys):
        # Arrange
        argv = ["synthetic"]

        # Act
        code = fetcher.main(argv)

        # Assert
        out = capsys.readouterr().out
        assert code == 0
        assert "1 of 1 clips are ready" in out
