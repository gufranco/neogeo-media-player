from __future__ import annotations

import struct

import numpy as np
import pytest

from neogeomedia import bake
from tests.bakehelp import small_request
from tests.capturehelp import (
    HEIGHT,
    OVERSCAN,
    WIDTH,
    active,
    load_script,
    noise_frames,
    write_lossless,
    write_png,
)

pytestmark = pytest.mark.ffmpeg

verify_capture = load_script("verify_capture")

PREVIEW_FRAMES = 6


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    directory = tmp_path_factory.mktemp("verify")
    frames = noise_frames(PREVIEW_FRAMES, stream=0)
    return frames, write_lossless(directory / "preview.mkv", frames), directory


@pytest.fixture(scope="module")
def reconstructed(synthetic_clip, tmp_path_factory):
    directory = tmp_path_factory.mktemp("reconstruct")
    request = small_request(
        synthetic_clip, directory / "build", palette_count=8, preview=directory / "ref.mkv"
    )
    outcome = bake.run(request)
    reference = np.stack(list(verify_capture.stream_preview(directory / "ref.mkv")))
    return outcome.build_dir / "baked", reference, outcome.result.stats.frames


def run_main(capture, **options) -> int:
    argv = ["--capture", str(capture)]
    for key, value in options.items():
        argv += [f"--{key.replace('_', '-')}", str(value)]
    return verify_capture.main(argv)


class TestDecoding:
    def test_the_preview_decodes_back_to_the_written_frames(self, rendered):
        # Arrange
        frames, preview, _ = rendered

        # Act
        decoded = np.stack(list(verify_capture.stream_preview(preview)))

        # Assert
        assert np.array_equal(decoded, frames)

    def test_a_capture_decodes_at_its_own_geometry(self, rendered):
        # Arrange
        frames, _, directory = rendered
        capture = write_png(directory / "shot.png", active(frames[2]))

        # Act
        decoded = verify_capture.decode_capture(capture)

        # Assert
        assert decoded.shape == (HEIGHT, WIDTH - 2 * OVERSCAN, 3)
        assert np.array_equal(decoded, active(frames[2]))


class TestMatching:
    def test_an_exact_capture_passes(self, rendered, capsys):
        # Arrange
        frames, preview, directory = rendered
        capture = write_png(directory / "exact.png", active(frames[3]))

        # Act
        code = run_main(capture, preview=preview)

        # Assert
        assert code == 0
        assert "exact pixel match: True" in capsys.readouterr().out

    def test_it_reports_which_frame_matched(self, rendered, capsys):
        # Arrange
        frames, preview, directory = rendered
        capture = write_png(directory / "which.png", active(frames[4]))

        # Act
        run_main(capture, preview=preview)

        # Assert
        assert f"best match: rendered frame 4 of {PREVIEW_FRAMES}" in capsys.readouterr().out

    def test_an_unrelated_capture_fails(self, rendered, capsys):
        # Arrange
        _, preview, directory = rendered
        capture = write_png(directory / "unrelated.png", active(noise_frames(1, stream=1)[0]))

        # Act
        code = run_main(capture, preview=preview)

        # Assert
        assert code == 1
        assert "FAIL: best match error" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("rows", "columns", "complaint"),
        [
            (slice(None), slice(None), "does not match a 8 pixel overscan"),
            (slice(0, 100), slice(OVERSCAN, WIDTH - OVERSCAN), "capture height 100"),
        ],
        ids=["wrong-width", "wrong-line-count"],
    )
    def test_a_wrongly_sized_capture_is_rejected(self, rendered, capsys, rows, columns, complaint):
        # Arrange
        _, preview, directory = rendered
        image = noise_frames(1, stream=2)[0][rows, columns]
        capture = write_png(directory / "wrong.png", image)

        # Act
        code = run_main(capture, preview=preview)

        # Assert
        assert code == 2
        assert complaint in capsys.readouterr().err


class TestSeparation:
    def test_the_run_of_identical_frames_around_the_best_is_not_a_rival(self):
        # Arrange
        scored = {0: 9.0, 1: 1.5, 2: 1.5, 3: 1.5, 4: 8.0}

        # Act
        run = verify_capture.tied_run(scored, 2)

        # Assert
        assert run == {1, 2, 3}

    def test_a_lone_best_frame_is_its_own_run(self):
        # Arrange
        scored = {0: 9.0, 1: 1.5, 2: 8.0}

        # Act
        run = verify_capture.tied_run(scored, 1)

        # Assert
        assert run == {1}

    def test_a_run_that_reaches_the_end_stops_there(self):
        # Arrange
        scored = {0: 1.5, 1: 1.5}

        # Act
        run = verify_capture.tied_run(scored, 1)

        # Assert
        assert run == {0, 1}

    def test_it_reports_how_far_ahead_the_match_is(self, rendered, capsys):
        # Arrange
        frames, preview, directory = rendered
        capture = write_png(directory / "separated.png", active(frames[2]))

        # Act
        run_main(capture, preview=preview)

        # Assert
        assert "nearest rival: frame " in capsys.readouterr().out

    def test_a_match_no_better_than_its_rival_is_refused(self, tmp_path, capsys):
        # Arrange
        first = noise_frames(1, stream=3)[0]
        second = first.copy()
        second[0, WIDTH // 2] = (second[0, WIDTH // 2].astype(int) + 1) % 256
        preview = write_lossless(tmp_path / "twins.mkv", np.stack([first, second]))
        capture = write_png(tmp_path / "twin.png", active(first))

        # Act
        code = run_main(capture, preview=preview, min_separation=5.0)

        # Assert
        assert code == 2
        assert "AMBIGUOUS" in capsys.readouterr().err

    def test_a_clearly_separated_match_is_accepted(self, rendered, capsys):
        # Arrange
        frames, preview, directory = rendered
        capture = write_png(directory / "clear.png", active(frames[1]))

        # Act
        code = run_main(capture, preview=preview, min_separation=1.0)

        # Assert
        assert code == 0
        assert capsys.readouterr().out.endswith("PASS\n")


class TestGuardsOnTheInputs:
    def test_a_reference_with_no_frames_at_all_is_refused(self, rendered, tmp_path, capsys):
        # Arrange
        frames, _, directory = rendered
        capture = write_png(directory / "empty-reference.png", active(frames[0]))
        empty = tmp_path / "empty.mkv"
        empty.write_bytes(b"")

        # Act
        code = run_main(capture, preview=empty)

        # Assert
        assert code == 2
        assert "the reference produced no frames" in capsys.readouterr().err

    def test_naming_neither_a_preview_nor_a_bake_is_refused(self, rendered, capsys):
        # Arrange
        _, _, directory = rendered

        # Act
        with pytest.raises(SystemExit) as refused:
            run_main(directory / "shot.png")

        # Assert
        assert refused.value.code == 2
        assert "pass either --preview or --baked" in capsys.readouterr().err

    def test_naming_a_bake_without_a_frame_is_refused(self, rendered, tmp_path, capsys):
        # Arrange
        _, _, directory = rendered

        # Act
        with pytest.raises(SystemExit) as refused:
            run_main(directory / "shot.png", baked=tmp_path)

        # Assert
        assert refused.value.code == 2
        assert "--baked needs --frame" in capsys.readouterr().err

    def test_a_frame_outside_the_movie_is_refused(self, tmp_path):
        # Arrange
        baked = tmp_path / "baked"
        baked.mkdir()
        (baked / "stream.bin").write_bytes(b"")
        (baked / "index.bin").write_bytes(struct.pack(">I", 0))

        # Act
        with pytest.raises(ValueError, match="outside the 1 frame movie") as refused:
            verify_capture.reconstruct_frame(baked, 5)

        # Assert
        assert str(refused.value) == "frame 5 is outside the 1 frame movie"


class TestEpochPalettes:
    def test_a_bake_with_no_epoch_table_keeps_the_whole_palette(self, tmp_path):
        # Arrange
        colors = np.arange(64, dtype=np.uint16).reshape(4, 16)

        # Act
        epoch, kept = verify_capture._epoch_palettes(tmp_path, 0, colors)

        # Assert
        assert epoch == 0
        assert np.array_equal(kept, colors)

    def test_a_single_epoch_keeps_the_whole_palette(self, tmp_path):
        # Arrange
        (tmp_path / "epochs.bin").write_bytes(struct.pack(">I", 0))
        colors = np.arange(64, dtype=np.uint16).reshape(4, 16)

        # Act
        epoch, kept = verify_capture._epoch_palettes(tmp_path, 0, colors)

        # Assert
        assert epoch == 0
        assert np.array_equal(kept, colors)

    def test_a_later_epoch_takes_its_own_slice(self, tmp_path):
        # Arrange
        (tmp_path / "epochs.bin").write_bytes(struct.pack(">II", 0, 10))
        colors = np.arange(64, dtype=np.uint16).reshape(4, 16)

        # Act
        epoch, kept = verify_capture._epoch_palettes(tmp_path, 12, colors)

        # Assert
        assert epoch == 1
        assert np.array_equal(kept, colors[2:])


class TestUpscaledCaptures:
    def test_an_integer_upscaled_capture_is_reduced_to_the_active_area(self):
        # Arrange
        frame = active(noise_frames(1, stream=4)[0])
        upscaled = np.repeat(np.repeat(frame, 6, axis=0), 6, axis=1)

        # Act
        reduced = verify_capture.downscale_capture(upscaled)

        # Assert
        assert np.array_equal(reduced, frame)

    def test_a_native_capture_is_left_alone(self):
        # Arrange
        frame = active(noise_frames(1, stream=5)[0])

        # Act
        kept = verify_capture.downscale_capture(frame)

        # Assert
        assert np.array_equal(kept, frame)

    def test_an_upscaled_capture_still_matches_its_rendered_frame(self, rendered, capsys):
        # Arrange
        frames, preview, directory = rendered
        frame = active(frames[1])
        capture = write_png(
            directory / "upscaled.png", np.repeat(np.repeat(frame, 3, axis=0), 3, axis=1)
        )

        # Act
        code = run_main(capture, preview=preview)

        # Assert
        assert code == 0
        assert f"best match: rendered frame 1 of {PREVIEW_FRAMES}" in capsys.readouterr().out


class TestReconstruction:
    def test_reconstruction_matches_the_rendered_preview(self, reconstructed):
        # Arrange
        baked, reference, frames = reconstructed

        # Act
        rebuilt = verify_capture.reconstruct_frame(baked, frames - 1)

        # Assert
        assert np.array_equal(rebuilt, reference[frames - 1])

    def test_reconstruction_matches_at_an_intermediate_frame(self, reconstructed):
        # Arrange
        baked, reference, _ = reconstructed

        # Act
        rebuilt = verify_capture.reconstruct_frame(baked, 3)

        # Assert
        assert np.array_equal(rebuilt, reference[3])

    def test_a_capture_verifies_against_the_baked_artifacts(self, reconstructed, tmp_path, capsys):
        # Arrange
        baked, reference, _ = reconstructed
        capture = write_png(tmp_path / "shot.png", active(reference[5]))

        # Act
        code = run_main(capture, baked=baked, frame=5)

        # Assert
        assert code == 0
        assert "exact pixel match: True" in capsys.readouterr().out


class TestStreamingIsBounded:
    def test_it_yields_frames_one_at_a_time(self, tmp_path):
        # Arrange
        preview = write_lossless(tmp_path / "ref.mkv", noise_frames(4, stream=6))

        # Act
        first = next(verify_capture.stream_preview(preview))

        # Assert
        assert first.shape == (HEIGHT, WIDTH, 3)

    def test_it_yields_every_frame(self, tmp_path):
        # Arrange
        frames = noise_frames(4, stream=6)
        preview = write_lossless(tmp_path / "ref.mkv", frames)

        # Act
        decoded = list(verify_capture.stream_preview(preview))

        # Assert
        assert np.array_equal(np.stack(decoded), frames)
