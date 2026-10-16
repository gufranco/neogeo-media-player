from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fmvcore.testing import SEED, seeded

from neogeomedia import frames
from tests.bakehelp import lavfi_clip
from tests.scripthelp import build_core, load_script

FRAMES = 40
HEIGHT = 224
WIDTH = 304
OVERSCAN_SIDE = 8
LAG = 3
FILM_SECONDS = 0.5
FILM_FRAMES = 29


@pytest.fixture(scope="module")
def compare():
    return load_script("compare_capture")


@pytest.fixture(scope="module")
def film_core(tmp_path_factory):
    return build_core("filmcore.c", tmp_path_factory.mktemp("filmcore"))


@pytest.fixture(scope="module")
def film(tmp_path_factory):
    path = tmp_path_factory.mktemp("film") / "film.mkv"
    return lavfi_clip(path, "testsrc2=size=320x224:rate=15625/264:duration=1")


@pytest.fixture
def source() -> np.ndarray:
    rng = np.random.default_rng(SEED)
    return rng.integers(0, 256, size=(FRAMES, HEIGHT, WIDTH, 3), dtype=np.uint8)


def delayed(source: np.ndarray, lag: int) -> np.ndarray:
    return np.concatenate([np.repeat(source[:1], lag, axis=0), source[:-lag]])


def late_cartridge(film: Path, out: Path, *, lead: int) -> Path:
    raster = frames.decode(film, start=0.0, duration=FILM_SECONDS)
    played = delayed(raster[:, :, OVERSCAN_SIDE : 320 - OVERSCAN_SIDE], LAG)
    boot = np.zeros((lead, HEIGHT, WIDTH, 3), dtype=np.uint8)
    out.write_bytes(np.concatenate([boot, played]).tobytes())
    return out


def compare_argv(film: Path, core: Path, cartridge: Path, *, lead: int) -> list[str]:
    return [
        *("--rom", str(cartridge), "--source", str(film), "--core", str(core)),
        *("--system-dir", str(cartridge.parent), "--duration", str(FILM_SECONDS)),
        *("--film-frame", str(lead)),
    ]


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


class TestTheCommand:
    def test_a_late_cartridge_reports_its_lag_and_no_error(
        self, compare, film_core, film, tmp_path, capsys
    ):
        # Arrange
        lead = seeded().random_int(1, 20)
        cartridge = late_cartridge(film, tmp_path / "late.rgb", lead=lead)

        # Act
        compare.main(compare_argv(film, film_core, cartridge, lead=lead))

        # Assert
        report = json.loads(capsys.readouterr().out)
        assert (report["frames"], report["lag_median_frames"]) == (FILM_FRAMES, LAG)
        assert (report["frame_error"], report["blurred_frame_error"]) == (0.0, 0.0)

    def test_the_report_is_also_written_where_asked(
        self, compare, film_core, film, tmp_path, capsys
    ):
        # Arrange
        cartridge = late_cartridge(film, tmp_path / "late.rgb", lead=1)
        written = tmp_path / "report" / "compare.json"
        written.parent.mkdir()
        argv = [*compare_argv(film, film_core, cartridge, lead=1), "--json", str(written)]

        # Act
        compare.main(argv)

        # Assert
        assert written.read_text() == capsys.readouterr().out

    def test_a_run_without_a_film_frame_is_refused(self, compare, film, capsys):
        # Arrange
        argv = ["--source", str(film), "--duration", str(FILM_SECONDS)]

        # Act
        with pytest.raises(SystemExit) as refused:
            compare.main(argv)

        # Assert
        assert refused.value.code == 2
        assert "the following arguments are required: --film-frame" in capsys.readouterr().err
