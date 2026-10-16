from __future__ import annotations

import numpy as np
import pytest
from fmvcore.testing import SEED

from neogeomedia import encode
from tests.encodehelp import (
    HEIGHT,
    SLOT_COUNT,
    WIDTH,
    filler_colour,
    filler_colours,
    flat_clip,
    options,
    scene_cut_clip,
)

STILL = options(keyframe_interval=100)


def two_random_frames() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(SEED)
    first = rng.integers(0, 256, size=(HEIGHT, WIDTH, 3), dtype=np.uint8)
    second = rng.integers(0, 256, size=(HEIGHT, WIDTH, 3), dtype=np.uint8)
    return first, second


def one_slot_changed(count: int, *, from_frame: int, to_frame: int | None = None) -> np.ndarray:
    base = filler_colour()
    patch = tuple((channel + 128) % 256 for channel in base)
    clip = flat_clip(count, base)
    clip[from_frame:to_frame, 0:16, 0:16] = patch
    return clip


def gentle_drift(count: int) -> np.ndarray:
    clip = np.zeros((count, HEIGHT, WIDTH, 3), dtype=np.uint8)
    for index in range(count):
        clip[index, :, :] = (100 + 8 * index, 100, 100)
    return clip


@pytest.fixture(scope="module")
def drift_without_a_floor() -> encode.EncodeResult:
    return encode.encode(gentle_drift(6), options(keyframe_interval=100, scene_cut_floor=0.0))


@pytest.fixture(scope="module")
def two_frame_dictionary_size() -> int:
    first, second = two_random_frames()
    return len(encode.encode(np.stack([first, second]), STILL).dictionary)


class TestFrameCadence:
    def test_the_stream_holds_one_record_per_source_frame(self):
        # Arrange
        clip = flat_clip(12, filler_colour())

        # Act
        result = encode.encode(clip, options())

        # Assert
        assert len(result.stream) == 12

    def test_the_first_frame_is_always_a_keyframe(self):
        # Arrange
        clip = flat_clip(4, filler_colour())

        # Act
        result = encode.encode(clip, options())

        # Assert
        assert list(result.stream.keyframes()) == [0]

    def test_keyframes_follow_the_requested_interval(self):
        # Arrange
        clip = flat_clip(20, filler_colour())

        # Act
        result = encode.encode(clip, options(keyframe_interval=8))

        # Assert
        assert list(result.stream.keyframes()) == [0, 8, 16]

    def test_a_keyframe_rewrites_every_slot(self):
        # Arrange
        clip = flat_clip(9, filler_colour())

        # Act
        result = encode.encode(clip, options(keyframe_interval=8))

        # Assert
        assert result.updates_per_frame[8] == SLOT_COUNT

    def test_a_static_clip_emits_no_deltas_between_keyframes(self):
        # Arrange
        clip = flat_clip(6, filler_colour())

        # Act
        result = encode.encode(clip, STILL)

        # Assert
        assert list(result.updates_per_frame[1:]) == [0] * 5


class TestDictionary:
    def test_a_flat_clip_needs_a_single_tile_and_reports_it(self):
        # Arrange
        clip = flat_clip(6, filler_colour())

        # Act
        result = encode.encode(clip, options())

        # Assert
        assert len(result.dictionary) == 1
        assert result.stats.tile_count == 1

    def test_uniform_frames_cost_at_most_one_tile_per_colour(self):
        # Arrange
        first, second = filler_colours(2)
        clip = np.concatenate([flat_clip(3, first), flat_clip(3, second)])

        # Act
        result = encode.encode(clip, STILL)

        # Assert
        assert len(result.dictionary) <= 2

    def test_content_returning_to_an_earlier_frame_adds_no_tiles(self, two_frame_dictionary_size):
        # Arrange
        first, second = two_random_frames()
        clip = np.stack([first, second, first])

        # Act
        result = encode.encode(clip, STILL)

        # Assert
        assert len(result.dictionary) == two_frame_dictionary_size


class TestDeltas:
    def test_changing_one_slot_emits_one_update(self):
        # Arrange
        clip = one_slot_changed(3, from_frame=1)

        # Act
        result = encode.encode(clip, STILL)

        # Assert
        assert result.updates_per_frame[1] == 1

    def test_a_reverted_slot_emits_again(self):
        # Arrange
        clip = one_slot_changed(4, from_frame=1, to_frame=2)

        # Act
        result = encode.encode(clip, STILL)

        # Assert
        assert list(result.updates_per_frame) == [SLOT_COUNT, 1, 1, 0]

    def test_a_duplicated_source_frame_costs_nothing(self):
        # Arrange
        clip = flat_clip(4, filler_colour())

        # Act
        result = encode.encode(clip, STILL)

        # Assert
        assert result.stats.delta_bytes == 6


class TestValidation:
    def test_an_empty_clip_is_rejected(self):
        # Arrange
        clip = np.zeros((0, HEIGHT, WIDTH, 3), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError, match="empty") as raised:
            encode.encode(clip, options())

        # Assert
        assert str(raised.value) == "cannot encode an empty clip"

    def test_a_wrongly_sized_clip_is_rejected(self):
        # Arrange
        clip = np.zeros((2, 100, 100, 3), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError, match="320x224") as raised:
            encode.encode(clip, options())

        # Assert
        assert "(100, 100, 3)" in str(raised.value)


class TestSceneCuts:
    def test_a_full_frame_change_forces_a_keyframe(self):
        # Arrange
        clip = scene_cut_clip()

        # Act
        result = encode.encode(clip, options(keyframe_interval=100, scene_cut_ratio=0.5))

        # Assert
        assert list(result.stream.keyframes()) == [0, 3]

    def test_a_small_change_does_not_force_a_keyframe(self):
        # Arrange
        clip = one_slot_changed(6, from_frame=3)

        # Act
        result = encode.encode(clip, options(keyframe_interval=100, scene_cut_ratio=0.5))

        # Assert
        assert list(result.stream.keyframes()) == [0]


class TestSceneCutFloor:
    def test_a_shade_everywhere_is_not_a_scene_cut(self):
        # Arrange
        clip = gentle_drift(6)

        # Act
        result = encode.encode(clip, options(keyframe_interval=100, scene_cut_floor=0.01))

        # Assert
        assert list(result.stream.keyframes()) == [0]

    def test_a_floor_of_zero_reads_the_same_drift_as_a_cut(self):
        # Arrange
        clip = gentle_drift(6)

        # Act
        result = encode.encode(clip, options(keyframe_interval=100, scene_cut_floor=0.0))

        # Assert
        assert len(result.stream.keyframes()) > 1

    def test_a_real_jump_still_forces_a_keyframe(self):
        # Arrange
        clip = scene_cut_clip()

        # Act
        result = encode.encode(clip, options(keyframe_interval=100, scene_cut_floor=0.01))

        # Assert
        assert list(result.stream.keyframes()) == [0, 3]

    def test_the_floor_cuts_the_dictionary_on_drifting_content(self, drift_without_a_floor):
        # Arrange
        clip = gentle_drift(6)

        # Act
        result = encode.encode(clip, options(keyframe_interval=100, scene_cut_floor=0.01))

        # Assert
        assert len(result.dictionary) < len(drift_without_a_floor.dictionary)
