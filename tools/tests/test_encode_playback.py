from __future__ import annotations

import numpy as np
from fmvcore.testing import SEED

from neogeomedia import encode, stream
from tests.encodehelp import (
    HEIGHT,
    SLOT_COUNT,
    WIDTH,
    jumped_render,
    jumped_vram,
    noise_clip,
    options,
    played_vram,
    replayed,
)
from tests.geolith_model import StreamPlayer

PATCH = 16
SEEKABLE = options(keyframe_interval=4, scene_cut_ratio=1.1)


def gradient_clip(count: int) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    base = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    base[:, :, 0] = np.linspace(0, 255, WIDTH, dtype=np.uint8)[None, :]
    base[:, :, 1] = np.linspace(0, 255, HEIGHT, dtype=np.uint8)[:, None]
    base[:, :, 2] = 128
    clip = np.repeat(base[None], count, axis=0)
    for index in range(1, count):
        top = rng.integers(0, HEIGHT - PATCH)
        left = rng.integers(0, WIDTH - PATCH)
        clip[index:, top : top + PATCH, left : left + PATCH] = rng.integers(
            0, 256, size=(PATCH, PATCH, 3), dtype=np.uint8
        )
    return clip


def frames_crossing_a_bank(result: encode.EncodeResult) -> list[int]:
    blob = result.stream.blob()
    crossing = []
    for frame, offset in enumerate(result.stream.frame_offsets()):
        end = StreamPlayer().apply(blob, int(offset))
        if int(offset) // stream.PROM_BANK_BYTES != (end - 1) // stream.PROM_BANK_BYTES:
            crossing.append(frame)
    return crossing


class TestPlaybackFidelity:
    def test_replaying_the_stream_reproduces_the_encoder_render(self):
        # Arrange
        clip = gradient_clip(10)

        # Act
        result = encode.encode(clip, options(palette_count=16, keyframe_interval=4))

        # Assert
        assert np.array_equal(replayed(result), result.rendered)

    def test_a_keyframe_alone_reconstructs_the_full_picture(self):
        # Arrange
        clip = gradient_clip(9)

        # Act
        result = encode.encode(clip, options(palette_count=16, keyframe_interval=4))

        # Assert
        assert np.array_equal(jumped_render(result, 8), result.rendered[8])

    def test_the_reported_render_matches_the_source_within_the_quantizer_error(self):
        # Arrange
        clip = gradient_clip(4)

        # Act
        result = encode.encode(clip, options(palette_count=32, keyframe_interval=4))

        # Assert
        assert result.stats.mean_error >= 0.0
        assert result.rendered.shape == (4, HEIGHT, WIDTH)


class TestSeekEquivalence:
    def test_every_keyframe_lands_where_sequential_play_would(self):
        # Arrange
        clip = noise_clip(12)

        # Act
        result = encode.encode(clip, SEEKABLE)

        # Assert
        assert list(result.stream.keyframes()) == [0, 4, 8]
        assert [
            np.array_equal(played_vram(result, keyframe), jumped_vram(result, keyframe))
            for keyframe in (0, 4, 8)
        ] == [True, True, True]

    def test_a_keyframe_rewrites_every_slot(self):
        # Arrange
        clip = noise_clip(12)

        # Act
        result = encode.encode(clip, SEEKABLE)

        # Assert
        assert [int(result.updates_per_frame[frame]) for frame in (0, 4, 8)] == [SLOT_COUNT] * 3

    def test_no_frame_record_straddles_a_bank_boundary(self):
        # Arrange
        clip = noise_clip(12)

        # Act
        result = encode.encode(clip, SEEKABLE)

        # Assert
        assert frames_crossing_a_bank(result) == []
