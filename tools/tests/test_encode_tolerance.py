from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from fmvcore.testing import SEED

from neogeomedia import encode
from tests.encodehelp import HEIGHT, WIDTH, filler_colour, flat_clip, noise_clip, options

GREY = (100, 100, 100)
PROBE = (200, 40, 40)


def drifting_slot(shade: int) -> np.ndarray:
    clip = flat_clip(3, GREY)
    clip[1:, 0:16, 0:16] = (shade, 100, 100)
    return clip


def half_moving(count: int) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    clip = np.zeros((count, HEIGHT, WIDTH, 3), dtype=np.uint8)
    clip[:, :, WIDTH // 2 :] = rng.integers(0, 256, size=(HEIGHT, WIDTH // 2, 3), dtype=np.uint8)
    clip[:, :, : WIDTH // 2] = rng.integers(
        0, 256, size=(count, HEIGHT, WIDTH // 2, 3), dtype=np.uint8
    )
    return clip


def probed_still(count: int) -> np.ndarray:
    clip = flat_clip(count, GREY)
    clip[1:, 0:16, 0:16] = PROBE
    return clip


def drifting_corner(count: int) -> np.ndarray:
    clip = flat_clip(count, GREY)
    for index in range(count):
        clip[index, 0:16, 0:16] = (100 + 12 * index, 100, 100)
    return clip


def masking(**extra: Any) -> encode.EncodeOptions:
    return options(keyframe_interval=1000, scene_cut_ratio=1.1, tolerance=0.0005, **extra)


@pytest.fixture(scope="module")
def unmasked() -> encode.EncodeResult:
    return encode.encode(half_moving(6), masking())


@pytest.fixture(scope="module")
def lightly_masked() -> encode.EncodeResult:
    return encode.encode(half_moving(6), masking(motion_masking=5.0))


@pytest.fixture(scope="module")
def keen() -> encode.EncodeResult:
    return encode.encode(drifting_corner(8), options(keyframe_interval=1000, tolerance=0.0))


@pytest.fixture(scope="module")
def live() -> encode.EncodeResult:
    return encode.encode(drifting_corner(8), options(keyframe_interval=1000, frame_hold=1))


class TestTolerance:
    @pytest.mark.parametrize(
        ("shade", "tolerance", "updates"),
        [(120, 0.0005, 1), (120, 0.002, 0), (120, 0.0005, 1), (200, 0.0, 1)],
        ids=[
            "the probe change survives colour quantization",
            "a tolerance above the change suppresses it",
            "a tolerance below the change keeps it",
            "zero tolerance keeps every visible change",
        ],
    )
    def test_the_tolerance_decides_whether_a_slot_is_rewritten(self, shade, tolerance, updates):
        # Arrange
        clip = drifting_slot(shade)

        # Act
        result = encode.encode(clip, options(keyframe_interval=100, tolerance=tolerance))

        # Assert
        assert result.updates_per_frame[1] == updates

    def test_a_suppressed_slot_leaves_the_earlier_picture_on_screen(self):
        # Arrange
        clip = drifting_slot(120)

        # Act
        result = encode.encode(clip, options(keyframe_interval=100, tolerance=0.002))

        # Assert
        assert np.array_equal(result.rendered[1], result.rendered[0])


class TestMotionMasking:
    def test_masking_off_reproduces_the_flat_threshold(self, unmasked):
        # Arrange
        clip = half_moving(6)

        # Act
        result = encode.encode(clip, masking(motion_masking=0.0))

        # Assert
        assert list(result.updates_per_frame) == list(unmasked.updates_per_frame)

    def test_masking_shrinks_the_dictionary_and_the_slot_updates(self, unmasked):
        # Arrange
        clip = half_moving(6)

        # Act
        result = encode.encode(clip, masking(motion_masking=20.0))

        # Assert
        assert len(result.dictionary) < len(unmasked.dictionary)
        assert result.updates_per_frame[3] < unmasked.updates_per_frame[3]

    def test_an_error_hidden_by_motion_is_repaired_once_motion_stops(self):
        # Arrange
        clip = probed_still(4)

        # Act
        result = encode.encode(clip, masking(motion_masking=20.0))

        # Assert
        assert result.updates_per_frame[1] == 0
        assert result.updates_per_frame[2] == 1

    def test_a_still_region_is_never_left_wrong(self):
        # Arrange
        clip = probed_still(6)

        # Act
        result = encode.encode(clip, masking(motion_masking=20.0))

        # Assert
        assert np.array_equal(result.rendered[5], result.rendered[4])
        assert int(result.updates_per_frame[3:].sum()) == 0

    def test_a_bigger_masking_factor_saves_more(self, lightly_masked):
        # Arrange
        clip = half_moving(6)

        # Act
        result = encode.encode(clip, masking(motion_masking=40.0))

        # Assert
        assert len(result.dictionary) <= len(lightly_masked.dictionary)


class TestDisplayedError:
    def test_skipping_work_is_reported_as_worse_not_better(self, keen):
        # Arrange
        clip = drifting_corner(8)

        # Act
        lazy = encode.encode(clip, options(keyframe_interval=1000, tolerance=0.05))

        # Assert
        assert lazy.stats.displayed_error > keen.stats.displayed_error

    def test_holding_a_frame_is_charged_against_the_true_source(self, live):
        # Arrange
        clip = drifting_corner(8)

        # Act
        held = encode.encode(clip, options(keyframe_interval=1000, frame_hold=4))

        # Assert
        assert held.stats.displayed_error > live.stats.displayed_error

    def test_an_exact_reproduction_reports_no_error(self):
        # Arrange
        clip = flat_clip(4, filler_colour())

        # Act
        result = encode.encode(clip, options())

        # Assert
        assert result.stats.displayed_error == pytest.approx(0.0, abs=1e-6)


class TestBlurredError:
    def test_a_flat_clip_the_palette_holds_exactly_scores_zero(self):
        # Arrange
        clip = flat_clip(4, (0, 0, 0))

        # Act
        result = encode.encode(clip, options())

        # Assert
        assert result.stats.blurred_error == 0.0

    def test_a_clip_with_more_colours_than_the_palettes_scores_above_zero(self):
        # Arrange
        clip = noise_clip(2)

        # Act
        result = encode.encode(clip, options())

        # Assert
        assert result.stats.blurred_error > 0.0
