from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from fmvcore.testing import SEED

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
FRAMES = 40
HEIGHT = 224
WIDTH = 304
LAG = 3


@pytest.fixture(scope="module")
def compare():
    spec = importlib.util.spec_from_file_location("compare_capture", SCRIPTS / "compare_capture.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source() -> np.ndarray:
    rng = np.random.default_rng(SEED)
    return rng.integers(0, 256, size=(FRAMES, HEIGHT, WIDTH, 3), dtype=np.uint8)


def delayed(source: np.ndarray, lag: int) -> np.ndarray:
    return np.concatenate([np.repeat(source[:1], lag, axis=0), source[:-lag]])


class TestMeasure:
    def test_a_capture_three_frames_late_reports_that_lag(self, compare, source):
        # Arrange
        shown = delayed(source, LAG)

        # Act
        report = compare.measure(shown, source, rate=60.0, window=8)

        # Assert
        assert report["lag_median_frames"] == LAG

    def test_a_matched_capture_has_no_picture_error(self, compare, source):
        # Arrange
        shown = delayed(source, LAG)

        # Act
        report = compare.measure(shown, source, rate=60.0, window=8)

        # Assert
        assert (report["frame_error"], report["blurred_frame_error"]) == (0.0, 0.0)

    def test_the_lag_is_reported_in_seconds_at_the_given_rate(self, compare, source):
        # Arrange
        shown = delayed(source, LAG)

        # Act
        report = compare.measure(shown, source, rate=60.0, window=8)

        # Assert
        assert report["lag_median_s"] == pytest.approx(LAG / 60.0)

    def test_rows_under_the_panel_are_left_out(self, compare, source):
        # Arrange
        shown = delayed(source, LAG).copy()
        shown[:, compare.PANEL_TOP :] = 255

        # Act
        report = compare.measure(shown, source, rate=60.0, window=8)

        # Assert
        assert report["frame_error"] == 0.0


class TestCrop:
    def test_the_source_is_cropped_like_the_capture(self, compare):
        # Arrange
        raster = np.zeros((2, HEIGHT, 320, 3), dtype=np.uint8)

        # Act
        cropped = compare.crop_like_capture(raster, width=WIDTH)

        # Assert
        assert cropped.shape == (2, HEIGHT, WIDTH, 3)

    def test_a_capture_narrower_than_the_overscan_allows_is_refused(self, compare):
        # Arrange
        raster = np.zeros((2, HEIGHT, 320, 3), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            compare.crop_like_capture(raster, width=301)

        # Assert
        assert str(refused.value) == "a capture 301 pixels wide is not 320 less an even overscan"
