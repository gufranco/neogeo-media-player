from __future__ import annotations

import numpy as np
import pytest

from neogeomedia import palettes, screen
from neogeomedia.dictionary import TileDictionary

TILE = 16


@pytest.fixture
def palette_set():
    rng = np.random.default_rng(11)
    tiles = rng.integers(0, 1 << 15, size=(64, TILE, TILE), dtype=np.uint16)
    return palettes.build_palette_set(tiles, count=4, base_bank=16, seed=0)


@pytest.fixture
def placed(palette_set):
    rng = np.random.default_rng(12)
    tiles = rng.integers(0, 1 << 15, size=(2, TILE, TILE), dtype=np.uint16)
    assignment = palettes.PaletteAssigner(palette_set).assign(tiles)
    refs = TileDictionary().intern_batch(assignment.nibbles)
    return tiles, assignment, refs


class TestAFreshScreen:
    def test_it_shows_no_tile_anywhere(self, palette_set):
        # Arrange
        shape = (screen.GRID_ROWS, screen.GRID_COLS)

        # Act
        shown = screen.Screen(palette_set)

        # Assert
        assert shown.tile.shape == shape
        assert bool(np.all(shown.tile == screen.EMPTY_TILE))


class TestCommit:
    def test_a_new_tile_is_sent_with_its_palette_bank(self, palette_set, placed):
        # Arrange
        _, assignment, refs = placed
        shown = screen.Screen(palette_set)

        # Act
        updates = shown.commit(np.array([0, 3]), np.array([1, 5]), refs, assignment, force=False)

        # Assert
        assert [(u.row, u.col, u.tile) for u in updates] == [(0, 1, 0), (3, 5, 1)]
        assert [u.palette for u in updates] == [
            16 + int(assignment.palette_ids[0]),
            16 + int(assignment.palette_ids[1]),
        ]

    def test_a_slot_already_showing_the_tile_is_not_sent_again(self, palette_set, placed):
        # Arrange
        _, assignment, refs = placed
        shown = screen.Screen(palette_set)
        shown.commit(np.array([0, 3]), np.array([1, 5]), refs, assignment, force=False)

        # Act
        updates = shown.commit(np.array([0, 3]), np.array([1, 5]), refs, assignment, force=False)

        # Assert
        assert updates == []

    def test_a_forced_commit_resends_an_unchanged_slot(self, palette_set, placed):
        # Arrange
        _, assignment, refs = placed
        shown = screen.Screen(palette_set)
        shown.commit(np.array([0, 3]), np.array([1, 5]), refs, assignment, force=False)

        # Act
        updates = shown.commit(np.array([0, 3]), np.array([1, 5]), refs, assignment, force=True)

        # Assert
        assert len(updates) == 2

    def test_a_tile_the_dictionary_refused_leaves_its_slot_alone(self, palette_set, placed):
        # Arrange
        _, assignment, refs = placed
        shown = screen.Screen(palette_set)

        # Act
        updates = shown.commit(
            np.array([0, 3]), np.array([1, 5]), [None, refs[1]], assignment, force=False
        )

        # Assert
        assert [(u.row, u.col) for u in updates] == [(3, 5)]
        assert int(shown.tile[0, 1]) == screen.EMPTY_TILE


class TestFidelity:
    def test_a_source_matching_the_screen_scores_zero(self, palette_set, placed):
        # Arrange
        _, assignment, refs = placed
        shown = screen.Screen(palette_set)
        shown.commit(np.array([0, 3]), np.array([1, 5]), refs, assignment, force=False)
        source = shown.render.copy()

        # Act
        error = shown.fidelity(source)

        # Assert
        assert error == 0.0

    def test_drift_is_zero_only_where_the_screen_matches(self, palette_set, placed):
        # Arrange
        tiles, assignment, refs = placed
        shown = screen.Screen(palette_set)
        shown.commit(np.array([0]), np.array([1]), refs[:1], assignment, force=False)
        source = shown.render.copy()
        source[2, 2] = tiles[1]
        targets = np.zeros((screen.GRID_ROWS, screen.GRID_COLS), dtype=bool)
        targets[0, 1] = targets[2, 2] = True

        # Act
        drift = shown.drift(source, targets)

        # Assert
        assert float(drift[0]) == 0.0
        assert float(drift[1]) > 0.0
