from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from neogeomedia import bake
from tests.bakehelp import generated, small_request, tone_clip

_spec = importlib.util.spec_from_file_location(
    "verify_capture", Path(__file__).resolve().parents[1] / "scripts" / "verify_capture.py"
)
verify_capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_capture)


@pytest.fixture(scope="module")
def tone(tmp_path_factory):
    return tone_clip(tmp_path_factory.mktemp("tone") / "tone.mp4")


def decoded_frames(path: Path) -> np.ndarray:
    command = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(command, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 224, 320, 3)


class TestReport:
    def test_the_report_records_the_dictionary_size(self, baked):
        # Arrange
        expected = baked.result.stats.tile_count

        # Act
        report = baked.report()

        # Assert
        assert report["tile_count"] == expected

    def test_the_report_projects_a_feature_length_runtime(self, baked):
        # Arrange
        key = "projected_crom_bytes_per_minute"

        # Act
        report = baked.report()

        # Assert
        assert report[key] > 0

    def test_the_report_is_json_serializable(self, baked):
        # Arrange
        expected = baked.result.stats.frames

        # Act
        text = json.dumps(baked.report())

        # Assert
        assert json.loads(text)["frames"] == expected


class TestPreview:
    def test_it_can_render_a_preview_of_the_decoded_output(self, synthetic_clip, tmp_path):
        # Arrange
        preview = tmp_path / "preview.mp4"
        request = small_request(synthetic_clip, tmp_path / "build", duration=0.25, preview=preview)

        # Act
        bake.run(request)

        # Assert
        assert preview.stat().st_size > 0

    def test_a_lossless_preview_round_trips_the_rendered_picture(self, synthetic_clip, tmp_path):
        # Arrange
        preview = tmp_path / "lossless.mkv"
        request = small_request(
            synthetic_clip, tmp_path / "build", duration=0.1, palette_count=8, preview=preview
        )

        # Act
        outcome = bake.run(request)

        # Assert
        decoded = decoded_frames(preview)
        assert len(decoded) == outcome.result.stats.frames
        rebuilt = verify_capture.reconstruct_frame(outcome.build_dir / "baked", 3)
        assert np.array_equal(decoded[3], rebuilt)


class TestRenderCollection:
    def test_skipping_the_preview_skips_collecting_rendered_frames(self, synthetic_clip, tmp_path):
        # Arrange
        request = small_request(synthetic_clip, tmp_path / "build")

        # Act
        outcome = bake.run(request)

        # Assert
        assert outcome.result.rendered.shape[0] == 0

    def test_a_preview_is_written_without_holding_the_frames(self, synthetic_clip, tmp_path):
        # Arrange
        preview = tmp_path / "p.mkv"
        request = small_request(synthetic_clip, tmp_path / "build", preview=preview)

        # Act
        outcome = bake.run(request)

        # Assert
        assert outcome.result.rendered.shape[0] == 0
        assert preview.stat().st_size > 0


class TestAudio:
    def test_a_silent_source_bakes_without_a_voice_rom(self, synthetic_clip, tmp_path):
        # Arrange
        request = small_request(synthetic_clip, tmp_path / "build")

        # Act
        outcome = bake.run(request)

        # Assert
        assert "voice" not in outcome.artifacts
        assert not (outcome.build_dir / "baked" / "v2.bin").exists()

    def test_a_source_with_audio_produces_a_voice_rom(self, tone, tmp_path):
        # Arrange
        request = small_request(tone, tmp_path / "build", duration=0.3)

        # Act
        outcome = bake.run(request)

        # Assert
        assert (outcome.build_dir / "baked" / "v2.bin").is_file()

    def test_the_audio_parameters_are_emitted_for_the_z80(self, tone, tmp_path):
        # Arrange
        request = small_request(tone, tmp_path / "build", duration=0.3)

        # Act
        outcome = bake.run(request)

        # Assert
        params = generated(outcome, "audio_params.s")
        assert all(
            name in params for name in ("ADPCM_B_START_LO", "ADPCM_B_END_HI", "ADPCM_B_DELTA_LO")
        )

    def test_audio_can_be_switched_off(self, tone, tmp_path):
        # Arrange
        request = small_request(tone, tmp_path / "build", duration=0.3, audio=False)

        # Act
        outcome = bake.run(request)

        # Assert
        assert not (outcome.build_dir / "baked" / "v2.bin").exists()

    def test_the_header_carries_the_alignment_ratio(self, synthetic_clip, tmp_path):
        # Arrange
        request = small_request(synthetic_clip, tmp_path / "b")

        # Act
        outcome = bake.run(request)

        # Assert
        text = generated(outcome, "movie_data.h")
        assert "MOVIE_AUDIO_PAGE_NUM" in text
        assert "MOVIE_AUDIO_PAGE_DEN" in text


class TestTheOverlayNamesTheRungActuallyUsed:
    def test_a_resolved_rung_is_named_in_capitals(self):
        # Arrange
        request = small_request(Path("clip.mp4"), Path("build"), quality="q11")

        # Act
        name = bake.self_tier_name(request)

        # Assert
        assert name == "Q11"

    def test_a_bake_with_no_tier_is_named_custom(self):
        # Arrange
        request = small_request(Path("clip.mp4"), Path("build"), quality=None)

        # Act
        name = bake.self_tier_name(request)

        # Assert
        assert name == "CUSTOM"
