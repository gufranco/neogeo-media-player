# Hardware encodings and timing

Every bit layout below was read out of an emulator's source rather than from a prose summary, and the timing section records what the build gate enforces.

## Encodings read from the decoders

Sources: [geolith-libretro](https://github.com/libretro/geolith-libretro) `src/geo_lspc.c`, and [mamedev/mame](https://github.com/mamedev/mame) `src/mame/snk/neogeo_spr.cpp`, `neogeo.cpp`, `src/devices/bus/neogeo/slot.cpp`.

| Encoding | Value |
|---|---|
| SCB1 tile number | `even_word \| ((odd_word & 0x00F0) << 12)`, 20 bits |
| SCB1 palette | odd bits 15 to 8 |
| SCB1 hflip / vflip | odd bit 0 / odd bit 1 |
| SCB1 auto-animation | odd bits 3 to 2 |
| SCB3 | bit 6 sticky, bits 15 to 7 are `512 - top`, bits 5 to 0 height in tiles |
| Sprite loop | `for i = 1; i < 382`, so sprite 0 never draws |
| Tile bytes | 128 bytes, byte-interleaved c1 and c2, columns 8 to 15 first, four bytes per row, bit `n` is column `n`, leftmost pixel is the least significant bit |
| Colour word | `\|D0\|R1\|G1\|B1\|R5R4R3R2\|G5G4G3G2\|B5B4B3B2\|`, 15-bit colour |
| ADPCM-B rate | `f = 55555 * DeltaN / 65535`, 1.85 kHz to 55.5 kHz |
| ADPCM-B ROM | 16 MiB, one continuous loopable sample |
| Watchdog | About 0.13 s, roughly 7.7 frames |

Where the two disagree, the board decides. MAME masks the program-ROM bank register with `0x07`, giving 8 banks of 1 MiB, which matches the three-bit latch. geolith derives its mask from the ROM size and allows up to 8 bits, so a stream needing more than 8 banks would work there and read the wrong bank on hardware. The baker enforces MAME's limit.


## VRAM timing, checked on every build

The NeoGeo Development Wiki's VRAM page requires at least 12 CPU cycles between consecutive data writes and at least 16 cycles after a write before setting a new address. C cannot express instruction spacing, so a check holds the result instead.

[`check_vram_timing.py`](../tools/scripts/check_vram_timing.py) walks the compiled objects, models each write as its bus cycles rather than as an instruction, follows branches across the whole reachable window, and fails on any pair under the floor. It runs right after the compile step in [`build-in-docker.sh`](../toolchain/build-in-docker.sh):

```
CHECK VRAM write spacing
VRAM write spacing clears the 12 and 16 cycle minimums across 2 object(s)
```

The tightest pair anywhere in the player is 20 cycles.

One documented claim did not survive a source read. Bit 15 of `$3C0006` is described as a vblank flag; the register is a raster line counter, and bit 15 is bit 8 of that counter, low for values `0xF8` to `0xFF` and high for `0x100` to `0x1FF`. It marks 8 scanlines out of 264 rather than a blanking interval. `wait_vblank` waits for the start of blanking instead. Blanking is 40 lines, not 24: MAME's raster is 264 lines with 224 visible, `NEOGEO_VBEND` 0x010 to `NEOGEO_VBSTART` 0x0F0 in `neogeo_spr.h`, its line counter is the screen line plus 0x100 wrapping to 0xF8 (`get_video_control` in `neogeo_v.cpp`), and geolith draws the same 224 visible lines. So the counter is blank from 0x1F0 to 0x1FF, from 0xF8 to 0xFF and from 0x100 to 0x10F. The player counts 39 of those lines, 29,952 cycles at 768 a line, and leaves out 0x10F because the video chip prepares the first visible line during it. Measured under MAME on the same cartridge across 60 emulated seconds each:

| Sync point | Frames | Overruns | Rate |
|---|---|---|---|
| Bit 15, the last 8 lines | 2,743 | 631 | 23.0% |
| Start of blanking | 2,743 | 64 | 2.3% |

The frame count is identical either way, and the hardware permits the overrun regardless.


