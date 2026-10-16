#include <stdint.h>

#include "fmv.h"
#include "hw.h"
#include "menu.h"
#include "movie_data.h"
#include "timeline.h"

#define OVERLAY_HOLD_FRAMES    180
#define OVERLAY_REDRAW_MASK    0x07
#define DEBUG_ROW_MASK         0x0Fu
#define REWIND_FRAMES_PER_STEP 6
#define SEEK_SECONDS           10u
#define FAULT_RED              0x4F00u
#define RESTART_BUTTONS        (FMV_PAD_A | FMV_PAD_B)

static const uint16_t speed_ladder[] = {2, 5, 10};
#define SPEED_STEPS ((uint16_t)(sizeof(speed_ladder) / sizeof(speed_ladder[0])))

typedef struct {
    uint8_t pad;
    uint8_t status;
} buttons;

typedef struct {
    transport_state state;
    uint16_t speed_index;
    uint16_t speed;
    uint32_t frame;
    uint16_t overlay_timer;
    uint16_t rewind_countdown;
    uint16_t overlay_tick;
    uint16_t resident_cue;
    uint8_t overlay_visible;
    uint8_t debug_visible;
    uint8_t subtitles_on;
    uint8_t sound_on;
    debug_stats diag;
} session;

static fmv_player video;

static void clear_vram(void)
{
    vram_fill(VRAM_SCB1, VRAM_LOWER_WORDS, 0);
    vram_fill(VRAM_SCB2, VRAM_UPPER_WORDS, 0);
}

static void clear_reserved_palettes(void)
{
    volatile uint16_t *target = PALRAM;
    uint16_t reserved = (uint16_t)(MOVIE_PALETTE_BASE * PALETTE_WORDS);

    while (reserved--) {
        *target++ = 0;
    }
}

static uint32_t seconds_to_frames(uint32_t seconds)
{
    return timeline_seconds_to_frames(seconds, MOVIE_FPS_NUM, MOVIE_FPS_DEN);
}

static buttons read_buttons(void)
{
    buttons now;

    now.pad = (uint8_t)~REG_P1CNT;
    now.status = (uint8_t)(~REG_STATUS_B & (FMV_START | STATUS_SELECT));
    return now;
}

static void begin_playing(session *s)
{
    fmv_options options = fmv_defaults();

    options.skip_pad = 0;
    options.skip_start = 0;
    options.audio = s->sound_on;
    fmv_open(&video, &fmv_movie_data, &options);
    fmv_start(&video);
    s->frame = fmv_position(&video);
    s->state = TRANSPORT_PLAY;
    s->speed = 1;
    s->resident_cue = MOVIE_SUBTITLE_COUNT;
    s->overlay_timer = OVERLAY_HOLD_FRAMES;
}

static void stop_playing(session *s)
{
    fmv_close(&video);
    menu_hide();
    menu_subtitle_hide();
    menu_debug_hide();
    s->overlay_visible = 0;
    s->debug_visible = 0;
    s->state = TRANSPORT_STOP;
}

static void show_fault(void)
{
    fmv_close(&video);
    menu_hide();
    menu_subtitle_hide();
    menu_debug_hide();
    PALRAM[PALRAM_BACKDROP] = FAULT_RED;
    for (;;) {
        wait_vblank();
        watchdog_kick();
    }
}

static void toggle_pause(session *s)
{
    s->state = (s->state == TRANSPORT_PAUSE) ? TRANSPORT_PLAY : TRANSPORT_PAUSE;
    s->speed = 1;
    if (s->state == TRANSPORT_PAUSE) {
        fmv_pause(&video);
    } else {
        fmv_resume(&video);
    }
}

static void toggle_sound(session *s)
{
    s->sound_on = (uint8_t)!s->sound_on;
    fmv_set_audio(&video, s->sound_on);
    if (s->sound_on && s->state == TRANSPORT_PLAY) {
        fmv_resume(&video);
    }
}

static void fast_forward(session *s)
{
    if (s->state != TRANSPORT_FORWARD) {
        s->speed_index = 0;
    } else if (s->speed_index + 1 < SPEED_STEPS) {
        s->speed_index++;
    }
    s->state = TRANSPORT_FORWARD;
    s->speed = speed_ladder[s->speed_index];
    fmv_pause(&video);
}

static void start_rewind(session *s)
{
    s->state = TRANSPORT_REWIND;
    s->speed = 1;
    s->rewind_countdown = REWIND_FRAMES_PER_STEP;
    fmv_pause(&video);
}

static void seek_to(session *s, uint32_t frame)
{
    fmv_seek(&video, frame);
    s->frame = fmv_position(&video);
    s->state = TRANSPORT_PLAY;
    s->speed = 1;
}

static void toggle_subtitles(session *s)
{
    s->subtitles_on = (uint8_t)!s->subtitles_on;
    if (!s->subtitles_on) {
        menu_subtitle_hide();
    }
    s->resident_cue = MOVIE_SUBTITLE_COUNT;
}

static void toggle_debug(session *s)
{
    s->debug_visible = (uint8_t)!s->debug_visible;
    if (!s->debug_visible) {
        menu_debug_hide();
    }
}

static void play_normally(session *s)
{
    s->state = TRANSPORT_PLAY;
    s->speed = 1;
    fmv_resume(&video);
}

static void handle_transport(session *s, uint8_t pressed)
{
    uint32_t back = seconds_to_frames(SEEK_SECONDS);

    if (pressed & FMV_PAD_A) {
        toggle_pause(s);
    }
    if (pressed & FMV_PAD_B) {
        play_normally(s);
    }
    if (pressed & FMV_PAD_RIGHT) {
        fast_forward(s);
    }
    if (pressed & FMV_PAD_LEFT) {
        start_rewind(s);
    }
    if (pressed & FMV_PAD_C) {
        seek_to(s, (s->frame > back) ? s->frame - back : 0);
    }
    if (pressed & FMV_PAD_D) {
        seek_to(s, s->frame + back);
    }
}

static void handle_input(session *s, buttons pressed)
{
    if (pressed.pad || pressed.status) {
        s->overlay_timer = OVERLAY_HOLD_FRAMES;
    }
    if (s->state == TRANSPORT_STOP) {
        if ((pressed.pad & RESTART_BUTTONS) || (pressed.status & FMV_START)) {
            begin_playing(s);
        }
        return;
    }
    if (pressed.status & FMV_START) {
        stop_playing(s);
        return;
    }
    handle_transport(s, pressed.pad);
    if (pressed.pad & FMV_PAD_UP) {
        toggle_sound(s);
    }
    if (pressed.pad & FMV_PAD_DOWN) {
        toggle_subtitles(s);
    }
    if (pressed.status & STATUS_SELECT) {
        toggle_debug(s);
    }
}

static void step_rewind(session *s)
{
    fmv_hold(&video);
    if (--s->rewind_countdown != 0) {
        return;
    }
    s->rewind_countdown = REWIND_FRAMES_PER_STEP;
    if (s->frame == 0) {
        s->state = TRANSPORT_PLAY;
        fmv_resume(&video);
        return;
    }
    fmv_seek(&video, s->frame - 1u);
    s->frame = fmv_position(&video);
}

static void step_forward(session *s)
{
    uint16_t steps = s->speed;

    while (steps--) {
        fmv_tick(&video);
        if (fmv_faulted(&video)) {
            return;
        }
        if (fmv_ended(&video)) {
            fmv_seek(&video, 0);
            if (s->state != TRANSPORT_PLAY) {
                fmv_pause(&video);
            }
            break;
        }
    }
    s->frame = fmv_position(&video);
}

static void step_video(session *s)
{
    switch (s->state) {
    case TRANSPORT_STOP:
        break;
    case TRANSPORT_PAUSE:
        fmv_hold(&video);
        break;
    case TRANSPORT_REWIND:
        step_rewind(s);
        break;
    case TRANSPORT_FORWARD:
    case TRANSPORT_PLAY:
    default:
        step_forward(s);
        break;
    }
}

static void note_deadline(session *s)
{
    if (!in_vblank()) {
        s->diag.overran = 1;
        s->diag.overruns++;
    } else {
        s->diag.overran = 0;
    }
}

static void draw_overlay(session *s)
{
    if (s->state == TRANSPORT_STOP) {
        return;
    }
    if (s->overlay_timer) {
        s->overlay_timer--;
        if (!s->overlay_visible || (s->overlay_tick & OVERLAY_REDRAW_MASK) == 0) {
            menu_draw(s->state, s->speed, s->sound_on, s->frame, MOVIE_FRAME_COUNT);
        }
        s->overlay_visible = 1;
    } else if (s->overlay_visible) {
        menu_hide();
        s->overlay_visible = 0;
    }
}

#if MOVIE_SUBTITLE_COUNT > 0
#define SUBTITLE_RECORD_BYTES (8u + MOVIE_SUBTITLE_COLUMNS * MOVIE_SUBTITLE_LINES)

static void draw_subtitles(session *s)
{
    uint16_t cue;

    if (!s->subtitles_on || s->state == TRANSPORT_STOP) {
        return;
    }
    cue = timeline_subtitle_at(movie_subtitles, MOVIE_SUBTITLE_COUNT, SUBTITLE_RECORD_BYTES,
                               s->frame);
    if (cue == s->resident_cue) {
        return;
    }
    s->resident_cue = cue;
    if (cue < MOVIE_SUBTITLE_COUNT) {
        menu_subtitle_show(movie_subtitles + (uint32_t)cue * SUBTITLE_RECORD_BYTES + 8u);
    } else {
        menu_subtitle_hide();
    }
}
#else
static void draw_subtitles(session *s)
{
    (void)s;
}
#endif

static void draw_diagnostics(session *s)
{
    uint16_t updates = fmv_last_updates(&video);

    if (updates > s->diag.peak_updates) {
        s->diag.peak_updates = updates;
    }
    if (!s->debug_visible) {
        return;
    }
    s->diag.frame = s->frame;
    s->diag.total = MOVIE_FRAME_COUNT;
    s->diag.epoch = fmv_epoch(&video);
    s->diag.bank = fmv_stream_bank(&video);
    s->diag.audio_page = timeline_audio_page(s->frame, MOVIE_AUDIO_PAGE_NUM,
                                             MOVIE_AUDIO_PAGE_DEN);
    s->diag.updates = updates;
    menu_debug_row(&s->diag, (uint16_t)(s->overlay_tick & DEBUG_ROW_MASK));
}

int main(void)
{
    session s = {0};
    buttons previous = read_buttons();

    s.subtitles_on = 1;
    s.sound_on = 1;
    clear_vram();
    watchdog_kick();
    clear_reserved_palettes();
    menu_init();
    begin_playing(&s);

    for (;;) {
        buttons now = read_buttons();
        buttons pressed;

        pressed.pad = (uint8_t)(now.pad & ~previous.pad);
        pressed.status = (uint8_t)(now.status & ~previous.status);
        previous = now;
        handle_input(&s, pressed);
        wait_vblank();
        watchdog_kick();
        step_video(&s);
        note_deadline(&s);
        draw_overlay(&s);
        draw_subtitles(&s);
        draw_diagnostics(&s);
        fmv_prepare(&video);
        if (fmv_faulted(&video)) {
            show_fault();
        }
        s.overlay_tick++;
    }
}
