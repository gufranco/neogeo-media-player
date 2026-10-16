from __future__ import annotations

from neogeomedia import codegen
from tests.bakehelp import generated

HEADER = "movie_data.h"


class TestMovieFigures:
    def test_the_header_reports_the_stream_bank_count(self, baked):
        # Arrange
        expected = f"#define MOVIE_STREAM_BANKS {baked.result.stream.bank_count()}"

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert expected in text

    def test_it_emits_a_header_with_the_frame_count(self, baked):
        # Arrange
        expected = f"#define MOVIE_FRAME_COUNT {baked.result.stats.frames}"

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert expected in text

    def test_it_emits_a_header_with_the_palette_base_bank(self, baked):
        # Arrange
        expected = "#define MOVIE_PALETTE_BASE 16"

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert expected in text

    def test_the_header_guards_against_double_inclusion(self, baked):
        # Arrange
        guard = "#ifndef MOVIE_DATA_H"

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert text.count(guard) == 1
        assert "#endif" in text

    def test_every_stream_stub_carries_the_bank_naming_convention(self, baked):
        # Arrange
        folder = baked.build_dir / "generated"

        # Act
        stems = [stub.stem for stub in folder.glob("fmv_stream__bank*.S")]

        # Assert
        assert stems
        assert all("__bank" in stem for stem in stems)


class TestVersionStamp:
    def test_the_header_stamps_the_version_that_baked_it(self, baked):
        # Arrange
        major, minor = codegen.baker_version()

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert f"#define MOVIE_BAKER_VERSION_MAJOR {major}" in text
        assert f"#define MOVIE_BAKER_VERSION_MINOR {minor}" in text

    def test_the_stamp_is_readable_as_a_string_too(self, baked):
        # Arrange
        major, minor = codegen.baker_version()

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert f'#define MOVIE_BAKER_VERSION_STRING "{major}.{minor}"' in text

    def test_a_library_of_another_version_stops_the_build(self, baked):
        # Arrange
        checks = ("MAJOR != FMV_VERSION_MAJOR", "MINOR != FMV_VERSION_MINOR", "#error")

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert all(check in text for check in checks)

    def test_the_failing_build_names_both_versions(self, baked):
        # Arrange
        names = ("MOVIE_BAKER_VERSION_STRING)", "FMV_VERSION_STRING)")

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert all(name in text for name in names)


class TestTickCost:
    def test_the_header_states_the_worst_frame_in_updates(self, baked):
        # Arrange
        expected = f"#define MOVIE_MAX_UPDATES {baked.result.stats.max_updates}"

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert expected in text

    def test_the_header_states_what_one_update_costs(self, baked):
        # Arrange
        expected = f"#define MOVIE_CYCLES_PER_UPDATE {codegen.CYCLES_PER_UPDATE}"

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert expected in text

    def test_the_header_states_what_the_worst_frame_costs(self, baked):
        # Arrange
        expected = baked.result.stats.max_updates * codegen.CYCLES_PER_UPDATE

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert f"#define MOVIE_TICK_CYCLES {expected}" in text

    def test_the_header_states_the_budget_that_cost_is_measured_against(self, baked):
        # Arrange
        expected = f"#define MOVIE_VBLANK_CYCLES {codegen.VBLANK_CYCLES}"

        # Act
        text = generated(baked, HEADER)

        # Assert
        assert expected in text
