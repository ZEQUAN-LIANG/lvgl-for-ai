
#ifndef SPECTRUM_H
#define SPECTRUM_H

#include "lvgl.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#define SPECTRUM_SCREEN_W      800
#define SPECTRUM_SCREEN_H      600
#define SPECTRUM_PANEL_Y       74
#define SPECTRUM_PANEL_W       152
#define SPECTRUM_PANEL_H       404
#define SPECTRUM_LEFT_X        20
#define SPECTRUM_RIGHT_X       628
#define SPECTRUM_VIZ_X         0
#define SPECTRUM_VIZ_Y         0
#define SPECTRUM_VIZ_W         800
#define SPECTRUM_VIZ_H         600
#define SPECTRUM_VIZ_CX        400
#define SPECTRUM_VIZ_CY        282
#define SPECTRUM_TRACK_COUNT   3
#define SPECTRUM_BAND_COUNT    48
#define SPECTRUM_WAVE_COUNT    160
#define SPECTRUM_LOUD_SEGMENTS 14
#define SPECTRUM_MINI_BARS     16

typedef enum {
    SPECTRUM_MODE_ORBIT,
    SPECTRUM_MODE_DUAL,
    SPECTRUM_MODE_RADIAL,
    SPECTRUM_MODE_SPIRAL,
    SPECTRUM_MODE_SONAR,
    SPECTRUM_MODE_STARS,
    SPECTRUM_MODE_COUNT
} spectrum_mode_t;

typedef enum {
    SPECTRUM_PALETTE_ION,
    SPECTRUM_PALETTE_MAGMA,
    SPECTRUM_PALETTE_VERDANT,
    SPECTRUM_PALETTE_COUNT
} spectrum_palette_id_t;

typedef enum {
    SPECTRUM_FONT_SANS_14,
    SPECTRUM_FONT_MONO_7,
    SPECTRUM_FONT_MONO_8,
    SPECTRUM_FONT_MONO_9,
    SPECTRUM_FONT_MONO_9B,
    SPECTRUM_FONT_MONO_32,
    SPECTRUM_FONT_COUNT
} spectrum_font_id_t;

typedef enum {
    SPECTRUM_ICON_LOGO,
    SPECTRUM_ICON_PLAY,
    SPECTRUM_ICON_PAUSE,
    SPECTRUM_ICON_PREV,
    SPECTRUM_ICON_NEXT,
    SPECTRUM_ICON_HEART,
    SPECTRUM_ICON_HEART_FILLED,
    SPECTRUM_ICON_PALETTE,
    SPECTRUM_ICON_AUTO,
    SPECTRUM_ICON_VOLUME,
    SPECTRUM_ICON_ORBIT,
    SPECTRUM_ICON_DUAL,
    SPECTRUM_ICON_RADIAL,
    SPECTRUM_ICON_SPIRAL,
    SPECTRUM_ICON_SONAR,
    SPECTRUM_ICON_STARS,
    SPECTRUM_ICON_COUNT
} spectrum_icon_id_t;

typedef struct {
    const char * title;
    const char * artist;
    int bpm;
    int duration;
    const char * key;
    int seed;
    int palette;
} spectrum_track_t;

typedef struct {
    const char * name;
    uint32_t bg0;
    uint32_t bg1;
    uint32_t a;
    uint32_t b;
    uint32_t c;
    uint32_t soft;
    uint32_t dim;
} spectrum_palette_t;

typedef struct {
    float bands[SPECTRUM_BAND_COUNT];
    float targets[SPECTRUM_BAND_COUNT];
    float peaks[SPECTRUM_BAND_COUNT];
    float wave[SPECTRUM_WAVE_COUNT];
    double time;
    double playhead;
    double duration;
    double bpm;
    double beat_phase;
    double beat_pulse;
    double drop;
    double low;
    double mid;
    double high;
    double energy;
    int beat;
    bool playing;
    bool just_beat;
    bool just_drop;
    double burst;
} spectrum_sim_t;

typedef struct {
    int track_index;
    int palette_index;
    int mode;
    bool palette_locked;
    bool auto_cycle;
    bool like;
    float auto_clock;
    float volume;
} spectrum_state_t;

extern spectrum_state_t spectrum_state;
extern spectrum_sim_t spectrum_sim;
extern const spectrum_track_t spectrum_tracks[SPECTRUM_TRACK_COUNT];
extern const spectrum_palette_t spectrum_palettes[SPECTRUM_PALETTE_COUNT];

const lv_font_t * spectrum_font(spectrum_font_id_t id);
const lv_image_dsc_t * spectrum_icon(spectrum_icon_id_t id);
const lv_image_dsc_t * spectrum_cover(int track, int palette);
const lv_image_dsc_t * spectrum_cover_spin(int track, int palette);
const lv_image_dsc_t * spectrum_cover_spin96(int track, int palette);
const lv_image_dsc_t * spectrum_cover_spin88(int track, int palette);
const lv_image_dsc_t * spectrum_cover_spin78(int track, int palette);
const lv_image_dsc_t * spectrum_cover_base88(int track, int palette);
const lv_image_dsc_t * spectrum_cover_base78(int track, int palette);
const lv_image_dsc_t * spectrum_glow_asset(void);

lv_obj_t * spectrum_box(lv_obj_t * parent, int x, int y, int w, int h);
lv_obj_t * spectrum_card(lv_obj_t * parent, int x, int y, int w, int h,
                         int radius, uint32_t bg, lv_opa_t bg_opa);
lv_obj_t * spectrum_label(lv_obj_t * parent, const char * text,
                          spectrum_font_id_t font, uint32_t color, int x, int y,
                          int w, int h);
lv_obj_t * spectrum_label_align(lv_obj_t * parent, const char * text,
                                spectrum_font_id_t font, uint32_t color, int x,
                                int y, int w, int h, lv_text_align_t align);
lv_obj_t * spectrum_icon_obj(lv_obj_t * parent, spectrum_icon_id_t icon, int x,
                             int y, int size, uint32_t color);
void spectrum_set_icon(lv_obj_t * image, spectrum_icon_id_t icon, int size,
                       uint32_t color);
void spectrum_clickable(lv_obj_t * obj, const char * name);
void spectrum_divider(lv_obj_t * parent, int x, int y, int w);

const spectrum_track_t * spectrum_track(void);
const spectrum_palette_t * spectrum_palette(void);
float spectrum_db(void);
uint32_t spectrum_mix(uint32_t first, uint32_t second, float t);
void spectrum_format_time(char * buffer, size_t size, float seconds);
bool spectrum_sim_update(double dt);
void spectrum_sim_reset(void);
void spectrum_track_select(int index);
void spectrum_track_next(void);
void spectrum_track_prev(void);
void spectrum_toggle_play(void);
void spectrum_seek(float ratio);
void spectrum_cycle_palette(void);
void spectrum_set_mode(int mode);
void spectrum_toggle_auto(void);
void spectrum_toggle_like(void);
void spectrum_set_volume(float ratio);

void spectrum_create(void);
void spectrum_page_refresh_track(void);
void spectrum_page_refresh_theme(void);
void spectrum_page_refresh_mode(void);
void spectrum_page_refresh_play(void);
void spectrum_page_refresh_meters(void);

void spectrum_viz_create(lv_obj_t * parent);
void spectrum_viz_update(double dt);
void spectrum_viz_reset(void);

#endif

#endif
