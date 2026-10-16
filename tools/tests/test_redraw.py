from __future__ import annotations

import numpy as np
import pytest

from neogeomedia import encode, neocolor, palettes, redraw, screen

SHAPE = (screen.GRID_ROWS, screen.GRID_COLS)
BLACK, WHITE = (
    int(index)
    for index in neocolor.rgb_to_color_index(np.array([[0, 0, 0], [255, 255, 255]], np.uint8))
)


def frame(colour: int) -> np.ndarray:
    return np.full((*SHAPE, 16, 16), colour, dtype=np.uint16)


@pytest.fixture
def blank_screen():
    tiles = np.full((4, 16, 16), BLACK, dtype=np.uint16)
    return screen.Screen(palettes.build_palette_set(tiles, count=1, base_bank=16, seed=0))


class TestSceneCuts:
    def test_the_first_frame_is_always_a_cut(self):
        # Arrange
        changed = np.ones(SHAPE, dtype=bool)

        # Act
        cut = redraw.is_scene_cut(frame(BLACK), None, changed, 0, encode.EncodeOptions())

        # Assert
        assert cut is True

    def test_a_frame_with_nothing_changed_is_not_a_cut(self):
        # Arrange
        changed = np.zeros(SHAPE, dtype=bool)

        # Act
        cut = redraw.is_scene_cut(frame(BLACK), frame(BLACK), changed, 5, encode.EncodeOptions())

        # Assert
        assert cut is False

    def test_a_picture_that_jumps_everywhere_is_a_cut(self):
        # Arrange
        changed = np.ones(SHAPE, dtype=bool)

        # Act
        cut = redraw.is_scene_cut(frame(WHITE), frame(BLACK), changed, 5, encode.EncodeOptions())

        # Assert
        assert cut is True


class TestTargets:
    def test_a_keyframe_redraws_every_slot_and_clears_the_backlog(self, blank_screen):
        # Arrange
        pending = np.ones(SHAPE, dtype=bool)

        # Act
        targets, owed = redraw.select_targets(
            frame(BLACK),
            frame(BLACK),
            np.zeros(SHAPE, dtype=bool),
            pending,
            screen=blank_screen,
            keyframe=True,
            options=encode.EncodeOptions(),
            tolerance=0.5,
        )

        # Assert
        assert bool(targets.all())
        assert not bool(owed.any())

    def test_a_zero_budget_redraws_every_changed_or_owed_slot(self, blank_screen):
        # Arrange
        changed = np.zeros(SHAPE, dtype=bool)
        changed[0, 0] = True
        pending = np.zeros(SHAPE, dtype=bool)
        pending[1, 1] = True

        # Act
        targets, owed = redraw.select_targets(
            frame(WHITE),
            frame(BLACK),
            changed,
            pending,
            screen=blank_screen,
            keyframe=False,
            options=encode.EncodeOptions(),
            tolerance=0.0,
        )

        # Assert
        assert np.array_equal(targets, changed | pending)
        assert not bool(owed.any())

    def test_a_drift_under_the_budget_stays_owed(self, blank_screen):
        # Arrange
        changed = np.zeros(SHAPE, dtype=bool)
        changed[0, 0] = True

        # Act
        targets, owed = redraw.select_targets(
            blank_screen.render.copy(),
            frame(WHITE),
            changed,
            np.zeros(SHAPE, dtype=bool),
            screen=blank_screen,
            keyframe=False,
            options=encode.EncodeOptions(),
            tolerance=0.5,
        )

        # Assert
        assert not bool(targets.any())
        assert np.array_equal(owed, changed)


class TestMasking:
    def test_no_masking_keeps_the_flat_threshold(self):
        # Arrange
        targets = np.ones(SHAPE, dtype=bool)

        # Act
        threshold = redraw.masked_threshold(
            frame(WHITE), frame(BLACK), targets, encode.EncodeOptions(), 0.25
        )

        # Assert
        assert threshold == 0.25

    def test_movement_raises_the_threshold(self):
        # Arrange
        targets = np.ones(SHAPE, dtype=bool)
        options = encode.EncodeOptions(motion_masking=1.0)

        # Act
        threshold = redraw.masked_threshold(frame(WHITE), frame(BLACK), targets, options, 0.25)

        # Assert
        assert isinstance(threshold, np.ndarray)
        assert bool(np.all(threshold > 0.25))
