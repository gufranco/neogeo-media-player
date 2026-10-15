# The quality ladder

Reference for the 35 rungs, the levers behind them, and the three mechanisms that keep a bake inside the cartridge. The README covers how a rung gets chosen; this page is the detail behind that choice.

## All 35 rungs

Cost falls strictly from each rung to the next, so a higher number is always cheaper and never looks better. Colour is the only lever until `q30`, falling geometrically at about 6% off the previous rung each time. Frame rate starts dropping at `q31`, once colour has bottomed out at 8%.

| Rung | Colour | Frame rate | Redraw threshold | Cost vs `q01` | Skipped when |
|:-----|-------:|-----------:|-----------------:|--------------:|:-------------|
| `q01` | 100% | 59.2 | 0.000500 | 1.000 | never |
| `q02` | 94% | 59.2 | 0.000558 | 0.979 | never |
| `q03` | 89% | 59.2 | 0.000623 | 0.954 | never |
| `q04` | 84% | 59.2 | 0.000695 | 0.925 | never |
| `q05` | 79% | 59.2 | 0.000775 | 0.900 | never |
| `q06` | 74% | 59.2 | 0.000865 | 0.874 | never |
| `q07` | 70% | 59.2 | 0.000965 | 0.850 | never |
| `q08` | 66% | 59.2 | 0.001077 | 0.829 | never |
| `q09` | 62% | 59.2 | 0.001201 | 0.809 | never |
| `q10` | 58% | 59.2 | 0.001341 | 0.789 | never |
| `q11` | 54% | 59.2 | 0.001496 | 0.770 | never |
| `q12` | 51% | 59.2 | 0.001669 | 0.751 | never |
| `q13` | 48% | 59.2 | 0.001862 | 0.733 | never |
| `q14` | 45% | 59.2 | 0.002078 | 0.713 | never |
| `q15` | 42% | 59.2 | 0.002319 | 0.693 | never |
| `q16` | 39% | 59.2 | 0.002587 | 0.674 | never |
| `q17` | 37% | 59.2 | 0.002887 | 0.654 | never |
| `q18` | 34% | 59.2 | 0.003222 | 0.634 | never |
| `q19` | 31% | 59.2 | 0.003595 | 0.613 | never |
| `q20` | 28% | 59.2 | 0.004011 | 0.593 | never |
| `q21` | 26% | 59.2 | 0.004475 | 0.573 | never |
| `q22` | 24% | 59.2 | 0.004994 | 0.553 | never |
| `q23` | 22% | 59.2 | 0.005572 | 0.532 | never |
| `q24` | 20% | 59.2 | 0.006218 | 0.510 | never |
| `q25` | 18% | 59.2 | 0.006938 | 0.489 | never |
| `q26` | 16% | 59.2 | 0.007741 | 0.466 | never |
| `q27` | 14% | 59.2 | 0.008638 | 0.445 | never |
| `q28` | 12% | 59.2 | 0.009638 | 0.422 | never |
| `q29` | 10% | 59.2 | 0.010754 | 0.401 | never |
| `q30` | 8% | 59.2 | 0.012000 | 0.380 | never |
| `q31` | 8% | 29.6 | 0.012000 | 0.343 | source is 29.6 fps or slower |
| `q32` | 8% | 19.7 | 0.012000 | 0.286 | source is 19.7 fps or slower |
| `q33` | 8% | 14.8 | 0.012000 | 0.233 | source is 14.8 fps or slower |
| `q34` | 8% | 11.8 | 0.012000 | 0.201 | source is 11.8 fps or slower |
| `q35` | 8% | 9.9 | 0.012000 | 0.173 | source is 9.9 fps or slower |

**Redraw threshold** is how far a tile must change before the player spends a slot redrawing it. It rises with the colour reduction, because a picture already charged less for colour error has nothing to gain from being redrawn on a colour change too small to see.

**Skipped when** is about the source. A rung that holds each frame for two refreshes shows the movie at 29.6 fps, which against a 24 fps source drops nothing and saves nothing, so the baker refuses it rather than pretending.

The levers, in order of how much they cost perceptually:

| Lever | What it does |
|---|---|
| Chroma weight | Scales the `a` and `b` axes of the shared Oklab metric, so colour error is charged at a fraction of the rate luma error is |
| Frame hold | Shows each frame for N refreshes. Only worth anything when the effective rate drops below the source rate |
| Denoise | Removes grain the dictionary would otherwise have to store |
| Redraw threshold | How far the picture may drift before a slot is rewritten |


## Per-scene palettes, rate control and colour

**Per-scene palettes.** CRAM holds 240 palettes for video, and one set stretched over a whole feature has to cover every scene in it. The baker cuts the movie into epochs and refits colours for each, which measures about 6% less error on real footage for 1.5% more tiles.

A full set is around 17,900 cycles against the 18,432 the blanking interval affords, so it cannot be written in one frame alongside the picture. Epochs alternate between the two halves of the allocation: while one half is being read, the next epoch is written into the other, a slice per frame across the hundreds of frames an epoch lasts. Seeks and rewinds have no run-up, so they make the target epoch resident at once.

Epochs never share dictionary entries. A tile stores palette indices rather than colours, so one interned while a bank held one epoch's colours draws wrong once that bank holds another's. Scenes share about 0.1% of their tiles. Set `--palette-epoch-seconds 0` for a single shared set.

**Rate control.** A rung is settled from a sample, and a sample cannot know that the third act is busier than the first. Two mechanisms keep the dictionary from running out partway through:

- The dictionary is capped at the budget, so the guarantee is structural.
- A controller keeps the cap out of reach. It compares the recent rate of tile creation against the rate the remaining budget affords, and holds a multiplier that ratchets up while spending runs hot and decays while it does not. The multiplier never falls below one, so the rung's own threshold is a floor and the controller can only tighten.

**Colour.** The Neo Geo colour word is `|D0|R1|G1|B1|R5R4R3R2|G5G4G3G2|B5B4B3B2|`: five independent bits per channel plus `D0`, a sixth bit shared across all three. That is 15-bit colour, not the 12-bit a four-bits-per-channel reading gives. The baker targets geolith's resistor-ladder DAC model of 3900, 2200, 1000, 470 and 220 ohms per channel, which reaches true black where the linear model bottoms out. Distance is measured in Oklab throughout, so palette fitting, tile assignment, redraw decisions and the fidelity metric all agree on what close means.


