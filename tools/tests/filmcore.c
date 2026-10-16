#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum {
    WIDTH = 304,
    HEIGHT = 224,
    CHANNELS = 3,
    FRAME_BYTES = WIDTH * HEIGHT * CHANNELS,
    ENV_SET_PIXEL_FORMAT = 10,
    PIXEL_XRGB8888 = 1
};

struct retro_game_info {
    const char *path;
    const void *data;
    size_t size;
    const char *meta;
};

struct retro_system_info {
    const char *library_name;
    const char *library_version;
    const char *valid_extensions;
    bool need_fullpath;
    bool block_extract;
};

struct retro_game_geometry {
    unsigned base_width;
    unsigned base_height;
    unsigned max_width;
    unsigned max_height;
    float aspect_ratio;
};

struct retro_system_timing {
    double fps;
    double sample_rate;
};

struct retro_system_av_info {
    struct retro_game_geometry geometry;
    struct retro_system_timing timing;
};

typedef bool (*environment_t)(unsigned, void *);
typedef void (*video_t)(const void *, unsigned, unsigned, size_t);
typedef void (*audio_sample_t)(int16_t, int16_t);
typedef size_t (*audio_batch_t)(const int16_t *, size_t);
typedef void (*input_poll_t)(void);
typedef int16_t (*input_state_t)(unsigned, unsigned, unsigned, unsigned);

static environment_t environment;
static video_t video;
static uint8_t *film;
static size_t film_frames;
static size_t shown;
static uint32_t frame[WIDTH * HEIGHT];

unsigned retro_api_version(void) { return 1; }
void retro_set_environment(environment_t callback) { environment = callback; }
void retro_set_video_refresh(video_t callback) { video = callback; }
void retro_set_audio_sample(audio_sample_t callback) { (void)callback; }
void retro_set_audio_sample_batch(audio_batch_t callback) { (void)callback; }
void retro_set_input_poll(input_poll_t callback) { (void)callback; }
void retro_set_input_state(input_state_t callback) { (void)callback; }

void retro_init(void) { shown = 0; }

void retro_unload_game(void) {
    free(film);
    film = NULL;
    film_frames = 0;
}

void retro_deinit(void) { retro_unload_game(); }

void retro_get_system_info(struct retro_system_info *info) {
    memset(info, 0, sizeof(*info));
    info->library_name = "filmcore";
    info->library_version = "1";
    info->valid_extensions = "rgb";
}

void retro_get_system_av_info(struct retro_system_av_info *info) {
    memset(info, 0, sizeof(*info));
    info->geometry.base_width = WIDTH;
    info->geometry.base_height = HEIGHT;
    info->geometry.max_width = WIDTH;
    info->geometry.max_height = HEIGHT;
    info->timing.fps = 60.0;
    info->timing.sample_rate = 48000.0;
}

bool retro_load_game(const struct retro_game_info *game) {
    unsigned format = PIXEL_XRGB8888;
    if (game == NULL || game->data == NULL || game->size < FRAME_BYTES) {
        return false;
    }
    film_frames = game->size / FRAME_BYTES;
    film = malloc(film_frames * FRAME_BYTES);
    if (film == NULL) {
        return false;
    }
    memcpy(film, game->data, film_frames * FRAME_BYTES);
    return environment(ENV_SET_PIXEL_FORMAT, &format);
}

void retro_run(void) {
    const uint8_t *source = film + (shown % film_frames) * FRAME_BYTES;
    for (size_t pixel = 0; pixel < WIDTH * HEIGHT; pixel += 1) {
        const uint8_t *rgb = source + pixel * CHANNELS;
        frame[pixel] = ((uint32_t)rgb[0] << 16) | ((uint32_t)rgb[1] << 8) | rgb[2];
    }
    video(frame, WIDTH, HEIGHT, WIDTH * sizeof(uint32_t));
    shown += 1;
}
