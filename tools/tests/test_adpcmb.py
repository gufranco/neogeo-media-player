from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest
from fmvcore.testing import SEED

from neogeomedia import adpcmb

STEP_SCALE = (57, 57, 57, 57, 77, 102, 128, 153)
STEP_MIN = 127
STEP_MAX = 24576
CEILING_MESSAGE = "must be above 0 and at most 55555.555555555555 Hz"


class YmfmDecoder:
    def __init__(self) -> None:
        self.accumulator = 0
        self.step = STEP_MIN

    def nibble(self, data: int) -> int:
        delta = (2 * (data & 7) + 1) * self.step // 8
        if data & 8:
            delta = -delta
        self.accumulator = max(-32768, min(32767, self.accumulator + delta))
        self.step = max(STEP_MIN, min(STEP_MAX, (self.step * STEP_SCALE[data & 7]) // 64))
        return self.accumulator

    def decode(self, payload: bytes) -> np.ndarray:
        out = []
        for byte in payload:
            out.append(self.nibble((byte >> 4) & 0x0F))
            out.append(self.nibble(byte & 0x0F))
        return np.array(out, dtype=np.int32)


def sine(count: int, cycles: float, amplitude: int = 20000) -> np.ndarray:
    t = np.linspace(0.0, cycles * 2.0 * np.pi, count, endpoint=False)
    return (np.sin(t) * amplitude).astype(np.int16)


def noise(count: int) -> np.ndarray:
    return np.random.default_rng(SEED).integers(-20000, 20000, size=count, dtype=np.int16)


class TestDeltaN:
    def test_the_rate_register_follows_the_chip_accumulator(self):
        # Arrange
        rate = adpcmb.BASE_RATE_HZ

        # Act
        delta_n = adpcmb.delta_n_for(rate)

        # Assert
        assert delta_n == 65535

    def test_the_unity_step_is_the_accumulator_wrap(self):
        # Arrange
        module = adpcmb

        # Act
        unity = module.DELTA_N_UNITY

        # Assert
        assert unity == 0x10000

    def test_the_chip_rate_is_the_clock_over_the_divider(self):
        # Arrange
        module = adpcmb

        # Act
        rate = float(module.CHIP_RATE_HZ)

        # Assert
        assert rate == pytest.approx(55555.5556, abs=0.001)

    def test_the_exact_rate_is_a_ratio(self):
        # Arrange
        delta_n = 26011

        # Act
        rate = adpcmb.exact_rate(delta_n)

        # Assert
        assert type(rate) is Fraction
        assert rate == Fraction(406421875, 18432)

    def test_a_common_rate_lands_close_to_the_request(self):
        # Arrange
        delta_n = adpcmb.delta_n_for(22050)

        # Act
        rate = adpcmb.rate_for(delta_n)

        # Assert
        assert rate == pytest.approx(22050, abs=2)

    def test_the_register_stays_inside_sixteen_bits(self):
        # Arrange
        rate = 55555

        # Act
        delta_n = adpcmb.delta_n_for(rate)

        # Assert
        assert 0 < delta_n <= 0xFFFF

    @pytest.mark.parametrize("rate", [60000, 0])
    def test_a_rate_outside_the_chip_range_is_rejected(self, rate):
        # Arrange
        expected = f"rate {rate} {CEILING_MESSAGE}"

        # Act
        with pytest.raises(ValueError) as raised:
            adpcmb.delta_n_for(rate)

        # Assert
        assert str(raised.value) == expected


class TestEncoding:
    @pytest.mark.parametrize("count", [512, 511])
    def test_two_samples_pack_into_one_byte_padded_to_a_whole_byte(self, count):
        # Arrange
        source = sine(count, 2.0)

        # Act
        encoded = adpcmb.encode(source)

        # Assert
        assert len(encoded.payload) == 256

    def test_the_high_nibble_holds_the_earlier_sample(self):
        # Arrange
        source = np.array([20000, 20000], dtype=np.int16)

        # Act
        encoded = adpcmb.encode(source)

        # Assert
        assert (encoded.payload[0] >> 4) & 0x08 == 0

    @pytest.mark.parametrize("count", [512, 300])
    def test_silence_and_its_padding_tail_stay_at_the_smallest_steps(self, count):
        # Arrange
        source = np.zeros(count, dtype=np.int16)

        # Act
        encoded = adpcmb.encode(source)

        # Assert
        decoded = YmfmDecoder().decode(encoded.payload)
        assert int(np.abs(decoded).max()) < 200

    def test_a_sine_reconstructs_within_a_few_percent(self):
        # Arrange
        source = sine(4096, 16.0)

        # Act
        encoded = adpcmb.encode(source)

        # Assert
        decoded = YmfmDecoder().decode(encoded.payload)[: len(source)]
        assert np.abs(decoded - source.astype(np.int32)).mean() < 0.05 * 20000

    def test_a_loud_sine_does_not_clip_the_accumulator(self):
        # Arrange
        source = sine(2048, 8.0, amplitude=32000)

        # Act
        encoded = adpcmb.encode(source)

        # Assert
        decoded = YmfmDecoder().decode(encoded.payload)[: len(source)]
        assert np.abs(decoded - source.astype(np.int32)).mean() < 0.08 * 32000

    def test_a_step_change_is_tracked_within_a_few_samples(self):
        # Arrange
        source = np.concatenate([np.zeros(32, dtype=np.int16), np.full(224, 15000, dtype=np.int16)])

        # Act
        encoded = adpcmb.encode(source)

        # Assert
        decoded = YmfmDecoder().decode(encoded.payload)[: len(source)]
        assert abs(int(decoded[-1]) - 15000) < 1500

    def test_encoding_is_deterministic(self):
        # Arrange
        source = noise(512)
        first = adpcmb.encode(source).payload

        # Act
        second = adpcmb.encode(source)

        # Assert
        assert second.payload == first

    def test_an_empty_signal_is_rejected(self):
        # Arrange
        source = np.zeros(0, dtype=np.int16)

        # Act
        with pytest.raises(ValueError) as raised:
            adpcmb.encode(source)

        # Assert
        assert str(raised.value) == "cannot encode an empty signal"

    def test_a_stereo_signal_is_rejected(self):
        # Arrange
        source = np.zeros((64, 2), dtype=np.int16)

        # Act
        with pytest.raises(ValueError) as raised:
            adpcmb.encode(source)

        # Assert
        assert str(raised.value) == "audio must be mono, got shape (64, 2)"


class TestRomLayout:
    def test_the_rom_pads_to_the_requested_size_with_the_payload_in_front(self):
        # Arrange
        encoded = adpcmb.encode(sine(1024, 4.0))

        # Act
        rom = adpcmb.build_rom(encoded, pad_to=65536)

        # Assert
        assert len(rom) == 65536
        assert rom[:512] == encoded.payload

    def test_addresses_are_reported_in_the_chip_s_units(self):
        # Arrange
        source = sine(2048, 4.0)

        # Act
        encoded = adpcmb.encode(source)

        # Assert
        assert (encoded.start_address, encoded.end_address) == (0, 3)

    def test_the_payload_is_padded_to_a_page_boundary(self):
        # Arrange
        source = sine(300, 2.0)

        # Act
        encoded = adpcmb.encode(source)

        # Assert
        assert len(encoded.payload) == 256

    def test_a_rom_smaller_than_the_payload_is_rejected(self):
        # Arrange
        encoded = adpcmb.encode(sine(4096, 4.0))

        # Act
        with pytest.raises(ValueError) as raised:
            adpcmb.build_rom(encoded, pad_to=256)

        # Assert
        assert str(raised.value) == "pad_to 256 is smaller than the 2048 byte payload"

    def test_the_sixteen_mebibyte_ceiling_is_enforced(self):
        # Arrange
        encoded = adpcmb.encode(sine(512, 2.0))

        # Act
        with pytest.raises(ValueError) as raised:
            adpcmb.build_rom(encoded, pad_to=(16 << 20) + 256)

        # Assert
        assert str(raised.value) == "ADPCM-B holds at most 16 MiB, asked for 16777472 bytes"


class TestAdaptiveRates:
    RATES = (8000.0, 11025.0, 16000.0, 17600.0, 20000.0, 22050.0)

    def signal(self, rate_hz: float) -> np.ndarray:
        count = int(rate_hz)
        t = np.arange(count) / rate_hz
        tone = 12000 * np.sin(2 * np.pi * 440 * t) + 5000 * np.sin(2 * np.pi * 1970 * t)
        return tone.astype(np.int16)

    @pytest.mark.parametrize("rate_hz", RATES)
    def test_it_reproduces_the_signal(self, rate_hz):
        # Arrange
        source = self.signal(rate_hz)

        # Act
        encoded = adpcmb.encode(source, rate_hz=rate_hz)

        # Assert
        decoded = YmfmDecoder().decode(encoded.payload)[: source.size]
        matrix = np.corrcoef(source.astype(np.float64), decoded.astype(np.float64))
        assert float(matrix[0, 1]) > 0.99

    @pytest.mark.parametrize("rate_hz", RATES)
    def test_the_rate_register_lands_within_a_hundred_ppm(self, rate_hz):
        # Arrange
        delta_n = adpcmb.delta_n_for(rate_hz)

        # Act
        actual = adpcmb.rate_for(delta_n)

        # Assert
        assert abs(actual - rate_hz) / rate_hz < 1e-4


class TestDecode:
    def test_it_matches_the_reference_decoder(self):
        # Arrange
        payload = adpcmb.encode(sine(512, 4.0), rate_hz=18000.0).payload

        # Act
        decoded = adpcmb.decode(payload, sample_count=512)

        # Assert
        assert np.array_equal(decoded, YmfmDecoder().decode(payload)[:512].astype(np.int16))

    def test_it_tracks_an_encoded_sine(self):
        # Arrange
        samples = sine(1024, 8.0)

        # Act
        decoded = adpcmb.decode(adpcmb.encode(samples, rate_hz=18000.0).payload, sample_count=1024)

        # Assert
        assert np.corrcoef(decoded.astype(np.float64), samples.astype(np.float64))[0, 1] > 0.99

    def test_it_stops_at_the_sample_count(self):
        # Arrange
        payload = adpcmb.encode(noise(300), rate_hz=18000.0).payload

        # Act
        decoded = adpcmb.decode(payload, sample_count=300)

        # Assert
        assert decoded.size == 300

    def test_it_rejects_a_negative_sample_count(self):
        # Arrange
        payload = adpcmb.encode(sine(64, 2.0), rate_hz=18000.0).payload

        # Act
        with pytest.raises(ValueError) as raised:
            adpcmb.decode(payload, sample_count=-1)

        # Assert
        assert "sample_count" in str(raised.value)
