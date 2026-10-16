#include "fmv.h"

#include "fmv_audio.h"
#include "guard.h"
#include "hw.h"
#include "timeline.h"

#define SPRITE_DISABLED    0
#define DEFAULT_FIRST_SPRITE 1
#define DEFAULT_SKIP_PAD   (FMV_PAD_A)
#define DEFAULT_SKIP_START 1
#define DEFAULT_LSPC_MODE  0
#define NO_FRAME           0xFFFFFFFFu
#define NO_BANK            0xFFFFu
#define RUN_HEADER_WORDS   2u

static uint16_t epoch_words(const fmv_player *player)
{
    return player->epoch_words;
}

static volatile uint16_t *epoch_cram(const fmv_player *player, uint16_t epoch)
{
    return PALRAM + (player->movie->palette_base * PALETTE_WORDS)
           + (epoch & 1u) * epoch_words(player);
}

static const uint16_t *epoch_source(const fmv_player *player, uint16_t epoch)
{
    return (const uint16_t *)player->movie->palettes + (uint32_t)epoch * epoch_words(player);
}

static uint32_t epoch_start(const fmv_player *player, uint16_t epoch)
{
    return ((const uint32_t *)player->movie->epochs)[epoch];
}

static void upload_epoch(const fmv_player *player, uint16_t epoch)
{
    const uint16_t *source = epoch_source(player, epoch);
    volatile uint16_t *target = epoch_cram(player, epoch);
    uint16_t words = epoch_words(player);

    while (words--) {
        *target++ = *source++;
    }
}

static void upload_palette_slice(fmv_player *player)
{
    const uint16_t *source;
    volatile uint16_t *target;
    uint16_t words = player->movie->epoch_slice;
    uint16_t total = epoch_words(player);

    if (player->loading_epoch >= player->movie->epoch_count || player->loading_word >= total) {
        return;
    }
    source = epoch_source(player, player->loading_epoch) + player->loading_word;
    target = epoch_cram(player, player->loading_epoch) + player->loading_word;
    if (player->loading_word + words > total) {
        words = (uint16_t)(total - player->loading_word);
    }
    player->loading_word = (uint16_t)(player->loading_word + words);
    while (words--) {
        *target++ = *source++;
    }
}

static void begin_loading(fmv_player *player, uint16_t epoch)
{
    player->loading_epoch = epoch;
    player->loading_word = 0;
}

static void palettes_for_frame(fmv_player *player, uint32_t frame)
{
    uint16_t epoch = 0;

    while (epoch + 1u < player->movie->epoch_count
           && epoch_start(player, (uint16_t)(epoch + 1u)) <= frame) {
        epoch++;
    }
    upload_epoch(player, epoch);
    player->resident_epoch = epoch;
    begin_loading(player, (uint16_t)(epoch + 1u));
}

static void follow_epoch(fmv_player *player, uint32_t frame)
{
    uint16_t next = (uint16_t)(player->resident_epoch + 1u);

    if (next < player->movie->epoch_count && frame >= epoch_start(player, next)) {
        player->resident_epoch = next;
        begin_loading(player, (uint16_t)(next + 1u));
    }
    upload_palette_slice(player);
}

static void setup_sprite_grid(const fmv_player *player)
{
    const fmv_options *options = &player->options;

    for (uint16_t column = 0; column < player->movie->grid_cols; column++) {
        uint16_t sprite = (uint16_t)(options->first_sprite + column);

        vram_poke((uint16_t)(VRAM_SCB2 + sprite), SCB2_NO_SHRINK);
        if (column == 0) {
            vram_poke((uint16_t)(VRAM_SCB3 + sprite),
                      scb3_word(options->top_line, 0, player->movie->grid_rows));
            vram_poke((uint16_t)(VRAM_SCB4 + sprite), scb4_word(options->left_pixel));
        } else {
            vram_poke((uint16_t)(VRAM_SCB3 + sprite),
                      scb3_word(options->top_line, SCB3_STICKY, 0));
        }
    }
}

static void retire_sprite_grid(const fmv_player *player)
{
    for (uint16_t column = 0; column < player->movie->grid_cols; column++) {
        uint16_t sprite = (uint16_t)(player->options.first_sprite + column);

        vram_poke((uint16_t)(VRAM_SCB3 + sprite), SPRITE_DISABLED);
    }
}

static void blank_owned_palettes(const fmv_player *player)
{
    volatile uint16_t *target = PALRAM + (player->movie->palette_base * PALETTE_WORDS);
    uint16_t words = (uint16_t)(epoch_words(player) * 2u);

    while (words--) {
        *target++ = 0;
    }
}

static const uint16_t *frame_cursor(fmv_player *player, uint32_t frame)
{
    const uint32_t *index = (const uint32_t *)player->movie->index;
    uint32_t offset = player->movie->stream_base + index[frame];
    uint16_t wanted = (uint16_t)(offset / PROM_BANK_BYTES);

    if (wanted != player->stream_bank) {
        PROM_BANK_SELECT = wanted;
        player->stream_bank = wanted;
    }
    return (const uint16_t *)(PROM_BANK_WINDOW + (offset % PROM_BANK_BYTES));
}

static fmv_stream_limits stream_limits(const fmv_movie *movie)
{
    fmv_stream_limits limits;

    limits.first = (uint16_t)(movie->first_sprite * SCB1_WORDS_PER_SPRITE);
    limits.end = ((uint32_t)movie->first_sprite + movie->grid_cols) * SCB1_WORDS_PER_SPRITE;
    limits.max_tiles = movie->max_updates;
    return limits;
}

static int frame_valid(fmv_player *player, uint32_t frame)
{
    fmv_stream_limits limits = stream_limits(player->movie);
    const uint16_t *cursor;
    uint16_t runs;
    uint16_t written = 0;

    if (frame >= player->movie->frames) {
        return 0;
    }
    cursor = frame_cursor(player, frame);
    runs = *cursor++;
    if (runs > limits.max_tiles) {
        return 0;
    }
    while (runs--) {
        uint16_t tiles = cursor[1];

        if (!fmv_run_fits(&limits, cursor[0], tiles, written)) {
            return 0;
        }
        written = (uint16_t)(written + tiles);
        cursor += RUN_HEADER_WORDS + (uint32_t)tiles * FMV_SCB1_WORDS_PER_TILE;
    }
    return 1;
}

static void check_frame(fmv_player *player, uint32_t frame)
{
    if (player->faulted || player->checked_frame == frame) {
        return;
    }
    if (!frame_valid(player, frame)) {
        player->faulted = 1;
        return;
    }
    player->checked_frame = frame;
}

static void apply_frame(fmv_player *player, uint32_t frame)
{
    const uint16_t *cursor;
    uint16_t runs;

    check_frame(player, frame);
    if (player->faulted) {
        return;
    }
    cursor = frame_cursor(player, frame);
    runs = *cursor++;
    player->updates = 0;

    while (runs--) {
        uint16_t address = *cursor++;
        uint16_t tiles = *cursor++;

        REG_VRAMADDR = (uint16_t)(address + player->sprite_offset);
        REG_VRAMMOD = 1;
        player->updates = (uint16_t)(player->updates + tiles);
        while (tiles--) {
            REG_VRAMRW = *cursor++;
            REG_VRAMRW = *cursor++;
        }
    }
}

static fmv_layout movie_layout(const fmv_movie *movie, const fmv_options *options)
{
    fmv_layout layout;

    layout.first_sprite = movie->first_sprite;
    layout.grid_cols = movie->grid_cols;
    layout.grid_rows = movie->grid_rows;
    layout.palette_base = movie->palette_base;
    layout.epoch_palettes = movie->epoch_palettes;
    layout.epoch_count = movie->epoch_count;
    layout.caller_first_sprite = options->first_sprite;
    return layout;
}

fmv_options fmv_defaults(void)
{
    fmv_options options;

    options.first_sprite = DEFAULT_FIRST_SPRITE;
    options.top_line = 0;
    options.left_pixel = 0;
    options.lspc_mode = DEFAULT_LSPC_MODE;
    options.fix_source = FMV_FIX_CART;
    options.palette_bank = 0;
    options.prom_bank = 0;
    options.skip_pad = DEFAULT_SKIP_PAD;
    options.skip_start = DEFAULT_SKIP_START;
    options.audio = 1;
    options.skip = 0;
    options.skip_user = 0;
    return options;
}

static void restore_machine(const fmv_options *options)
{
    REG_LSPCMODE = options->lspc_mode;
    if (options->fix_source == FMV_FIX_BOARD) {
        select_board_fix_rom();
    } else {
        select_cart_fix_rom();
    }
    if (options->palette_bank != 0) {
        select_palette_bank_one();
    } else {
        select_palette_bank_zero();
    }
    PROM_BANK_SELECT = options->prom_bank;
}

void fmv_open(fmv_player *player, const fmv_movie *movie, const fmv_options *options)
{
    fmv_layout layout = movie_layout(movie, options);

    player->movie = movie;
    player->options = *options;
    player->checked_frame = NO_FRAME;
    player->faulted = 0;
    player->open = 0;
    if (!fmv_layout_fits(&layout)) {
        player->faulted = 1;
        return;
    }
    player->epoch_words = (uint16_t)(movie->epoch_palettes * PALETTE_WORDS);
    player->sprite_offset = (uint16_t)((player->options.first_sprite - movie->first_sprite)
                                       * SCB1_WORDS_PER_SPRITE);
    player->frame = 0;
    player->resident_epoch = 0;
    player->loading_epoch = 0;
    player->loading_word = 0;
    player->stream_bank = NO_BANK;
    player->updates = 0;
    player->audio_running = 0;
    player->open = 1;

    REG_LSPCMODE = LSPC_DISABLE_AUTOANIM;
    select_cart_fix_rom();
    select_palette_bank_zero();
    watchdog_kick();
    palettes_for_frame(player, 0);
    watchdog_kick();
    setup_sprite_grid(player);
}

void fmv_start(fmv_player *player)
{
    if (player->faulted) {
        return;
    }
    wait_vblank();
    watchdog_kick();
    apply_frame(player, 0);
    player->frame = 1;
    fmv_audio_cue(player, 0);
}

void fmv_tick(fmv_player *player)
{
    if (fmv_ended(player)) {
        return;
    }
    follow_epoch(player, player->frame);
    apply_frame(player, player->frame);
    player->frame++;
}

void fmv_hold(fmv_player *player)
{
    if (player->faulted) {
        return;
    }
    follow_epoch(player, player->frame);
}

void fmv_pause(fmv_player *player)
{
    fmv_audio_halt(player);
}

void fmv_resume(fmv_player *player)
{
    fmv_audio_cue(player, player->frame);
}

void fmv_seek(fmv_player *player, uint32_t frame)
{
    uint32_t target = timeline_clamp_frame(frame, player->movie->frames);
    uint32_t landing = timeline_keyframe_at_or_before(
        (const uint32_t *)player->movie->keyframes, player->movie->keyframe_count, target);

    if (player->faulted) {
        return;
    }
    palettes_for_frame(player, landing);
    apply_frame(player, landing);
    player->frame = landing + 1u;
    fmv_audio_cue(player, landing);
}

void fmv_prepare(fmv_player *player)
{
    if (!fmv_ended(player)) {
        check_frame(player, player->frame);
    }
}

void fmv_set_audio(fmv_player *player, int on)
{
    player->options.audio = (uint8_t)(on != 0);
    if (!on) {
        fmv_audio_halt(player);
    }
}

void fmv_close(fmv_player *player)
{
    if (!player->open) {
        return;
    }
    fmv_audio_halt(player);
    retire_sprite_grid(player);
    blank_owned_palettes(player);
    restore_machine(&player->options);
    player->stream_bank = NO_BANK;
    player->open = 0;
}

int fmv_ended(const fmv_player *player)
{
    return player->faulted || player->frame >= player->movie->frames;
}

int fmv_faulted(const fmv_player *player)
{
    return player->faulted;
}

uint32_t fmv_position(const fmv_player *player)
{
    return player->frame;
}

uint16_t fmv_last_updates(const fmv_player *player)
{
    return player->updates;
}

uint16_t fmv_epoch(const fmv_player *player)
{
    return player->resident_epoch;
}

uint16_t fmv_stream_bank(const fmv_player *player)
{
    return player->stream_bank;
}

static int viewer_skipped(const fmv_player *player)
{
    const fmv_options *options = &player->options;

    if (options->skip != 0) {
        return options->skip(options->skip_user);
    }
    if (options->skip_pad != 0 && ((uint8_t)~REG_P1CNT & options->skip_pad) != 0) {
        return 1;
    }
    return options->skip_start != 0 && ((uint8_t)~REG_STATUS_B & FMV_START) != 0;
}

fmv_result fmv_play(const fmv_movie *movie, const fmv_options *options)
{
    fmv_player player;
    fmv_result outcome = FMV_FINISHED;

    fmv_open(&player, movie, options);
    fmv_start(&player);
    while (!fmv_ended(&player)) {
        if (viewer_skipped(&player)) {
            outcome = FMV_SKIPPED;
            break;
        }
        wait_vblank();
        watchdog_kick();
        fmv_tick(&player);
        fmv_prepare(&player);
    }
    if (fmv_faulted(&player)) {
        outcome = FMV_CORRUPT;
    }
    fmv_close(&player);
    return outcome;
}
