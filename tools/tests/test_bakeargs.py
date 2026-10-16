from __future__ import annotations

import argparse
import subprocess

import pytest
from fmvcore import ffmpeg

from neogeomedia import bakeargs, content, quality

SOURCE = ["--source", "clip.mp4", "--duration", "1"]


@pytest.fixture(scope="module")
def synthetic_clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("bakeargs") / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=24:duration=1",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


def namespace(source, **extra):
    base = {"quality": None, "source": source, "start": 0.0, "duration": 1.0, "fit": "fill"}
    return argparse.Namespace(**{**base, **extra})


class TestSourceDefaults:
    def test_the_duration_defaults_to_the_rest_of_the_source(self, synthetic_clip):
        # Arrange
        args = bakeargs.parse_args(["--source", str(synthetic_clip)])

        # Act
        resolved = bakeargs.resolve_duration(args)

        # Assert
        assert resolved == pytest.approx(ffmpeg.probe(synthetic_clip).duration, abs=0.05)

    def test_an_explicit_duration_still_wins(self, synthetic_clip):
        # Arrange
        args = bakeargs.parse_args(["--source", str(synthetic_clip), "--duration", "0.25"])

        # Act
        resolved = bakeargs.resolve_duration(args)

        # Assert
        assert resolved == pytest.approx(0.25)

    def test_a_start_offset_shortens_the_default_duration(self, synthetic_clip):
        # Arrange
        args = bakeargs.parse_args(["--source", str(synthetic_clip), "--start", "0.4"])
        full = ffmpeg.probe(synthetic_clip).duration

        # Act
        resolved = bakeargs.resolve_duration(args)

        # Assert
        assert resolved == pytest.approx(full - 0.4, abs=0.05)


class TestCommandLine:
    def test_default_arguments_target_the_full_palette_bank_allocation(self):
        # Arrange
        argv = SOURCE

        # Act
        args = bakeargs.parse_args(argv)

        # Assert
        assert (args.palette_count, args.base_bank) == (240, 16)

    def test_flip_dedup_is_off_unless_switched_on(self):
        # Arrange
        argv = SOURCE

        # Act
        args = bakeargs.parse_args(argv)

        # Assert
        assert args.flip is False

    def test_flip_dedup_can_be_switched_on(self):
        # Arrange
        argv = [*SOURCE, "--flip"]

        # Act
        args = bakeargs.parse_args(argv)

        # Assert
        assert args.flip is True

    def test_the_defaults_are_the_measured_settings(self):
        # Arrange
        argv = SOURCE

        # Act
        args = bakeargs.parse_args(argv)

        # Assert
        assert (args.scene_cut_ratio, args.keyframe_interval) == (0.90, 90)

    def test_a_tier_controlled_knob_is_unset_until_resolved(self):
        # Arrange
        argv = SOURCE

        # Act
        args = bakeargs.parse_args(argv)

        # Assert
        assert (args.tolerance, args.chroma_weight, args.frame_hold, args.denoise) == (
            None,
            None,
            None,
            None,
        )

    def test_no_bundle_is_written_unless_asked_for(self):
        # Arrange
        argv = SOURCE

        # Act
        args = bakeargs.parse_args(argv)

        # Assert
        assert args.bundle is None

    def test_the_bundle_flag_takes_a_directory(self, tmp_path):
        # Arrange
        argv = [*SOURCE, "--bundle", str(tmp_path)]

        # Act
        args = bakeargs.parse_args(argv)

        # Assert
        assert args.bundle == tmp_path

    def test_epochs_are_on_by_default(self):
        # Arrange
        argv = SOURCE

        # Act
        args = bakeargs.parse_args(argv)

        # Assert
        assert args.palette_epoch_seconds is None
        assert content.epoch_seconds_for(cuts_per_minute=6.0) > 0.0

    def test_epochs_can_be_switched_off(self):
        # Arrange
        argv = [*SOURCE, "--palette-epoch-seconds", "0"]

        # Act
        args = bakeargs.parse_args(argv)

        # Assert
        assert args.palette_epoch_seconds == 0.0


class TestPick:
    def test_an_unset_knob_falls_back_to_the_built_in_default(self):
        # Arrange
        fallback = 0.0005

        # Act
        picked = bakeargs.pick(None, None, fallback)

        # Assert
        assert picked == fallback

    def test_a_tier_value_beats_the_built_in_default(self):
        # Arrange
        tier_value = 0.25

        # Act
        picked = bakeargs.pick(None, tier_value, 1.0)

        # Assert
        assert picked == tier_value

    def test_an_explicit_flag_beats_the_tier(self):
        # Arrange
        explicit = 0.9

        # Act
        picked = bakeargs.pick(explicit, 0.25, 1.0)

        # Assert
        assert picked == explicit


class TestQualityResolution:
    def test_no_quality_flag_selects_no_tier(self, synthetic_clip):
        # Arrange
        args = namespace(synthetic_clip)

        # Act
        tier = bakeargs.resolve_quality(args)

        # Assert
        assert tier is None

    def test_a_named_tier_is_returned(self, synthetic_clip):
        # Arrange
        args = namespace(synthetic_clip, quality="q14")

        # Act
        tier = bakeargs.resolve_quality(args)

        # Assert
        assert tier is not None
        assert tier.name == "q14"

    def test_an_older_tier_name_still_resolves(self, synthetic_clip):
        # Arrange
        args = namespace(synthetic_clip, quality="long")

        # Act
        tier = bakeargs.resolve_quality(args)

        # Assert
        assert tier is quality.tier_by_name("long")

    def test_an_unknown_tier_is_rejected(self, synthetic_clip):
        # Arrange
        args = namespace(synthetic_clip, quality="cinematic")

        # Act
        with pytest.raises(ValueError, match="unknown quality tier") as raised:
            bakeargs.resolve_quality(args)

        # Assert
        assert "cinematic" in str(raised.value)

    def test_auto_is_refused_and_says_where_to_go(self, synthetic_clip):
        # Arrange
        args = namespace(synthetic_clip, quality="auto")

        # Act
        with pytest.raises(SystemExit) as raised:
            bakeargs.resolve_quality(args)

        # Assert
        assert "search" in str(raised.value)
        assert "plan" in str(raised.value)


class TestFrameHold:
    def test_no_hold_anywhere_is_a_hold_of_one(self, synthetic_clip):
        # Arrange
        args = namespace(synthetic_clip, frame_hold=None, target_fps=None)

        # Act
        hold = bakeargs.resolve_frame_hold(args, None)

        # Assert
        assert hold == 1

    def test_a_hold_that_drops_source_frames_is_kept(self, synthetic_clip):
        # Arrange
        args = namespace(synthetic_clip, frame_hold=4, target_fps=None)

        # Act
        hold = bakeargs.resolve_frame_hold(args, None)

        # Assert
        assert hold == 4

    def test_a_target_rate_replaces_the_hold(self, synthetic_clip):
        # Arrange
        args = namespace(synthetic_clip, frame_hold=None, target_fps=12.0)

        # Act
        hold = bakeargs.resolve_frame_hold(args, None)

        # Assert
        assert hold == 5

    def test_a_hold_that_drops_nothing_is_refused_with_the_smallest_useful_one(
        self, synthetic_clip
    ):
        # Arrange
        args = namespace(synthetic_clip, frame_hold=2, target_fps=None)

        # Act
        with pytest.raises(SystemExit) as raised:
            bakeargs.resolve_frame_hold(args, None)

        # Assert
        assert "Use a hold of 3 or more" in str(raised.value)


class TestMeasuredSettings:
    def test_explicit_flags_skip_every_measurement_but_the_profile(self, synthetic_clip, capsys):
        # Arrange
        args = namespace(
            synthetic_clip, scene_cut_floor=0.02, palette_epoch_seconds=2.0, sample_stride=3
        )

        # Act
        measured = bakeargs.measured_settings(args)

        # Assert
        assert measured == bakeargs.Measured(
            scene_cut_floor=0.02, palette_epoch_seconds=2.0, sample_stride=3
        )
        assert "palette sample every 3 frames" in capsys.readouterr().err

    def test_unset_flags_are_measured_from_the_source(self, synthetic_clip):
        # Arrange
        args = namespace(
            synthetic_clip, scene_cut_floor=None, palette_epoch_seconds=None, sample_stride=None
        )

        # Act
        measured = bakeargs.measured_settings(args)

        # Assert
        assert measured.scene_cut_floor == content.movement_floor(synthetic_clip)
        assert measured.palette_epoch_seconds > 0.0
        assert measured.sample_stride >= 1
