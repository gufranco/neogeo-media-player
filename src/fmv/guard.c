#include "guard.h"

int fmv_run_fits(const fmv_stream_limits *limits, uint16_t address, uint16_t tiles,
                 uint16_t written)
{
    uint32_t end = (uint32_t)address + (uint32_t)tiles * FMV_SCB1_WORDS_PER_TILE;

    if (address < limits->first || end > limits->end) {
        return 0;
    }
    return (uint32_t)written + tiles <= limits->max_tiles;
}

static int sprites_fit(uint16_t first, uint16_t cols)
{
    return cols != 0u && (uint32_t)first + cols <= FMV_SPRITE_COUNT;
}

int fmv_layout_fits(const fmv_layout *layout)
{
    uint32_t banks = (uint32_t)layout->palette_base + 2u * (uint32_t)layout->epoch_palettes;

    if (!sprites_fit(layout->first_sprite, layout->grid_cols)
        || !sprites_fit(layout->caller_first_sprite, layout->grid_cols)) {
        return 0;
    }
    if (layout->grid_rows > FMV_SPRITE_TILE_ROWS || layout->epoch_count == 0u) {
        return 0;
    }
    return banks <= FMV_PALETTE_BANKS;
}
