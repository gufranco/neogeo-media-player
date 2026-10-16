from __future__ import annotations

from fractions import Fraction

import pytest

from neogeomedia import frames


def displayed_aspect(geometry: frames.Geometry) -> float:
    width, height = geometry.image
    return (width / height) * frames.PIXEL_ASPECT


class TestVblankRate:
    def test_the_vblank_rate_matches_the_neo_geo_raster(self):
        # Arrange
        pixel_clock, line_pixels, frame_lines = 6_000_000, 384, 264

        # Act
        rate = frames.VBLANK_FPS

        # Assert
        assert rate == Fraction(pixel_clock, line_pixels * frame_lines)

    def test_the_vblank_rate_is_the_documented_frequency(self):
        # Arrange
        documented = 59.1856

        # Act
        rate = float(frames.VBLANK_FPS)

        # Assert
        assert rate == pytest.approx(documented, abs=1e-4)


class TestFrameCount:
    @pytest.mark.parametrize(
        ("seconds", "count"),
        [(1.0, 59), (20.0, 1183)],
        ids=["one second follows the vblank rate", "twenty seconds fill the frame budget"],
    )
    def test_frame_count_follows_the_vblank_rate(self, seconds, count):
        # Arrange
        duration = seconds

        # Act
        frame_total = frames.frame_count(seconds=duration)

        # Assert
        assert frame_total == count


class TestFillGeometry:
    @pytest.mark.parametrize(
        ("source", "crop"),
        [((1280, 720), (960, 720)), ((720, 1280), (720, 540)), ((640, 480), (640, 480))],
        ids=[
            "a wider source is cropped horizontally",
            "a taller source is cropped vertically",
            "a matching aspect is not cropped",
        ],
    )
    def test_fill_crops_the_source_to_the_displayed_aspect(self, source, crop):
        # Arrange
        width, height = source

        # Act
        geometry = frames.plan_geometry(width, height, 320, 224)

        # Assert
        assert geometry.crop == crop
        assert geometry.crop[0] <= width
        assert geometry.crop[1] <= height

    def test_fill_uses_the_whole_target_frame(self):
        # Arrange
        width, height = 1280, 720

        # Act
        geometry = frames.plan_geometry(width, height, 320, 224)

        # Assert
        assert geometry.image == (320, 224)

    def test_crop_dimensions_stay_even(self):
        # Arrange
        width, height = 1281, 721

        # Act
        geometry = frames.plan_geometry(width, height, 320, 224)

        # Assert
        assert geometry.crop == (960, 720)
        assert geometry.crop[0] % 2 == 0
        assert geometry.crop[1] % 2 == 0


class TestFrameHoldPlanning:
    @pytest.mark.parametrize(("target", "hold"), [(59.2, 1), (29.6, 2), (15.0, 4)])
    def test_a_target_rate_maps_to_the_nearest_hold(self, target, hold):
        # Arrange
        target_fps = target

        # Act
        chosen = frames.hold_for_target_fps(target_fps)

        # Assert
        assert chosen == hold

    def test_a_non_positive_target_is_rejected(self):
        # Arrange
        target = 0.0

        # Act
        with pytest.raises(ValueError, match="positive") as raised:
            frames.hold_for_target_fps(target)

        # Assert
        assert "0.0" in str(raised.value)

    @pytest.mark.parametrize(
        ("hold", "source_fps", "kept"),
        [(2, 24, 1.0), (4, 24, 0.616517), (3, 24, 0.822022), (3, 30, 0.657618)],
        ids=[
            "a hold above the source cadence keeps every frame",
            "a hold below the source cadence drops frames",
            "a hold of three on a film source",
            "a faster source makes the same hold drop more",
        ],
    )
    def test_the_share_of_source_frames_kept_follows_the_hold(self, hold, source_fps, kept):
        # Arrange
        rate = Fraction(source_fps)

        # Act
        share = frames.source_frames_kept(hold, rate)

        # Assert
        assert share == pytest.approx(kept, abs=1e-6)


class TestDisplayAspect:
    def test_a_widescreen_source_keeps_its_shape(self):
        # Arrange
        width, height = 1280, 720

        # Act
        geometry = frames.plan_geometry(width, height)

        # Assert
        assert geometry.crop[0] / geometry.crop[1] == pytest.approx(
            displayed_aspect(geometry), rel=1e-3
        )

    def test_a_four_by_three_source_is_not_cropped_sideways(self):
        # Arrange
        width, height = 640, 480

        # Act
        geometry = frames.plan_geometry(width, height)

        # Assert
        assert geometry.crop[0] == 640

    def test_the_crop_is_narrower_than_the_raster_ratio(self):
        # Arrange
        raster_ratio = 320 / 224

        # Act
        geometry = frames.plan_geometry(1280, 720)

        # Assert
        assert geometry.crop[0] / geometry.crop[1] < raster_ratio

    def test_the_pixel_aspect_follows_from_a_four_by_three_screen(self):
        # Arrange
        screen_aspect, raster_width, raster_height = 4 / 3, 320, 224

        # Act
        aspect = frames.PIXEL_ASPECT

        # Assert
        assert aspect == pytest.approx(screen_aspect * raster_height / raster_width)
