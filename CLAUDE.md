# Assistant guide

This file governs assistant behaviour in this repository. The engineering
contract is [AGENTS.md](AGENTS.md) and the family standard is
[FAMILY.md](FAMILY.md); read both first.

## One family, no ports

Owner's instruction, 2026-10-15: the players and the core are members of one
family of tools. Never describe one as a port, fork, translation or derivative
of another, in a README, a commit, a comment or any other text, in any
language. The Neo Geo player came first, but work has moved between the
members in both directions since, and more consoles will join.

## Everything must run on the original hardware

A change the board could disagree with is reported as unverified until the
owner has run it on an AES or MVS, and the report asks for that run.

## Every gate is a command

Nothing here is verified by compiling. The gates are listed in
[AGENTS.md](AGENTS.md); run them and read their output before claiming a change
is done.

## Emulators never take the screen

A fullscreen or flashing emulator window takes the display away from the owner
while they work. A scripted run is headless and silent: MAME with
`SDL_VIDEODRIVER=dummy` and `-window -video none -sound none`, RetroArch through
`open -g -j`. A run the owner asked to watch opens windowed and minimised, never
full screen.

Prefer geolith for evidence. MAME is a cross-check only, because its BIOS and
configuration defaults have produced failures and false positives.

## Do not ask what you can capture

When something is wrong on screen, capture the emulator, cut the recording
into frames and read them. Ask only when that loop has run and cannot settle
the question, and say what it showed.
