#ifndef FMV_GUARD_H
#define FMV_GUARD_H

#include <stdint.h>

#define FMV_SPRITE_COUNT          381u
#define FMV_SPRITE_TILE_ROWS      32u
#define FMV_PALETTE_BANKS         256u
#define FMV_SCB1_WORDS_PER_TILE   2u

typedef struct {
    uint16_t first;
    uint32_t end;
    uint16_t max_tiles;
} fmv_stream_limits;

typedef struct {
    uint16_t first_sprite;
    uint16_t grid_cols;
    uint16_t grid_rows;
    uint16_t palette_base;
    uint16_t epoch_palettes;
    uint16_t epoch_count;
    uint16_t caller_first_sprite;
} fmv_layout;

int fmv_run_fits(const fmv_stream_limits *limits, uint16_t address, uint16_t tiles,
                 uint16_t written);
int fmv_layout_fits(const fmv_layout *layout);

#endif
