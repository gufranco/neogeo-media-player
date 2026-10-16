from __future__ import annotations

import pytest

from neogeomedia import frames

FILL_CHAIN = "crop=960:720,scale=320:224:flags=lanczos,fps=15625/264,format=rgb24"
DENOISER = "hqdn3d=4:3:6:4.5"


def widescreen(fit: frames.FitMode = "fill") -> frames.Geometry:
    return frames.plan_geometry(1280, 720, 320, 224, fit=fit)


class TestFilterChain:
    def test_the_chain_crops_then_scales_then_resamples(self):
        # Arrange
        geometry = widescreen()

        # Act
        chain = frames.build_filter(geometry)

        # Assert
        assert chain == FILL_CHAIN
        assert chain.index("crop=") < chain.index("scale=") < chain.index("fps=")

    def test_the_chain_requests_packed_rgb_output(self):
        # Arrange
        geometry = widescreen()

        # Act
        chain = frames.build_filter(geometry)

        # Assert
        assert chain.endswith("format=rgb24")

    def test_a_filled_chain_carries_no_padding(self):
        # Arrange
        geometry = widescreen()

        # Act
        chain = frames.build_filter(geometry)

        # Assert
        assert "pad=" not in chain

    def test_a_letterboxed_chain_pads_to_the_raster(self):
        # Arrange
        geometry = widescreen("letterbox")

        # Act
        chain = frames.build_filter(geometry)

        # Assert
        assert "pad=320:224:0:32" in chain


class TestDenoise:
    def test_the_chain_has_no_denoiser_by_default(self):
        # Arrange
        geometry = widescreen()

        # Act
        chain = frames.build_filter(geometry)

        # Assert
        assert "hqdn3d" not in chain

    def test_a_positive_strength_inserts_the_denoiser(self):
        # Arrange
        geometry = widescreen()

        # Act
        chain = frames.build_filter(geometry, denoise=1.0)

        # Assert
        assert f",{DENOISER}," in chain

    def test_the_denoiser_runs_after_the_downscale_and_before_the_resample(self):
        # Arrange
        geometry = widescreen()

        # Act
        chain = frames.build_filter(geometry, denoise=1.0)

        # Assert
        assert chain.index("scale=") < chain.index("hqdn3d") < chain.index("fps=")

    def test_the_denoiser_runs_before_letterbox_padding(self):
        # Arrange
        geometry = widescreen("letterbox")

        # Act
        chain = frames.build_filter(geometry, denoise=1.0)

        # Assert
        assert chain.index("hqdn3d") < chain.index("pad=")

    @pytest.mark.parametrize(
        ("strength", "expected"),
        [(1.0, DENOISER), (2.0, "hqdn3d=8:6:12:9")],
        ids=["unit strength", "double strength"],
    )
    def test_strength_scales_every_term(self, strength, expected):
        # Arrange
        denoise = frames.Denoise()

        # Act
        rendered = denoise.scaled(strength).to_filter()

        # Assert
        assert rendered == expected


class TestMotionBlur:
    @pytest.mark.parametrize("motion_blur", [0, 1], ids=["by default", "a single frame"])
    def test_no_blur_is_added_without_a_window(self, motion_blur):
        # Arrange
        geometry = widescreen()

        # Act
        chain = frames.build_filter(geometry, motion_blur=motion_blur)

        # Assert
        assert chain == FILL_CHAIN

    def test_blur_averages_the_requested_frame_count(self):
        # Arrange
        geometry = widescreen()

        # Act
        chain = frames.build_filter(geometry, motion_blur=3)

        # Assert
        assert ",tmix=frames=3," in chain

    def test_blur_runs_before_the_frame_rate_resample(self):
        # Arrange
        geometry = widescreen()

        # Act
        chain = frames.build_filter(geometry, motion_blur=2)

        # Assert
        assert chain.index("tmix") < chain.index("fps=")


class TestDeinterlacing:
    @pytest.mark.parametrize(
        ("deinterlace", "present"),
        [(True, True), (False, False)],
        ids=["added when needed", "absent otherwise"],
    )
    def test_the_deinterlacer_is_only_added_when_needed(self, deinterlace, present):
        # Arrange
        geometry = frames.plan_geometry(640, 480)

        # Act
        chain = frames.build_filter(geometry, deinterlace=deinterlace)

        # Assert
        assert ("yadif=mode=0:parity=-1:deint=0" in chain) is present

    def test_the_deinterlacer_runs_before_the_scaler(self):
        # Arrange
        geometry = frames.plan_geometry(640, 480)

        # Act
        chain = frames.build_filter(geometry, deinterlace=True)

        # Assert
        assert chain.index("yadif") < chain.index("scale=")
