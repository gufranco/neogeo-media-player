from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from neogeomedia import adpcmb, soundtrack
from tests.bakehelp import tone_clip
from tests.scripthelp import load_script

measure_audio = load_script("measure_audio")

RATE = 18000.0
FULL = measure_audio.FULL_SCALE


def sine(frequency: float, samples: int, *, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(samples, dtype=np.float64) / RATE
    return (amplitude * np.sin(2.0 * np.pi * frequency * t) * FULL).astype(np.int16)


class TestLoudness:
    def test_a_half_scale_sine_reads_near_minus_nine_dbfs(self):
        # Arrange
        signal = sine(440.0, 8192, amplitude=0.5)

        # Act
        level = measure_audio.loudness_dbfs(signal)

        # Assert
        assert level == pytest.approx(-9.03, abs=0.2)

    def test_silence_reads_at_the_floor(self):
        # Arrange
        signal = np.zeros(0, dtype=np.int16)

        # Act
        level = measure_audio.loudness_dbfs(signal)

        # Assert
        assert level < -100.0


class TestSegmentalSnr:
    def test_identical_signals_read_at_the_ceiling(self):
        # Arrange
        signal = sine(440.0, 8192)

        # Act
        snr = measure_audio.segmental_snr_db(signal, signal)

        # Assert
        assert snr == pytest.approx(measure_audio.SNR_MAX)

    def test_a_pure_gain_change_does_not_lower_it(self):
        # Arrange
        reference = sine(440.0, 8192, amplitude=0.25)
        louder = (reference.astype(np.int32) * 2).astype(np.int16)

        # Act
        snr = measure_audio.segmental_snr_db(reference, louder)

        # Assert
        assert snr == pytest.approx(measure_audio.SNR_MAX)

    def test_added_noise_lowers_it(self):
        # Arrange
        reference = sine(440.0, 8192)
        generator = np.random.default_rng(0)
        noisy = np.clip(
            reference.astype(np.float64) + generator.normal(0, 0.1 * FULL, reference.size),
            -FULL,
            FULL,
        ).astype(np.int16)

        # Act
        snr = measure_audio.segmental_snr_db(reference, noisy)

        # Assert
        assert 0.0 < snr < measure_audio.SNR_MAX

    def test_no_overlap_reads_zero(self):
        # Arrange
        reference = np.zeros(0, dtype=np.int16)

        # Act
        snr = measure_audio.segmental_snr_db(reference, reference)

        # Assert
        assert snr == 0.0

    def test_a_silent_reference_reads_at_the_ceiling(self):
        # Arrange
        reference = np.zeros(4096, dtype=np.int16)
        test = sine(440.0, 4096)

        # Act
        snr = measure_audio.segmental_snr_db(reference, test)

        # Assert
        assert snr == pytest.approx(measure_audio.SNR_MAX)

    def test_a_silent_test_against_a_signal_reads_zero(self):
        # Arrange
        reference = sine(440.0, 4096)
        test = np.zeros(4096, dtype=np.int16)

        # Act
        snr = measure_audio.segmental_snr_db(reference, test)

        # Assert
        assert snr == pytest.approx(0.0, abs=0.01)


class TestMeasure:
    def test_it_reports_the_level_gain_and_fidelity(self):
        # Arrange
        source = sine(440.0, 8192, amplitude=0.25)
        output = (source.astype(np.float64) * 2.0).astype(np.int16)

        # Act
        report = measure_audio.measure(output, source)

        # Assert
        assert set(report) == {"output_dbfs", "source_dbfs", "gain_db", "snr_db", "samples"}

    def test_the_gain_matches_the_level_difference(self):
        # Arrange
        source = sine(440.0, 8192, amplitude=0.25)
        output = (source.astype(np.float64) * 2.0).astype(np.int16)

        # Act
        report = measure_audio.measure(output, source)

        # Assert
        assert report["gain_db"] == pytest.approx(6.02, abs=0.1)


@pytest.mark.ffmpeg
class TestOnFiles:
    def test_measure_files_reports_a_populated_dict(self, tmp_path: Path):
        # Arrange
        source = tone_clip(tmp_path / "tone.mp4")
        samples = soundtrack.decode_audio(source, 0.0, 1.0, RATE)
        rom = tmp_path / "v2.bin"
        rom.write_bytes(adpcmb.encode(samples, rate_hz=RATE).payload)

        # Act
        report = measure_audio.measure_files(rom, source, start=0.0, duration=1.0, rate=RATE)

        # Assert
        assert report["samples"] > 0 and report["snr_db"] > 0.0

    def test_main_prints_json_and_returns_zero(self, tmp_path: Path, capsys):
        # Arrange
        source = tone_clip(tmp_path / "tone.mp4")
        samples = soundtrack.decode_audio(source, 0.0, 1.0, RATE)
        rom = tmp_path / "v2.bin"
        rom.write_bytes(adpcmb.encode(samples, rate_hz=RATE).payload)
        argv = [
            "--rom",
            str(rom),
            "--source",
            str(source),
            "--duration",
            "1.0",
            "--rate",
            str(RATE),
        ]

        # Act
        code = measure_audio.main(argv)

        # Assert
        assert code == 0 and "snr_db" in json.loads(capsys.readouterr().out)
