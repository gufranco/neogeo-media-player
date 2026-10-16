from __future__ import annotations

import pytest

from neogeomedia import bakeargs, cartridge, limits

SOURCE = ["--source", "clip.mp4"]


def refusal(parse, argv, capsys) -> str:
    with pytest.raises(SystemExit) as stopped:
        parse(argv)
    assert stopped.value.code == 2
    return capsys.readouterr().err


class TestTheBakeRefusesValuesOutsideTheirRange:
    @pytest.mark.parametrize(
        ("flag", "value", "message"),
        [
            ("--start", "-1", "--start must lie between 0 and 14400, got -1"),
            ("--duration", "0", "--duration must lie between"),
            ("--audio-rate", "60000", "--audio-rate must lie between 1850 and 55555.6, got 60000"),
            ("--denoise", "nan", "--denoise must lie between 0 and 64, got nan"),
            ("--frame-hold", "0", "--frame-hold must lie between 1 and 59, got 0"),
            ("--motion-blur", "2000", "--motion-blur must lie between 0 and 1024, got 2000"),
            ("--target-fps", "100", "--target-fps must lie between 1 and"),
            ("--motion-masking", "-0.5", "--motion-masking must lie between 0 and 4096, got -0.5"),
            ("--chroma-weight", "0", "--chroma-weight must lie between 0.001 and 16, got 0"),
            ("--scene-cut-floor", "2", "--scene-cut-floor must lie between 0 and 1, got 2"),
            ("--scene-cut-ratio", "1.5", "--scene-cut-ratio must lie between 0 and 1, got 1.5"),
            (
                "--palette-epoch-seconds",
                "-1",
                "--palette-epoch-seconds must lie between 0 and 14400",
            ),
            ("--tile-budget", "0", "--tile-budget must lie between 1 and 1048576, got 0"),
            ("--palette-count", "300", "--palette-count must lie between 1 and 256, got 300"),
            ("--base-bank", "256", "--base-bank must lie between 0 and 255, got 256"),
            ("--keyframe-interval", "0", "--keyframe-interval must lie between 1 and"),
            ("--tolerance", "inf", "--tolerance must lie between 0 and 1, got inf"),
            ("--candidates", "-1", "--candidates must lie between 0 and 256, got -1"),
            ("--sample-stride", "0", "--sample-stride must lie between 1 and"),
            ("--seed", "-3", "--seed must lie between 0 and 4294967295, got -3"),
            ("--frame-hold", "two", "--frame-hold must be a whole number, got 'two'"),
        ],
    )
    def test_a_value_out_of_range_names_the_flag_and_the_range(self, capsys, flag, value, message):
        # Arrange
        argv = [*SOURCE, flag, value]

        # Act
        complaint = refusal(bakeargs.parse_args, argv, capsys)

        # Assert
        assert message in complaint

    def test_values_inside_every_range_parse(self):
        # Arrange
        argv = [*SOURCE, "--start", "1.5", "--duration", "5", "--audio-rate", "22050"]

        # Act
        args = bakeargs.parse_args(argv)

        # Assert
        assert (args.start, args.duration, args.audio_rate) == (1.5, 5.0, 22050.0)


class TestTheCartridgeRefusesValuesOutsideTheirRange:
    def test_a_negative_start_is_refused(self, capsys):
        # Arrange
        argv = ["clip.mp4", "--start", "-2"]

        # Act
        complaint = refusal(cartridge._parse_args, argv, capsys)

        # Assert
        assert "--start must lie between 0 and 14400, got -2" in complaint

    def test_a_zero_duration_is_refused(self, capsys):
        # Arrange
        argv = ["clip.mp4", "--duration", "0"]

        # Act
        complaint = refusal(cartridge._parse_args, argv, capsys)

        # Assert
        assert "--duration must lie between" in complaint


class TestTheRanges:
    def test_the_shortest_window_is_one_vblank(self):
        # Arrange
        expected = 384 * 264 / 6_000_000

        # Act
        shortest = limits.MIN_SECONDS

        # Assert
        assert shortest == pytest.approx(expected)
