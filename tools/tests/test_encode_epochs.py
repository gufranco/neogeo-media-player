from __future__ import annotations

import numpy as np
import pytest
from fmvcore.testing import SEED

from neogeomedia import encode, neocolor
from tests.encodehelp import HEIGHT, WIDTH, noise_clip, options

EpochSamples = list[tuple[int, np.ndarray]]


def two_scenes(count: int) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    warm = rng.integers(0, 90, size=(count // 2, HEIGHT, WIDTH, 3), dtype=np.uint8)
    warm[..., 0] += 160
    cool = rng.integers(0, 90, size=(count - count // 2, HEIGHT, WIDTH, 3), dtype=np.uint8)
    cool[..., 2] += 160
    return np.concatenate([warm, cool])


def four_scenes(per_scene: int) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    scenes = []
    for channel, boost in ((0, 150), (1, 150), (2, 150), (0, 60)):
        block = rng.integers(0, 80, size=(per_scene, HEIGHT, WIDTH, 3), dtype=np.uint8)
        block[..., channel] = np.minimum(255, block[..., channel] + boost)
        scenes.append(block)
    return np.concatenate(scenes)


def epochs_every(clip: np.ndarray, frames_per_epoch: int) -> EpochSamples:
    tiles = encode.to_tiles(neocolor.rgb_to_color_index(clip))
    return [
        (start, tiles[start : start + frames_per_epoch].reshape(-1, 16, 16))
        for start in range(0, clip.shape[0], frames_per_epoch)
    ]


def encode_epochs(clip: np.ndarray, epochs: EpochSamples, palette_count: int):
    return encode.encode_stream(
        [clip],
        options(palette_count=palette_count),
        sample_tiles=epochs[0][1],
        epoch_samples=epochs,
        total_frames=clip.shape[0],
    )


def bank_halves(result: encode.EncodeResult) -> list[int]:
    return [palette_set.base_bank for palette_set in result.palette_sets]


@pytest.fixture(scope="module")
def shared_four_scenes() -> encode.EncodeResult:
    return encode.encode(four_scenes(3), options(palette_count=16))


class TestPaletteEpochs:
    def test_each_epoch_gets_its_own_palette_set_in_the_other_half(self):
        # Arrange
        clip = two_scenes(8)
        epochs = epochs_every(clip, 4)

        # Act
        result = encode_epochs(clip, epochs, palette_count=8)

        # Assert
        assert len(result.palette_sets) == 2
        assert bank_halves(result) == [16, 20]

    def test_each_epoch_starts_on_a_keyframe(self):
        # Arrange
        clip = two_scenes(8)
        epochs = epochs_every(clip, 4)

        # Act
        result = encode_epochs(clip, epochs, palette_count=8)

        # Assert
        assert 4 in list(result.stream.keyframes())

    def test_refitting_per_scene_beats_one_shared_set(self, shared_four_scenes):
        # Arrange
        clip = four_scenes(3)
        epochs = epochs_every(clip, 3)

        # Act
        result = encode_epochs(clip, epochs, palette_count=16)

        # Assert
        assert result.stats.displayed_error < shared_four_scenes.stats.displayed_error

    def test_epochs_never_share_dictionary_entries(self):
        # Arrange
        clip = two_scenes(8)
        epochs = epochs_every(clip, 4)

        # Act
        result = encode_epochs(clip, epochs, palette_count=8)

        # Assert
        assert result.stats.tile_count > 0
        assert result.stats.dictionary_full is False


class TestEpochSchedule:
    def test_it_reports_where_each_epoch_starts(self):
        # Arrange
        clip = noise_clip(12)
        epochs = epochs_every(clip, 3)

        # Act
        result = encode_epochs(clip, epochs, palette_count=8)

        # Assert
        assert list(result.epoch_starts) == [0, 3, 6, 9]

    def test_consecutive_epochs_alternate_between_the_two_halves(self):
        # Arrange
        clip = noise_clip(12)
        epochs = epochs_every(clip, 3)

        # Act
        result = encode_epochs(clip, epochs, palette_count=8)

        # Assert
        assert bank_halves(result) == [16, 20, 16, 20]

    def test_a_single_epoch_encode_keeps_the_whole_allocation(self):
        # Arrange
        clip = noise_clip(4)

        # Act
        result = encode.encode(clip, options(palette_count=8))

        # Assert
        assert len(result.palette_sets) == 1
        assert len(result.palette_sets[0]) == 8


class TestSingleEpochAllocation:
    def test_one_epoch_keeps_every_palette(self):
        # Arrange
        clip = noise_clip(4)
        epochs = epochs_every(clip, 4)

        # Act
        result = encode_epochs(clip, epochs, palette_count=8)

        # Assert
        assert len(result.palette_sets[0]) == 8
