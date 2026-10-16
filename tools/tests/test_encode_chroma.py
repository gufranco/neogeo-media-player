from __future__ import annotations

import numpy as np
import pytest

from neogeomedia import encode, palettes
from tests.encodehelp import noise_clip, options


@pytest.fixture(scope="module")
def unweighted_grid() -> np.ndarray:
    return palettes.oklab_grid()


@pytest.fixture(scope="module")
def full_chroma() -> encode.EncodeResult:
    return encode.encode(noise_clip(6), options(chroma_weight=1.0))


class TestChromaWeight:
    def test_the_grid_scales_only_the_chroma_axes(self, unweighted_grid):
        # Arrange
        weight = 0.25

        # Act
        weighted = palettes.oklab_grid(weight)

        # Assert
        assert np.allclose(weighted[:, 0], unweighted_grid[:, 0])
        assert np.allclose(weighted[:, 1:], unweighted_grid[:, 1:] * 0.5)

    def test_a_weight_of_one_is_the_unweighted_grid(self, unweighted_grid):
        # Arrange
        weight = 1.0

        # Act
        grid = palettes.oklab_grid(weight)

        # Assert
        assert grid is unweighted_grid

    def test_a_non_positive_weight_is_rejected(self):
        # Arrange
        weight = 0.0

        # Act
        with pytest.raises(ValueError, match="positive") as raised:
            palettes.oklab_grid(weight)

        # Assert
        assert "0.0" in str(raised.value)

    def test_cheaper_chroma_never_grows_the_dictionary(self, full_chroma):
        # Arrange
        clip = noise_clip(6)

        # Act
        result = encode.encode(clip, options(chroma_weight=0.1))

        # Assert
        assert len(result.dictionary) <= len(full_chroma.dictionary)


class TestEmptyAssignment:
    def test_rendering_an_empty_assignment_yields_no_tiles(self):
        # Arrange
        palette_set = palettes.PaletteSet(colors=np.zeros((2, 15), dtype=np.uint16), base_bank=16)
        assigner = palettes.PaletteAssigner(palette_set)
        assignment = assigner.assign(np.zeros((0, 16, 16), dtype=np.uint16))

        # Act
        rendered = assignment.rendered(palette_set)

        # Assert
        assert rendered.shape == (0, 16, 16)
