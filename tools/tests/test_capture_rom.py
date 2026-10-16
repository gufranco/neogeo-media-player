from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fmvcore.testing import seeded

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TEST_CORE = (
    Path(__file__).resolve().parents[2] / "fmv-core-python" / "tests" / "fixtures" / "testcore.c"
)
SUFFIX = ".dylib" if sys.platform == "darwin" else ".so"
CORE_ANSWERS = 0x80 | 0x40 | 0x20 | 0x10 | 0x04 | 0x02


@pytest.fixture(scope="module")
def capture_rom():
    spec = importlib.util.spec_from_file_location("capture_rom", SCRIPTS / "capture_rom.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def core(tmp_path_factory):
    if shutil.which("cc") is None:
        reason = "cc not on the path, and this test builds a libretro core"
        if os.environ.get("NEOGEOMEDIA_CC_REQUIRED") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    built = tmp_path_factory.mktemp("core") / f"testcore{SUFFIX}"
    subprocess.run(["cc", "-shared", "-fPIC", "-O1", "-o", str(built), str(TEST_CORE)], check=True)
    return built


@pytest.fixture
def cartridge(tmp_path):
    fake = seeded()
    path = tmp_path / "film.neo"
    path.write_bytes(bytes([fake.random_int(1, 200), 0, 0, 0]))
    return path


def decoded(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.uint8)


class TestOptions:
    def test_the_universe_bios_is_always_chosen(self, capture_rom):
        # Arrange
        full_raster = False

        # Act
        options = capture_rom.core_options(full_raster=full_raster)

        # Assert
        assert options == {"geolith_system_type": "uni"}

    def test_a_full_raster_turns_every_overscan_crop_off(self, capture_rom):
        # Arrange
        full_raster = True

        # Act
        options = capture_rom.core_options(full_raster=full_raster)

        # Assert
        assert options == {
            "geolith_system_type": "uni",
            "geolith_overscan_t": "0",
            "geolith_overscan_b": "0",
            "geolith_overscan_l": "0",
            "geolith_overscan_r": "0",
        }


class TestPng:
    @pytest.mark.ffmpeg
    def test_the_written_png_decodes_to_the_same_pixels(self, capture_rom, tmp_path):
        # Arrange
        fake = seeded()
        frame = np.array(
            [[[fake.random_int(0, 255) for _ in range(3)] for _ in range(5)] for _ in range(3)],
            dtype=np.uint8,
        )
        out = tmp_path / "frame.png"

        # Act
        capture_rom.write_png(out, frame)

        # Assert
        assert decoded(out).tolist() == frame.reshape(-1).tolist()


class TestCapture:
    @pytest.mark.ffmpeg
    def test_the_last_frame_of_the_run_is_saved(self, capture_rom, core, cartridge, tmp_path):
        # Arrange
        out = tmp_path / "shot" / "last.png"
        seed = cartridge.read_bytes()[0]
        argv = ["--frames", "2", "--rom", str(cartridge), "--core", str(core)]

        # Act
        capture_rom.main([*argv, "--system-dir", str(tmp_path), "--out", str(out)])

        # Assert
        assert decoded(out)[:3].tolist() == [seed + 1, 0, CORE_ANSWERS]

    def test_a_missing_cartridge_is_named(self, capture_rom, core, tmp_path):
        # Arrange
        absent = tmp_path / "absent.neo"
        argv = ["--rom", str(absent), "--core", str(core), "--system-dir", str(tmp_path)]

        # Act
        with pytest.raises(FileNotFoundError) as refused:
            capture_rom.main(argv)

        # Assert
        assert str(refused.value) == f"no content at {absent}"

    def test_a_run_of_no_frames_is_refused(self, capture_rom):
        # Arrange
        argv = ["--frames", "0"]

        # Act
        with pytest.raises(SystemExit) as refused:
            capture_rom.main(argv)

        # Assert
        assert refused.value.code == 2


class TestHeldButtons:
    def test_a_hold_maps_neo_geo_buttons_to_geolith_bindings(self, capture_rom):
        # Arrange
        text = "40:a+start"

        # Act
        held = capture_rom.parse_hold(text)

        # Assert
        assert held == (40, frozenset({capture_rom.Joypad.B, capture_rom.Joypad.START}))

    def test_an_unknown_button_is_refused(self, capture_rom):
        # Arrange
        text = "40:z"

        # Act
        with pytest.raises(capture_rom.argparse.ArgumentTypeError) as refused:
            capture_rom.parse_hold(text)

        # Assert
        assert str(refused.value) == (
            "unknown button 'z'; use a, b, c, d, down, left, right, select, start, up"
        )

    def test_a_hold_without_a_frame_is_refused(self, capture_rom):
        # Arrange
        text = "start"

        # Act
        with pytest.raises(capture_rom.argparse.ArgumentTypeError) as refused:
            capture_rom.parse_hold(text)

        # Assert
        assert str(refused.value) == "a hold reads FRAME:BUTTON[+BUTTON], got 'start'"

    @pytest.mark.ffmpeg
    def test_held_buttons_reach_the_core(self, capture_rom, core, cartridge, tmp_path):
        # Arrange
        out = tmp_path / "held.png"
        argv = ["--frames", "2", "--rom", str(cartridge), "--core", str(core)]

        # Act
        capture_rom.main([*argv, "--system-dir", str(tmp_path), "--out", str(out), "--hold", "1:c"])

        # Assert
        assert decoded(out)[1] == 1 << capture_rom.Joypad.Y


class TestSavedFrames:
    def test_each_saved_frame_is_written_beside_the_output(
        self, capture_rom, core, cartridge, tmp_path
    ):
        # Arrange
        out = tmp_path / "shot.png"
        argv = ["--frames", "3", "--rom", str(cartridge), "--core", str(core)]

        # Act
        capture_rom.main(
            [*argv, "--system-dir", str(tmp_path), "--out", str(out), "--save", "0", "--save", "1"]
        )

        # Assert
        assert sorted(p.name for p in tmp_path.glob("shot*.png")) == [
            "shot-00000.png",
            "shot-00001.png",
            "shot.png",
        ]
