from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture(scope="module")
def timing():
    spec = importlib.util.spec_from_file_location(
        "check_vram_timing", SCRIPTS / "check_vram_timing.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def listing(name: str, *rows: str) -> str:
    header = [f"{name}:     file format elf32-m68k", "", "", "Disassembly of section .text:"]
    return "\n".join(header + list(rows)) + "\n"


def symbol(address: int, name: str) -> str:
    return f"\n{address:08x} <{name}>:"


def op(address: int, encoding: str, text: str) -> str:
    return f" {address:x}:\t{encoding} \t{text}"


def tail(address: int, encoding: str) -> str:
    return f" {address:x}:\t{encoding} "


def reloc(address: int, name: str) -> str:
    return f"\t\t\t{address:x}: R_68K_32\t{name}"


def found(violations) -> list[tuple[str, str, int, int]]:
    return [
        (v.spacing.leaving.kind, v.spacing.arriving.kind, v.spacing.cycles, v.floor)
        for v in violations
    ]


class TestPairsUnderTheFloor:
    def test_a_long_immediate_write_then_a_register_write_is_flagged(self, timing):
        # Arrange
        text = listing(
            "a.o",
            symbol(0x4D6, "sample"),
            op(0x4D6, "23fc 74ba 1016", "movel #1958350870,3c0000 <x>"),
            tail(0x4DC, "003c 0000"),
            op(0x4E0, "23c9 003c 0000", "movel %a1,3c0000 <x>"),
            op(0x4E6, "4e75", "rts"),
        )

        # Act
        violations = timing.violations({"a.o": text})

        # Assert
        assert found(violations) == [("data", "address", 12, 16)]

    def test_two_adjacent_register_indirect_writes_are_flagged(self, timing):
        # Arrange
        text = listing(
            "a.o",
            symbol(0x100, "sample"),
            op(0x100, "207c 003c 0000", "moveal #3932160,%a0"),
            op(0x106, "2080", "movel %d0,%a0@"),
            op(0x108, "2081", "movel %d1,%a0@"),
            op(0x10A, "4e75", "rts"),
        )

        # Act
        violations = timing.violations({"a.o": text})

        # Assert
        assert found(violations) == [("data", "address", 4, 16)]

    def test_a_write_in_a_callee_from_another_object_is_flagged(self, timing):
        # Arrange
        caller = listing(
            "a.o",
            symbol(0x0, "main"),
            op(0x0, "207c 003c 0002", "moveal #3932162,%a0"),
            op(0x6, "3080", "movew %d0,%a0@"),
            op(0x8, "4ef9 0000 0000", "jmp 0 <main>"),
            reloc(0xA, "poke"),
        )
        callee = listing(
            "b.o",
            symbol(0x0, "setup"),
            op(0x0, "227c 003c 0000", "moveal #3932160,%a1"),
            op(0x6, "4e75", "rts"),
            symbol(0x8, "poke"),
            op(0x8, "3281", "movew %d1,%a1@"),
            op(0xA, "4e75", "rts"),
        )

        # Act
        violations = timing.violations({"a.o": caller, "b.o": callee})

        # Assert
        assert [(v.spacing.source, v.spacing.to_source, v.spacing.cycles) for v in violations] == [
            ("a.o:.text", "b.o:.text", 14)
        ]


class TestPairsThatClearTheFloor:
    def test_one_cheap_instruction_between_two_writes_reaches_the_floor(self, timing):
        # Arrange
        text = listing(
            "a.o",
            symbol(0x4D6, "sample"),
            op(0x4D6, "23fc 74ba 1016", "movel #1958350870,3c0000 <x>"),
            tail(0x4DC, "003c 0000"),
            op(0x4E0, "4e71", "nop"),
            op(0x4E2, "23c9 003c 0000", "movel %a1,3c0000 <x>"),
            op(0x4E8, "4e75", "rts"),
        )

        # Act
        violations = timing.violations({"a.o": text})

        # Assert
        assert violations == []

    def test_the_stream_write_loop_passes(self, timing):
        # Arrange
        text = listing(
            "a.o",
            symbol(0x226, "sample"),
            op(0x226, "227c 003c 0002", "moveal #3932162,%a1"),
            op(0x22C, "3290", "movew %a0@,%a1@"),
            op(0x22E, "5888", "addql #4,%a0"),
            op(0x230, "32a8 fffe", "movew %a0@(-2),%a1@"),
            op(0x234, "b088", "cmpl %a0,%d0"),
            op(0x236, "66ee", "bnes 226 <x>"),
            op(0x238, "4e75", "rts"),
        )

        # Act
        violations = timing.violations({"a.o": text})

        # Assert
        assert violations == []

    def test_a_word_fill_loop_passes(self, timing):
        # Arrange
        text = listing(
            "a.o",
            symbol(0x6C, "sample"),
            op(0x6C, "33fc 0000 003c", "movew #0,3c0002 <x>"),
            tail(0x72, "0002"),
            op(0x74, "5342", "subqw #1,%d2"),
            op(0x76, "66f4", "bnes 6c <x>"),
            op(0x78, "4e75", "rts"),
        )

        # Act
        violations = timing.violations({"a.o": text})

        # Assert
        assert violations == []


class TestTheCommand:
    def test_clean_objects_exit_zero_and_say_so(self, timing, tmp_path, capsys):
        # Arrange
        path = tmp_path / "a.o.dis"
        path.write_text(listing("a.o", symbol(0x0, "main"), op(0x0, "4e75", "rts")))

        # Act
        code = timing.main([str(path)])

        # Assert
        assert (code, capsys.readouterr().out) == (
            0,
            "VRAM write spacing clears the 12 and 16 cycle minimums across 1 object(s)\n",
        )

    def test_a_violation_exits_one_and_names_both_writes(self, timing, tmp_path, capsys):
        # Arrange
        path = tmp_path / "a.o.dis"
        path.write_text(
            listing(
                "a.o",
                symbol(0x100, "sample"),
                op(0x100, "207c 003c 0000", "moveal #3932160,%a0"),
                op(0x106, "2080", "movel %d0,%a0@"),
                op(0x108, "2081", "movel %d1,%a0@"),
                op(0x10A, "4e75", "rts"),
            )
        )

        # Act
        code = timing.main([str(path)])

        # Assert
        assert (code, capsys.readouterr().err.splitlines()) == (
            1,
            [
                "a.o:.text sample: data write to address write is 4 cycles, needs 16",
                "    0x0106: movel %d0,%a0@",
                "    0x0108: movel %d1,%a0@",
                "1 VRAM write pair(s) under the minimum",
            ],
        )

    def test_an_unmodelled_write_form_exits_two(self, timing, tmp_path, capsys):
        # Arrange
        path = tmp_path / "a.o.dis"
        path.write_text(
            listing(
                "a.o",
                symbol(0x100, "main"),
                op(0x100, "33f0 0800 003c", "movew %a0@(0,%d0:l),3c0002 <x>"),
                tail(0x106, "0002"),
                op(0x108, "4e75", "rts"),
            )
        )

        # Act
        code = timing.main([str(path)])

        # Assert
        assert (code, capsys.readouterr().err) == (
            2,
            "cannot check VRAM timing: word absolute write from '%a0@(0,%d0:l)'\n",
        )
