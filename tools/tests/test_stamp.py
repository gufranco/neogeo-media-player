from __future__ import annotations

import pytest

from neogeomedia import codegen, stamp

HEADER = """#ifndef FMV_H
#define FMV_H

#define FMV_VERSION "2.7.3"
#define FMV_VERSION_MAJOR 1
#define FMV_VERSION_MINOR 0

#endif
"""


class TestRestamping:
    def test_it_takes_the_major_from_the_version_string(self):
        # Arrange
        header = HEADER

        # Act
        text = stamp.restamp(header)

        # Assert
        assert "#define FMV_VERSION_MAJOR 2" in text

    def test_it_takes_the_minor_from_the_version_string(self):
        # Arrange
        header = HEADER

        # Act
        text = stamp.restamp(header)

        # Assert
        assert "#define FMV_VERSION_MINOR 7" in text

    def test_it_leaves_the_version_string_alone(self):
        # Arrange
        header = HEADER

        # Act
        text = stamp.restamp(header)

        # Assert
        assert '#define FMV_VERSION "2.7.3"' in text

    def test_it_leaves_the_rest_of_the_header_alone(self):
        # Arrange
        header = HEADER

        # Act
        text = stamp.restamp(header)

        # Assert
        assert text.startswith("#ifndef FMV_H")
        assert text.endswith("#endif\n")

    def test_restamping_an_already_current_header_changes_nothing(self):
        # Arrange
        current = stamp.restamp(HEADER)

        # Act
        again = stamp.restamp(current)

        # Assert
        assert again == current

    def test_a_header_without_a_version_string_is_an_error(self):
        # Arrange
        header = "#define FMV_VERSION_MAJOR 1\n"

        # Act
        with pytest.raises(SystemExit) as raised:
            stamp.restamp(header)

        # Assert
        assert "FMV_VERSION" in str(raised.value)

    def test_a_header_without_the_numeric_defines_is_an_error(self):
        # Arrange
        header = '#define FMV_VERSION "1.0.0"\n'

        # Act
        with pytest.raises(SystemExit) as raised:
            stamp.restamp(header)

        # Assert
        assert "FMV_VERSION_MAJOR" in str(raised.value)


class TestTheCommandLine:
    def test_it_rewrites_the_header_in_place(self, tmp_path):
        # Arrange
        header = tmp_path / "fmv.h"
        header.write_text(HEADER)

        # Act
        code = stamp.main([str(header)])

        # Assert
        assert code == 0
        assert "#define FMV_VERSION_MAJOR 2" in header.read_text()

    def test_it_reports_nothing_when_the_header_is_already_current(self, tmp_path, capsys):
        # Arrange
        header = tmp_path / "fmv.h"
        header.write_text(stamp.restamp(HEADER))

        # Act
        stamp.main([str(header)])

        # Assert
        assert capsys.readouterr().out == ""


class TestTheShippedHeader:
    def test_the_repository_header_is_already_stamped(self):
        # Arrange
        text = stamp.HEADER.read_text()

        # Act
        restamped = stamp.restamp(text)

        # Assert
        assert restamped == text

    def test_it_states_the_version_the_package_states(self):
        # Arrange
        major, minor = codegen.baker_version()

        # Act
        text = stamp.HEADER.read_text()

        # Assert
        assert f'#define FMV_VERSION "{major}.{minor}.' in text
