from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fmvcore import m68kobjdump

ADDRESS: Final = "address"
DATA: Final = "data"
MODULO: Final = "modulo"
PORTS: Final = {0x3C0000: ADDRESS, 0x3C0002: DATA, 0x3C0004: MODULO}
MIN_CYCLES_DATA_TO_DATA: Final = 12
MIN_CYCLES_DATA_TO_ADDRESS: Final = 16
FLOORS: Final = {
    (DATA, DATA): MIN_CYCLES_DATA_TO_DATA,
    (DATA, ADDRESS): MIN_CYCLES_DATA_TO_ADDRESS,
    (DATA, MODULO): MIN_CYCLES_DATA_TO_ADDRESS,
}
DISASSEMBLY_SUFFIX: Final = ".dis"


@dataclass(frozen=True, slots=True)
class Violation:
    spacing: m68kobjdump.Spacing
    floor: int
    symbol: str


def violations(listings: Mapping[str, str]) -> list[Violation]:
    reading = m68kobjdump.read(listings, ports=PORTS)
    return [
        Violation(spacing, floor, _owner(reading, spacing))
        for spacing in m68kobjdump.spacings(reading)
        if (floor := FLOORS.get((spacing.leaving.kind or "", spacing.arriving.kind or "")))
        is not None
        and spacing.cycles < floor
    ]


def _owner(reading: m68kobjdump.Reading, spacing: m68kobjdump.Spacing) -> str:
    listing = reading.program.listings[spacing.source]
    index = listing.instructions.index(spacing.first)
    return listing.owners[index] or "?"


def _report(found: list[Violation], objects: int) -> int:
    if not found:
        print(
            f"VRAM write spacing clears the {MIN_CYCLES_DATA_TO_DATA} and "
            f"{MIN_CYCLES_DATA_TO_ADDRESS} cycle minimums across {objects} object(s)"
        )
        return 0
    for violation in found:
        spacing = violation.spacing
        print(
            f"{spacing.source} {violation.symbol}: {spacing.leaving.kind} write to "
            f"{spacing.arriving.kind} write is {spacing.cycles} cycles, needs {violation.floor}",
            file=sys.stderr,
        )
        print(f"    0x{spacing.first.address:04x}: {spacing.first.text}", file=sys.stderr)
        print(f"    0x{spacing.second.address:04x}: {spacing.second.text}", file=sys.stderr)
    print(f"{len(found)} VRAM write pair(s) under the minimum", file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check VRAM write spacing across disassembled player objects, objdump -dr."
    )
    parser.add_argument("disassemblies", nargs="+", type=Path)
    arguments = parser.parse_args(argv)
    paths: list[Path] = arguments.disassemblies
    listings = {path.name.removesuffix(DISASSEMBLY_SUFFIX): path.read_text() for path in paths}
    try:
        found = violations(listings)
    except (m68kobjdump.UnmodelledWriteError, m68kobjdump.UnresolvedCallError) as error:
        print(f"cannot check VRAM timing: {error}", file=sys.stderr)
        return 2
    return _report(found, len(paths))


if __name__ == "__main__":
    raise SystemExit(main())
