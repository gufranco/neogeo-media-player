from __future__ import annotations

import pytest

from neogeomedia import clips

CONTENT = {"synthetic", "3d-animation", "hand-drawn-cartoon", "live-action", "animals", "people"}


class TestTheManifest:
    def test_every_content_class_is_covered_once(self):
        # Arrange
        loader = clips.load

        # Act
        manifest = loader()

        # Assert
        assert sorted(clip.content for clip in manifest) == sorted(CONTENT)

    def test_every_key_is_unique(self):
        # Arrange
        loader = clips.load

        # Act
        manifest = loader()

        # Assert
        keys = [clip.key for clip in manifest]
        assert len(keys) == len(set(keys))

    def test_every_film_names_a_rung_and_its_ceilings(self):
        # Arrange
        loader = clips.load

        # Act
        manifest = loader()

        # Assert
        assert all(
            clip.quality and clip.max_error > 0 and clip.max_tiles_per_second > 0
            for clip in manifest
        )

    def test_the_committed_film_verifies_against_its_digest(self):
        # Arrange
        clip = clips.by_key("synthetic")

        # Act
        verdict = clips.verify(clips.path_of(clip), clip)

        # Assert
        assert verdict.ok


class TestLookups:
    def test_an_unknown_key_names_the_ones_that_exist(self):
        # Arrange
        key = "missing"

        # Act
        with pytest.raises(KeyError) as refused:
            clips.by_key(key)

        # Assert
        assert "missing is not in the manifest; it holds synthetic" in str(refused.value)

    def test_the_directory_follows_its_override(self, monkeypatch, tmp_path):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))

        # Act
        found = clips.directory()

        # Assert
        assert found == tmp_path

    def test_a_film_that_is_not_here_resolves_to_nothing(self, monkeypatch, tmp_path):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))

        # Act
        found = clips.resolve(clips.by_key("sintel-trailer"))

        # Assert
        assert found is None

    def test_required_reads_its_variable(self, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.REQUIRE_ENV, "1")

        # Act
        demanded = clips.required()

        # Assert
        assert demanded is True
