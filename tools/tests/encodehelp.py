from __future__ import annotations

from typing import Any

import numpy as np
from fmvcore.testing import SEED

from neogeomedia import crom, encode
from tests.geolith_model import GeolithTileReader, StreamPlayer

HEIGHT = 224
WIDTH = 320
SLOT_COUNT = 20 * 14
RED = (200, 0, 0)
GREEN = (0, 200, 0)

Colour = tuple[int, int, int]


def flat_clip(count: int, colour: Colour) -> np.ndarray:
    clip = np.zeros((count, HEIGHT, WIDTH, 3), dtype=np.uint8)
    clip[:, :, :] = colour
    return clip


def filler_colours(count: int) -> list[Colour]:
    rng = np.random.default_rng(SEED)
    picks = rng.integers(0, 256, size=(count, 3))
    return [(int(red), int(green), int(blue)) for red, green, blue in picks]


def filler_colour() -> Colour:
    return filler_colours(1)[0]


def noise_clip(count: int) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    return rng.integers(0, 256, size=(count, HEIGHT, WIDTH, 3), dtype=np.uint8)


def scene_cut_clip() -> np.ndarray:
    return np.concatenate([flat_clip(3, RED), flat_clip(3, GREEN)])


def options(**overrides: Any) -> encode.EncodeOptions:
    base: dict[str, Any] = {
        "palette_count": 4,
        "base_bank": 16,
        "keyframe_interval": 8,
        "candidates": 0,
        "sample_stride": 1,
        "seed": 5,
    }
    return encode.EncodeOptions(**{**base, **overrides})


def tile_reader(result: encode.EncodeResult) -> GeolithTileReader:
    c1, c2 = crom.pack_tiles(result.dictionary.tiles())
    return GeolithTileReader(c1, c2)


def render(result: encode.EncodeResult, player: StreamPlayer, reader: GeolithTileReader):
    return player.render(reader, result.palette_set.colors, result.palette_set.base_bank)


def replayed(result: encode.EncodeResult) -> np.ndarray:
    reader = tile_reader(result)
    player = StreamPlayer()
    blob = result.stream.blob()
    shown = []
    cursor = 0
    for _ in range(len(result.stream)):
        cursor = player.apply(blob, cursor)
        shown.append(render(result, player, reader))
    return np.stack(shown)


def jumped_render(result: encode.EncodeResult, frame: int) -> np.ndarray:
    player = StreamPlayer()
    player.apply(result.stream.blob(), int(result.stream.frame_offsets()[frame]))
    return render(result, player, tile_reader(result))


def played_vram(result: encode.EncodeResult, target: int) -> np.ndarray:
    player = StreamPlayer()
    blob = result.stream.blob()
    offsets = result.stream.frame_offsets()
    for frame in range(target + 1):
        player.apply(blob, int(offsets[frame]))
    return player.vram.copy()


def jumped_vram(result: encode.EncodeResult, target: int) -> np.ndarray:
    player = StreamPlayer()
    player.apply(result.stream.blob(), int(result.stream.frame_offsets()[target]))
    return player.vram.copy()
