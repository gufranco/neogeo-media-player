from __future__ import annotations

import numpy as np

from neogeomedia import epochs, frames, neocolor

BLACK, WHITE = (
    int(index)
    for index in neocolor.rgb_to_color_index(np.array([[0, 0, 0], [255, 255, 255]], np.uint8))
)


def scenes(*lengths_and_colours: tuple[int, int]) -> np.ndarray:
    rows = [
        np.full((length, 2, 2, 16, 16), colour, dtype=np.uint16)
        for length, colour in lengths_and_colours
    ]
    return np.concatenate(rows)


def random_tiles(seed: int, extra: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 100, size=(epochs.MAX_SAMPLE_TILES + extra, 16, 16), dtype=np.uint16)


class TestSampleThinning:
    def test_a_small_sample_is_left_alone(self):
        # Arrange
        tiles = np.zeros((10, 16, 16), dtype=np.uint16)

        # Act
        thinned = epochs.thin_sample(tiles, 0)

        # Assert
        assert thinned.shape[0] == 10

    def test_a_large_sample_is_capped(self):
        # Arrange
        tiles = np.zeros((epochs.MAX_SAMPLE_TILES + 5000, 16, 16), dtype=np.uint16)

        # Act
        thinned = epochs.thin_sample(tiles, 0)

        # Assert
        assert thinned.shape[0] == epochs.MAX_SAMPLE_TILES

    def test_thinning_is_deterministic_for_a_seed(self):
        # Arrange
        tiles = random_tiles(1, 100)

        # Act
        first = epochs.thin_sample(tiles, 3)

        # Assert
        assert np.array_equal(first, epochs.thin_sample(tiles, 3))

    def test_thinning_keeps_source_order(self):
        # Arrange
        tiles = np.arange(epochs.MAX_SAMPLE_TILES + 100, dtype=np.uint32)[:, None, None]

        # Act
        thinned = epochs.thin_sample(tiles, 4)

        # Assert
        assert thinned.shape == (epochs.MAX_SAMPLE_TILES, 1, 1)
        assert bool(np.all(np.diff(thinned[:, 0, 0].astype(np.int64)) > 0))


class TestPaletteSampling:
    def test_a_longer_epoch_gets_a_coarser_stride(self):
        # Arrange
        short_epoch = epochs.stride_for_epoch(epoch_frames=120)

        # Act
        long_epoch = epochs.stride_for_epoch(epoch_frames=1200)

        # Assert
        assert long_epoch > short_epoch

    def test_the_stride_is_never_below_one(self):
        # Arrange
        epoch_frames = 1

        # Act
        stride = epochs.stride_for_epoch(epoch_frames=epoch_frames)

        # Assert
        assert stride == 1

    def test_an_epoch_yields_about_the_target_sample_count(self):
        # Arrange
        frames_per_epoch = 900

        # Act
        stride = epochs.stride_for_epoch(epoch_frames=frames_per_epoch)

        # Assert
        assert abs(frames_per_epoch / stride - epochs.SAMPLES_PER_EPOCH) < epochs.SAMPLES_PER_EPOCH


class TestUploadMinimum:
    def test_the_minimum_follows_the_palette_count(self):
        # Arrange
        small = epochs.epoch_upload_frames(8)

        # Act
        large = epochs.epoch_upload_frames(240)

        # Assert
        assert large > small

    def test_the_minimum_covers_the_upload_with_room_to_spare(self):
        # Arrange
        bare = (240 // 2) * epochs.WORDS_PER_PALETTE / epochs.PALETTE_WORDS_PER_FRAME

        # Act
        minimum = epochs.epoch_upload_frames(240)

        # Assert
        assert minimum >= bare * epochs.EPOCH_UPLOAD_MARGIN

    def test_the_full_allocation_takes_one_hundred_and_twenty_frames(self):
        # Arrange
        palette_count = 240

        # Act
        minimum = epochs.epoch_upload_frames(palette_count)

        # Assert
        assert minimum == 120


class TestEpochStarts:
    def test_an_epoch_begins_on_a_hard_cut(self):
        # Arrange
        grids = scenes((4, BLACK), (4, WHITE))

        # Act
        starts = epochs.epoch_starts(grids, 8, 1, 8, floor=0.01, minimum=1)

        # Assert
        assert starts == [0, 4]

    def test_a_cut_inside_the_spacing_guard_is_ignored(self):
        # Arrange
        grids = scenes((1, BLACK), (7, WHITE))

        # Act
        starts = epochs.epoch_starts(grids, 8, 1, 8, floor=0.01, minimum=1)

        # Assert
        assert starts == [0]

    def test_a_long_scene_is_subdivided_at_the_cadence(self):
        # Arrange
        grids = scenes((10, BLACK))

        # Act
        starts = epochs.epoch_starts(grids, 4, 1, 10, floor=0.01, minimum=1)

        # Assert
        assert starts == [0, 4, 8]

    def test_boundaries_closer_than_the_minimum_are_dropped(self):
        # Arrange
        grids = scenes((10, BLACK))

        # Act
        starts = epochs.epoch_starts(grids, 4, 1, 10, floor=0.01, minimum=5)

        # Assert
        assert starts == [0, 8]

    def test_a_cut_lands_on_the_frame_its_sample_row_stands_for(self):
        # Arrange
        grids = scenes((3, BLACK), (3, WHITE))

        # Act
        starts = epochs.epoch_starts(grids, 40, 5, 30, floor=0.01, minimum=1)

        # Assert
        assert starts == [0, 15]


class TestEpochSamples:
    def test_epochs_switched_off_give_no_buckets(self):
        # Arrange
        grids = scenes((4, BLACK))

        # Act
        samples = epochs.epoch_samples(
            grids,
            epoch_seconds=0.0,
            sample_stride=1,
            duration=1.0,
            palette_count=8,
            scene_cut_floor=0.01,
            seed=0,
        )

        # Assert
        assert samples is None

    def test_a_cadence_too_short_for_one_frame_gives_no_buckets(self):
        # Arrange
        grids = scenes((4, BLACK))

        # Act
        samples = epochs.epoch_samples(
            grids,
            epoch_seconds=0.001,
            sample_stride=1,
            duration=1.0,
            palette_count=8,
            scene_cut_floor=0.01,
            seed=0,
        )

        # Assert
        assert samples is None

    def test_each_bucket_runs_one_cadence_from_its_own_start(self):
        # Arrange
        grids = scenes((4, BLACK), (4, WHITE))
        eight_frames = 8.5 / float(frames.VBLANK_FPS)

        # Act
        samples = epochs.epoch_samples(
            grids,
            epoch_seconds=eight_frames,
            sample_stride=1,
            duration=eight_frames,
            palette_count=2,
            scene_cut_floor=0.01,
            seed=0,
        )

        # Assert
        assert samples is not None
        assert [start for start, _ in samples] == [0, 4]
        assert [tiles.shape for _, tiles in samples] == [(32, 16, 16), (16, 16, 16)]
        assert int(samples[1][1][0, 0, 0]) == WHITE
