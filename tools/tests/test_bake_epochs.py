from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from neogeomedia import bake, epochs, frames
from tests.bakehelp import lavfi_clip

pytestmark = pytest.mark.ffmpeg


@pytest.fixture(scope="module")
def cut_clip(tmp_path_factory):
    return lavfi_clip(
        tmp_path_factory.mktemp("cut") / "cut.mp4",
        "color=c=red:size=320x224:rate=24:duration=3",
        "color=c=blue:size=320x224:rate=24:duration=3",
        extra=("-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0"),
    )


def epoch_request(source: Path, build_dir: Path, *, duration: float, seconds: float):
    return bake.BakeRequest(
        source=source,
        start=0.0,
        duration=duration,
        build_dir=build_dir,
        palette_count=8,
        palette_epoch_seconds=seconds,
    )


class TestPaletteEpochFlag:
    def test_a_long_clip_is_split_into_several_epochs(self, epoch_clip, tmp_path):
        # Arrange
        request = epoch_request(epoch_clip, tmp_path / "many", duration=8.0, seconds=3.0)

        # Act
        outcome = bake.run(request)

        # Assert
        assert len(outcome.result.palette_sets) > 1

    def test_switching_epochs_off_leaves_one_palette_set(self, synthetic_clip, tmp_path):
        # Arrange
        request = epoch_request(synthetic_clip, tmp_path / "one", duration=1.0, seconds=0.0)

        # Act
        outcome = bake.run(request)

        # Assert
        assert len(outcome.result.palette_sets) == 1

    def test_the_epoch_table_names_every_epoch(self, synthetic_clip, tmp_path):
        # Arrange
        request = epoch_request(synthetic_clip, tmp_path / "table", duration=1.0, seconds=0.25)

        # Act
        outcome = bake.run(request)

        # Assert
        table = (outcome.build_dir / "baked" / "epochs.bin").read_bytes()
        assert len(table) == 4 * len(outcome.result.palette_sets)


class TestSceneAlignedEpochs:
    def test_an_epoch_begins_at_the_cut(self, cut_clip, tmp_path):
        # Arrange
        request = epoch_request(cut_clip, tmp_path / "aligned", duration=6.0, seconds=5.0)
        cut = round(3.0 * float(frames.VBLANK_FPS))

        # Act
        outcome = bake.run(request)

        # Assert
        stride = outcome.request.sample_stride
        assert any(abs(start - cut) <= stride for start in outcome.result.epoch_starts)

    def test_a_cadence_still_subdivides_a_long_scene(self, cut_clip, tmp_path):
        # Arrange
        request = epoch_request(cut_clip, tmp_path / "subdivided", duration=6.0, seconds=2.5)

        # Act
        outcome = bake.run(request)

        # Assert
        assert len(outcome.result.epoch_starts) > 1


class TestEpochsGiveTheLoaderTime:
    def test_no_epoch_is_shorter_than_the_upload_needs(self, synthetic_clip, tmp_path):
        # Arrange
        request = epoch_request(synthetic_clip, tmp_path / "spaced", duration=1.0, seconds=0.05)

        # Act
        outcome = bake.run(request)

        # Assert
        starts = outcome.result.epoch_starts
        gaps = [later - earlier for earlier, later in itertools.pairwise(starts)]
        assert all(gap >= epochs.epoch_upload_frames(8) for gap in gaps)

    def test_a_cadence_below_the_minimum_collapses_to_one_epoch(self, synthetic_clip, tmp_path):
        # Arrange
        request = epoch_request(synthetic_clip, tmp_path / "single", duration=1.0, seconds=0.01)

        # Act
        outcome = bake.run(request)

        # Assert
        assert len(outcome.result.epoch_starts) == 1
