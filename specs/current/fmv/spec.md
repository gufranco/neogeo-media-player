# fmv Specification

## Purpose

What the movie library does for a caller that embeds it: how a cutscene
plays, what it borrows while it runs, and what state the caller gets
back.

## Requirements

### Requirement: A cutscene must be skippable

The library must stop playback within one frame of the caller's skip
condition becoming true, and must report which way the movie ended.

#### Scenario: A masked button ends the cutscene early
- GIVEN a movie playing with `FMV_PAD_A` in `options.skip_pad`
- WHEN that button is held at any frame
- THEN `fmv_play` returns `FMV_SKIPPED` and the soundtrack stops with it

#### Scenario: Start ends the cutscene early
- GIVEN a movie playing with `options.skip_start` set
- WHEN Start is held at any frame
- THEN `fmv_play` returns `FMV_SKIPPED`

#### Scenario: A movie left alone runs to the end
- GIVEN a movie playing with no skip condition true
- WHEN the last frame is reached
- THEN `fmv_play` returns `FMV_FINISHED`

#### Scenario: A caller's own input handling replaces the pad entirely
- GIVEN a caller that sets `options.skip` to its own predicate
- WHEN the predicate returns non-zero
- THEN playback stops as if a masked button had been pressed, and the
  library reads no pad register itself

### Requirement: The library must give the machine back

A cutscene borrows the console. What it must not do is leave the caller
unable to draw afterwards.

#### Scenario: The registers it changed are set to what the caller declared
- GIVEN a caller that set `options.lspc_mode`, `options.fix_source`,
  `options.palette_bank` and `options.prom_bank` to values of its own
- WHEN a movie plays and returns, whether finished or skipped
- THEN all four registers hold those values

#### Scenario: The restore holds on real hardware
- GIVEN the cutscene example running from a flash cart on an AES
- WHEN the movie finishes and the example redraws its title screen by
  writing fix tiles and nothing else
- THEN the screen appears correctly, which no emulator can settle because
  the registers involved cannot be read back on the machine either

#### Scenario: The caller declares that state because it cannot be read
- GIVEN the LSPC mode register, the fix-source and palette-bank latches
  and the program-bank latch
- WHEN any of them is read
- THEN the value is not the register's contents, so the library must be
  told what to restore rather than discovering it

#### Scenario: What it used is left blank rather than stale
- GIVEN a movie that used the sprites and CRAM banks its config named
- WHEN it returns
- THEN those sprites are disabled and those banks are zeroed

#### Scenario: The caller's own resources are untouched
- GIVEN a config naming a first sprite above the lowest, and a CRAM base
- WHEN the movie plays and returns
- THEN no write landed on any sprite below the first, or on any CRAM
  bank below the base

#### Scenario: Closing an already closed player changes nothing
- GIVEN a player that has been closed
- WHEN `fmv_close` is called again
- THEN no register is written a second time

### Requirement: The library must work with no audio at all

A game with its own Z80 driver must be able to use the video path
without surrendering the M1 ROM.

#### Scenario: A video-only build needs no sound driver
- GIVEN a build compiled with `FMV_NO_AUDIO` and linked without the
  audio module
- WHEN the ROM is linked
- THEN no Z80 symbol is referenced, and the movie still draws and still
  restores the machine

#### Scenario: A caller can silence a build that carries audio
- GIVEN a build with the audio module and `options.audio` cleared
- WHEN the movie starts
- THEN no sound command is sent

### Requirement: The stream must be placed by the linker

#### Scenario: The stream lands in switchable P-ROM by itself
- GIVEN one `__bank`-named stub per switchable bank the stream occupies
- WHEN the project links
- THEN each bank's slice sits at the start of the switchable window, and
  the build fails if anything was linked ahead of it

#### Scenario: Which bank the stream starts at is a link-time choice
- GIVEN a project that passes `--defsym=fmv_stream_base=N`
- WHEN a frame is fetched
- THEN the bank latch selects the bank that offset falls in, so a game's
  own banked code can occupy the banks below

### Requirement: A generated bundle must build in a stock project

#### Scenario: Integration touches only the caller's own files
- GIVEN an unmodified ngdevkit project
- WHEN the emitted folder is copied in and the guide's edits are applied
- THEN the ROM builds with no edit to any linkscript and no edit to any
  file the baker emitted

#### Scenario: The example returns to its own screen intact
- GIVEN the cutscene example built from an emitted bundle
- WHEN the cutscene finishes and the example draws its title screen
  using fix tiles alone
- THEN the screen renders correctly, holds still, and matches no frame
  of the movie

### Requirement: A mismatched bundle must announce itself

#### Scenario: A bundle older than the library beside it
- GIVEN emitted movie data stamped with a baker version
- WHEN it is compiled against library source of a different major or
  minor version
- THEN the build stops and both versions are named

#### Scenario: The library version tracks the package version
- GIVEN a release that bumps the package
- WHEN the suite runs
- THEN a test fails unless `fmv.h` states the same major and minor

### Requirement: The example must remain byte-faithful

#### Scenario: The movie cartridge renders as it did before the split
- GIVEN the same baked frames
- WHEN the cartridge runs under MAME
- THEN the mean absolute error against the baked render stays at or
  below 1.57 of 255, and the match beats its nearest rival by a stated
  margin rather than being chosen by argmin alone

### Requirement: The caller must be told what a tick costs

#### Scenario: The budget is knowable before integration
- GIVEN a baked movie
- WHEN the developer reads the generated header
- THEN it states the worst frame's slot updates, the cycles its inner
  loop spends on them, and the blanking interval that is measured
  against, with the guide saying plainly that the cycle figure is a
  floor rather than a ceiling
