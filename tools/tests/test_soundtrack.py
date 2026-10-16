from __future__ import annotations

import subprocess

import pytest

from neogeomedia import adpcmb, soundtrack
from neogeomedia import frames as frames_mod


def _make_clip(path, *, with_tone: bool):
    tone = ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"] if with_tone else []
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=24:duration=1",
            *tone,
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture(scope="module")
def silent_clip(tmp_path_factory):
    return _make_clip(tmp_path_factory.mktemp("silent") / "silent.mp4", with_tone=False)


@pytest.fixture(scope="module")
def tone_clip(tmp_path_factory):
    return _make_clip(tmp_path_factory.mktemp("tone") / "tone.mp4", with_tone=True)


class TestDecode:
    def test_a_silent_source_decodes_to_an_empty_signal(self, silent_clip):
        # Arrange
        source = silent_clip

        # Act
        samples = soundtrack.decode_audio(source, 0.0, 0.5, 22050.0)

        # Assert
        assert samples.size == 0

    def test_a_tone_decodes_to_one_sample_per_tick_of_the_rate(self, tone_clip):
        # Arrange
        rate_hz = 8000.0

        # Act
        samples = soundtrack.decode_audio(tone_clip, 0.0, 0.5, rate_hz)

        # Assert
        assert samples.size == pytest.approx(4000, abs=64)
        assert int(abs(samples).max()) > 0


class TestVoice:
    def test_a_silent_source_bakes_no_voice(self, silent_clip, tmp_path):
        # Arrange
        baked = tmp_path / "baked"
        baked.mkdir()

        # Act
        voice = soundtrack.bake_voice(
            source=silent_clip,
            start=0.0,
            duration=0.5,
            rate_hz=22050.0,
            baked=baked,
            build_dir=tmp_path,
        )

        # Assert
        assert voice.path is None
        assert voice.pages == 0
        assert not (baked / "v2.bin").exists()

    def test_a_tone_bakes_a_voice_rom_and_its_register_values(self, tone_clip, tmp_path):
        # Arrange
        baked = tmp_path / "baked"
        baked.mkdir()

        # Act
        voice = soundtrack.bake_voice(
            source=tone_clip,
            start=0.0,
            duration=0.5,
            rate_hz=22050.0,
            baked=baked,
            build_dir=tmp_path,
        )

        # Assert
        assert voice.path == baked / "v2.bin"
        assert voice.path.stat().st_size == soundtrack.V_ROM_MIN_BYTES
        assert voice.pages == soundtrack.audio_pages_per_frame(adpcmb.delta_n_for(22050.0))
        assert (tmp_path / "generated" / "audio_params.s").is_file()


class TestRegisterValues:
    def test_every_register_is_split_into_its_two_bytes(self, tmp_path):
        # Arrange
        encoded = adpcmb.EncodedAudio(payload=bytes(0x1235 * 256), sample_count=1, delta_n=0xABCD)

        # Act
        path = soundtrack.write_audio_params(tmp_path, encoded)

        # Assert
        assert path.read_text() == (
            "    ADPCM_B_START_LO = 0x00\n"
            "    ADPCM_B_START_HI = 0x00\n"
            "    ADPCM_B_END_LO = 0x34\n"
            "    ADPCM_B_END_HI = 0x12\n"
            "    ADPCM_B_DELTA_LO = 0xcd\n"
            "    ADPCM_B_DELTA_HI = 0xab\n"
        )


class TestAudioVideoAlignment:
    def rate_and_pages(self):
        delta_n = adpcmb.delta_n_for(22050)
        return adpcmb.rate_for(delta_n), soundtrack.audio_pages_per_frame(delta_n)

    def test_a_silent_bake_reports_no_audio_advance(self):
        # Arrange
        delta_n = 0

        # Act
        pages = soundtrack.audio_pages_per_frame(delta_n)

        # Assert
        assert pages == 0

    def test_the_ratio_matches_the_sample_rate(self):
        # Arrange
        expected_rate = adpcmb.rate_for(adpcmb.delta_n_for(22050))

        # Act
        _, pages = self.rate_and_pages()

        # Assert
        assert float(pages) == pytest.approx(
            expected_rate / 512 / float(frames_mod.VBLANK_FPS), rel=1e-6
        )

    def test_audio_never_drifts_more_than_half_a_page_from_the_video(self):
        # Arrange
        frames = (0, 59, 1183, 3551, 60000, 106_000, 500_000)

        # Act
        rate, pages = self.rate_and_pages()

        # Assert
        half_page = 512 / rate / 2
        for frame in frames:
            page = (frame * pages.numerator + pages.denominator // 2) // pages.denominator
            drift = abs(page * 512 / rate - frame / float(frames_mod.VBLANK_FPS))
            assert drift <= half_page + 1e-9, frame

    def test_the_drift_does_not_grow_with_runtime(self):
        # Arrange
        def drift(frame, rate, pages):
            page = (frame * pages.numerator + pages.denominator // 2) // pages.denominator
            return abs(page * 512 / rate - frame / float(frames_mod.VBLANK_FPS))

        # Act
        rate, pages = self.rate_and_pages()

        # Assert
        assert drift(500_000, rate, pages) <= drift(1183, rate, pages) + 512 / rate

    def test_the_seek_granularity_is_one_page(self):
        # Arrange
        delta_n = adpcmb.delta_n_for(22050)

        # Act
        rate = adpcmb.rate_for(delta_n)

        # Assert
        assert 512 / rate == pytest.approx(0.0232, abs=0.001)
