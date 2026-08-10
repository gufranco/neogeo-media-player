# fmv decisions

Why the library is shaped the way it is. Each entry names the choice, the
alternatives it beat, and the evidence that settled it. The
[specification](spec.md) says what the library does; this file says why it
does it that way, so a later change can tell a deliberate constraint from
an accident.

## The library reaches a project as source, not as a binary

A developer already has an ngdevkit project with a `Makefile`, a `rom.mk`
and an autoconf `config.mk`. Whatever the baker emits has to slot into that
without asking them to restructure anything.

The baker emits a self-contained folder of source plus an `fmv.mk`
fragment. The two alternatives were a prebuilt `libfmv.a` and a git
submodule. A static library has to match the developer's exact toolchain
and flags, and it is opaque when it misbehaves. A submodule is friction,
and the generated movie asset still has to live in their tree, so they end
up carrying both.

Source is also what the ecosystem already does: ngdevkit examples carry
their own assets. The real cost of copying is drift, and drift is answered
by stamping the emitted folder with the baker version that produced it. A
mismatched bundle stops the build and names both versions instead of
misbehaving quietly.

The 2.0 release exercised that stamp end to end. Bumping the package
rewrote `FMV_VERSION_MAJOR` in `fmv.h`, and a fresh bake stamped the same
2.0 into the generated header.

## The linker places the stream, the build does not append it

`apply_frame` reads the command stream through the 1 MiB bank window at
`0x200000`. The bank is the offset divided by the bank size, which assumes
the stream starts at the first switchable bank. That was true only because
an earlier build appended `stream.bin` to `p1.p1` after linking.

The stream is now emitted as one `__bank`-named stub per bank it occupies,
and offsets resolve against a linker symbol. Keeping the absolute layout
would have worked only for a project whose banks are otherwise empty, which
is exactly the project that does not need a library. The cost is one
register add outside the per-tile inner loop.

What settled it: `p1.p1` came out byte-identical before and after the
change, so the cartridge could not draw anything different.

## Video works with no audio, and audio is a second step

The soundtrack is ADPCM-B driven by a Z80 program in the M1 ROM. A game
that already has music already has its own Z80 driver, and there is one M1.

The core is video-only. Audio is an optional module whose Z80 side ships as
source to merge. Requiring the driver would have made the library unusable
by any game with its own sound, which is most games.

What settled it: CI builds the same example project twice from one bundle.
The default build produces a cartridge with no Z80 symbol referenced. The
`FMV_AUDIO=yes` build produces an M1 that is byte-different from ngdevkit's
empty `nullsound` driver, which is what proves the movie's own driver was
built from the bundle rather than silently falling back.

## The caller declares its layout in a struct

The original player hardcoded sprite 1 upward, CRAM from a fixed base, the
full raster at the origin, and the fix layer for its menu. A game owns some
of each already.

`fmv_options` carries the layout, read once at open and cached into the
player state so the hot path sees plain fields rather than a config
pointer. Compile-time defines were the alternative, and they turn every
layout change into a library rebuild while mistakes surface as silent
corruption rather than as a value the developer can print.

## Three registers are in that struct because they cannot be read

`fmv_open` originally saved the LSPC mode, the fix-source and palette-bank
latches and the program-bank latch by reading them, and `fmv_close` wrote
those values back.

Three of the four cannot be read on this hardware. MAME maps the whole
`0x3A0000` range to a handler that returns the last word on the bus, which
is almost always the next instruction's opcode because of prefetch, and
geolith has no read case for the range at all. A read of `0x3C0006` is the
raster line counter rather than the mode register. So `fmv_close` was
writing a prefetched opcode and a scanline number back into the machine.
The full citation is in the [development log](../../../CHANGELOG.md).

The caller now declares that state in `fmv_options` and the library
restores what it was told. The host tests model those latches with no read
path at all, so code that tries to read one fails to compile rather than
failing on silicon.

This is also why `fmv_options` is promised from 2.0 but the layout of
`fmv_movie` and `fmv_player` is not. The struct had to grow to absorb this
finding, and it may have to grow again.

## The player became the example rather than a new demo

A minimal demo would have proved less. If the library cannot rebuild the
player that already runs on real hardware, the split took something out
that a real application needs.

What settled it: the rebuilt player renders identically under MAME against
the same baked frames.

## The MAME gate is mitigated, and the mechanism is still unexplained

The acceptance criterion for the split was the MAME mean error, at or below
1.57 of 255. During that work the gate returned four different readings on
a ROM that had not changed: 1.5658, 1.5929, 1.5696, and 27.8718, the last
one a failure. The comparison itself is deterministic, measured across four
identical runs on one saved snapshot, so the variation was in what MAME
handed it.

Two things changed. MAME was given a real render target and stopped seizing
the display, which was a defect on its own terms regardless of determinism.
And the matcher now refuses a match it cannot separate from its nearest
rival, so a reading that is only a guess reports as ambiguous rather than
as a number.

The gate has been stable at 1.5658 since. That is an empirical result, not
a root cause, and it is recorded here as unexplained on purpose. If the
spread returns, it should be read as the original defect resurfacing rather
than as new noise.
