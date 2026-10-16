from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from neogeomedia import encode, neocolor, preview


class TestPreviewCodec:
    def test_matroska_previews_are_lossless(self):
        # Arrange
        path = Path("out.mkv")

        # Act
        codec = preview.preview_codec(path)

        # Assert
        assert "ffv1" in codec

    def test_other_containers_use_h264(self):
        # Arrange
        path = Path("out.mp4")

        # Act
        codec = preview.preview_codec(path)

        # Assert
        assert "libx264" in codec


class TestPreviewWriter:
    def test_frames_written_come_back_out_of_a_lossless_preview(self, tmp_path):
        # Arrange
        rng = np.random.default_rng(7)
        shape = (encode.FRAME_HEIGHT, encode.FRAME_WIDTH)
        frame = rng.integers(0, 1 << 15, size=shape, dtype=np.uint16)
        path = tmp_path / "nested" / "preview.mkv"
        writer = preview.PreviewWriter(path)
        writer.write(frame)

        # Act
        writer.close()

        # Assert
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True,
            check=True,
        ).stdout
        decoded = np.frombuffer(raw, np.uint8).reshape(-1, *shape, 3)
        assert np.array_equal(decoded[0], neocolor.color_index_to_rgb(frame))

    def test_a_preview_ffmpeg_cannot_write_is_an_error(self, tmp_path):
        # Arrange
        writer = preview.PreviewWriter(tmp_path / "preview.not-a-container")

        # Act
        with pytest.raises(RuntimeError) as raised:
            writer.close()

        # Assert
        assert "preview.not-a-container" in str(raised.value)
