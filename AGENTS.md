# Engineering contract

The rules for changing this repository. [FAMILY.md](FAMILY.md) is the standard
every member of the family follows, and it binds first; this file adds what is
particular to the Neo Geo. The [README](README.md) says what the project is and
how to use it.

## One family, no ports

Owner's instruction, 2026-10-15: the players and the core are members of one
family of tools. Never describe one as a port, fork, translation or derivative
of another, in a README, a commit, a comment or any other text, in any
language. The Neo Geo player came first, but work has moved between the
members in both directions since, and more consoles will join.

## Original hardware is the only target

Everything here is built to run on a real AES or MVS board. A clean emulator
run, a green suite and a good-looking capture are evidence about an emulator,
not about the board.

- A change that touches anything the board can disagree with, the VRAM write
  loop, the bank latch, the palette and fix latches, the interrupt or the ROM
  header, is unverified until it has run on a board. Say so in the change and
  ask for the run.
- Where a documented figure and a looser measured one disagree, the documented
  one binds.

### The binding numbers

| Rule | Value | Source |
|---|---|---|
| Cycles between consecutive VRAM data writes | at least 12 | NeoGeo Development Wiki, VRAM page |
| Cycles after a VRAM write before a new address | at least 16 | same |
| Program ROM bank latch | 3 bits, 8 banks of 1 MiB | MAME `neogeo.cpp`, which masks the register with `0x07` |
| Character ROM | 20-bit tile number, 128 MiB, no bankswitching | geolith `src/geo_lspc.c`, MAME `neogeo_spr.cpp` |
| Raster | 384 by 264 at a 6 MHz dot clock, 59.185 Hz, every region | geolith `LSPC_SCANLINES` |
| Watchdog | about 0.13 s | [`docs/hardware.md`](docs/hardware.md) |

Every bit layout the player depends on is in [`docs/hardware.md`](docs/hardware.md),
read out of both emulators' decoders.

## Gates

| Claim | Command |
|:--|:--|
| The baker holds | `uv --project tools run ruff format --check tools/`, `ruff check tools/`, `mypy tools/neogeomedia tools/scripts` |
| The behaviour holds | `uv --project tools run python -m pytest tools/tests --cov=neogeomedia --cov-fail-under=95` |
| It builds | `make rom` |
| The C holds | `make analyse` |
| No VRAM write pair is under its floor | `make timing`, after `make rom` |
| A cartridge comes out end to end | `uv --project tools run python -m neogeomedia.cartridge <source> --quality q17` |
| It runs on a board | the owner's AES or MVS; nothing on this machine settles it |

## Hard rules

1. **Docker for every build.** The toolchain image pins Ubuntu by digest, its
   packages by a dated snapshot and ngdevkit by version and SHA-256, and runs
   as the calling user.
2. **No comments or docstrings in source.** Reasoning goes in the commit
   message, this file or the development log.
3. **Functions under 30 lines, files under 500**, `mypy` strict, `ruff` clean,
   coverage 95%.
4. **The tier file is a property of films, not of a run.**
   [`neogeomedia-tiers.json`](neogeomedia-tiers.json) is committed; a bake made
   to test something, such as a demo capture, never lands in it.
5. **An emulator never takes the screen.** A scripted run is headless and makes
   no sound; a run the owner asked to watch opens windowed and minimised, never
   full screen. See "Running an emulator" below.

## Running an emulator

geolith, through RetroArch, is the first witness: a frame rebuilt from the
cartridge's own bytes matches what it draws pixel for pixel. MAME is a
cross-check only. Its BIOS and configuration defaults have produced failures
and false positives, and it starts full screen on macOS.

- **geolith**: [`tools/scripts/capture_rom.py`](tools/scripts/capture_rom.py)
  loads the geolith libretro core in-process through `fmvcore.libretro`, with
  no window and no RetroArch, and saves the last frame of the run as a PNG.
  It boots the Universe BIOS from `~/Documents/RetroArch/system`.
- **MAME**: every scripted run sets `SDL_VIDEODRIVER=dummy` and passes
  `-window -video none -sound none`, as
  [`tools/scripts/verify_mame.sh`](tools/scripts/verify_mame.sh) and the
  cutscene example's `verify.sh` do. `-video none` alone still opens a window on
  macOS.
- **A Neo Geo BIOS** is needed only to run an emulator, never to build, and is
  never committed or downloaded by a script.

## What is not done

The gaps against the family's requirements are listed in the state section of
[FAMILY.md](FAMILY.md).
