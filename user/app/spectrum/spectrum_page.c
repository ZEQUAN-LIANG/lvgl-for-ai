/**
 * @file spectrum_page.c
 * ORBITAL chrome: top status bar, queue/telemetry panels, transport and the
 * timer that feeds the synthetic audio model into the canvas HUD.
 */

#include "spectrum.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#define SP_TEXT 0xE8F6FF
#define SP_DIM 0x7E91B8
#define SP_PANEL_BG 0x060E1C
#define SP_BUTTON_BG 0x060A08

#define SEEK_X 226
#define SEEK_W 348
#define SEEK_Y 518
#define VOL_X 552
#define VOL_W 64
#define VOL_Y 558

static const char * const kFreqLabels[9] = {
    "63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"
};
static const char * const kModeNames[SPECTRUM_MODE_COUNT] = {
    "ORBIT", "DUAL", "RADIAL", "SPIRAL", "SONAR", "STARS"
};
static const char * const kModeTags[SPECTRUM_MODE_COUNT] = {
    "MODE // ORBIT RING",
    "MODE // DUAL COUNTER-RING",
    "MODE // RADIAL ARRAY",
    "MODE // SPIRAL SCAN",
    "MODE // SONAR SWEEP",
    "MODE // WARP FIELD"
};
static const spectrum_icon_id_t kModeIcons[SPECTRUM_MODE_COUNT] = {
    SPECTRUM_ICON_ORBIT,
    SPECTRUM_ICON_DUAL,
    SPECTRUM_ICON_RADIAL,
    SPECTRUM_ICON_SPIRAL,
    SPECTRUM_ICON_SONAR,
    SPECTRUM_ICON_STARS
};

static lv_obj_t * left_panel;
static lv_obj_t * right_panel;
static lv_obj_t * left_accent[4];
static lv_obj_t * right_accent[4];
static lv_obj_t * left_count;
static lv_obj_t * right_count;
static lv_obj_t * status_dot;
static lv_obj_t * brand_icon;
static lv_obj_t * title_label;
static lv_obj_t * artist_label;
static lv_obj_t * bpm_top_label;
static lv_obj_t * bpm_big_label;
static lv_obj_t * sys_label;
static lv_obj_t * key_label;
static lv_obj_t * key_value;
static lv_obj_t * level_label;
static lv_obj_t * level_value;
static lv_obj_t * peak_value;
static lv_obj_t * rms_value;
static lv_obj_t * sync_value;
static lv_obj_t * queue_rows[SPECTRUM_TRACK_COUNT];
static lv_obj_t * queue_titles[SPECTRUM_TRACK_COUNT];
static lv_obj_t * queue_artists[SPECTRUM_TRACK_COUNT];
static lv_obj_t * meter_fill[3];
static lv_obj_t * meter_value[3];
static lv_obj_t * loud_segments[SPECTRUM_LOUD_SEGMENTS];
static lv_obj_t * mini_bars[SPECTRUM_MINI_BARS];
static lv_obj_t * mode_buttons[SPECTRUM_MODE_COUNT];
static lv_obj_t * mode_icons[SPECTRUM_MODE_COUNT];
static lv_obj_t * mode_labels[SPECTRUM_MODE_COUNT];
static lv_obj_t * mode_tag;
static lv_obj_t * sweep_tag;
static lv_obj_t * time_now;
static lv_obj_t * time_total;
static lv_obj_t * seek_fill;
static lv_obj_t * seek_knob;
static lv_obj_t * play_button;
static lv_obj_t * play_icon;
static lv_obj_t * palette_icon;
static lv_obj_t * auto_button;
static lv_obj_t * auto_icon;
static lv_obj_t * auto_label;
static lv_obj_t * like_icon;
static lv_obj_t * vol_fill;
static lv_obj_t * vol_knob;

static uint32_t last_tick;
static float ui_clock;

/* ------------------------------------------------------------- helpers */

static lv_obj_t * make_panel(lv_obj_t * parent, int x, int y, int w, int h)
{
    lv_obj_t * panel = spectrum_card(parent, x, y, w, h, 0, SP_PANEL_BG, 198);
    lv_obj_set_style_bg_grad_color(panel, lv_color_hex(0x03070F), 0);
    lv_obj_set_style_bg_grad_dir(panel, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_border_width(panel, 1, 0);
    lv_obj_set_style_border_color(panel, lv_color_hex(SP_DIM), 0);
    lv_obj_set_style_border_opa(panel, 38, 0);
    lv_obj_set_style_pad_all(panel, 0, 0);
    return panel;
}

static lv_obj_t * make_button(lv_obj_t * parent, int x, int y, int w, int h,
                              int radius, const char * name)
{
    lv_obj_t * button = spectrum_card(parent, x, y, w, h, radius, SP_BUTTON_BG, 210);
    lv_obj_set_style_border_width(button, 1, 0);
    lv_obj_set_style_border_color(button, lv_color_hex(SP_DIM), 0);
    lv_obj_set_style_border_opa(button, 34, 0);
    spectrum_clickable(button, name);
    return button;
}

static void refresh_queue_active(void)
{
    const spectrum_palette_t * pal = spectrum_palette();
    for(int i = 0; i < SPECTRUM_TRACK_COUNT; i++) {
        bool active = (i == spectrum_state.track_index);
        lv_obj_t * row = queue_rows[i];
        lv_obj_set_style_bg_color(row, lv_color_hex(pal->a), 0);
        lv_obj_set_style_bg_opa(row, active ? 22 : 0, 0);
        lv_obj_set_style_border_color(row, lv_color_hex(pal->a), 0);
        lv_obj_set_style_border_opa(row, active ? 120 : 0, 0);
        lv_obj_set_style_border_width(row, 1, 0);
        lv_obj_set_style_text_color(queue_titles[i], lv_color_hex(0xDCDCDC), 0);
    }
}

static void refresh_progress(void)
{
    char buffer[16];
    spectrum_format_time(buffer, sizeof(buffer), spectrum_sim.playhead);
    lv_label_set_text(time_now, buffer);
    spectrum_format_time(buffer, sizeof(buffer), spectrum_sim.duration);
    lv_label_set_text(time_total, buffer);

    float ratio = spectrum_sim.duration > 0.0f ?
                  spectrum_sim.playhead / spectrum_sim.duration : 0.0f;
    if(ratio < 0.0f) ratio = 0.0f;
    if(ratio > 1.0f) ratio = 1.0f;
    int width = (int)(ratio * (float)SEEK_W);
    lv_obj_set_width(seek_fill, width);
    lv_obj_set_x(seek_knob, SEEK_X + width - 5);
}

static void refresh_volume(void)
{
    int width = (int)(spectrum_state.volume * (float)VOL_W);
    lv_obj_set_width(vol_fill, width);
    lv_obj_set_x(vol_knob, VOL_X + width - 4);
}

static void refresh_auto_button(void)
{
    const spectrum_palette_t * pal = spectrum_palette();
    bool on = spectrum_state.auto_cycle;
    lv_obj_set_style_border_color(auto_button, lv_color_hex(on ? pal->a : SP_DIM), 0);
    lv_obj_set_style_border_opa(auto_button, on ? 110 : 34, 0);
    lv_obj_set_style_bg_color(auto_button, lv_color_hex(pal->a), 0);
    lv_obj_set_style_bg_opa(auto_button, on ? 20 : 0, 0);
    lv_obj_set_style_image_recolor(auto_icon, lv_color_hex(on ? pal->a : SP_DIM), 0);
    lv_obj_set_style_text_color(auto_label, lv_color_hex(on ? pal->a : SP_DIM), 0);
}

static void refresh_like_button(void)
{
    const spectrum_palette_t * pal = spectrum_palette();
    spectrum_set_icon(like_icon,
                      spectrum_state.like ? SPECTRUM_ICON_HEART_FILLED : SPECTRUM_ICON_HEART,
                      15, spectrum_state.like ? pal->c : SP_DIM);
}

/* -------------------------------------------------------------- events */

static void mode_event_cb(lv_event_t * event)
{
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    spectrum_set_mode(index);
    spectrum_state.auto_clock = 0.0f;
    spectrum_page_refresh_mode();
}

static void queue_event_cb(lv_event_t * event)
{
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    spectrum_track_select(index);
    spectrum_page_refresh_track();
    spectrum_page_refresh_meters();
}

static void play_event_cb(lv_event_t * event)
{
    (void)event;
    spectrum_toggle_play();
    spectrum_page_refresh_play();
}

static void prev_event_cb(lv_event_t * event)
{
    (void)event;
    spectrum_track_prev();
    spectrum_page_refresh_track();
    spectrum_page_refresh_meters();
}

static void next_event_cb(lv_event_t * event)
{
    (void)event;
    spectrum_track_next();
    spectrum_page_refresh_track();
    spectrum_page_refresh_meters();
}

static void palette_event_cb(lv_event_t * event)
{
    (void)event;
    spectrum_cycle_palette();
    spectrum_page_refresh_theme();
    spectrum_page_refresh_mode();
    spectrum_page_refresh_meters();
}

static void auto_event_cb(lv_event_t * event)
{
    (void)event;
    spectrum_toggle_auto();
    refresh_auto_button();
}

static void like_event_cb(lv_event_t * event)
{
    (void)event;
    spectrum_toggle_like();
    refresh_like_button();
}

static float pointer_ratio(lv_event_t * event)
{
    lv_obj_t * target = lv_event_get_target_obj(event);
    lv_indev_t * indev = lv_indev_active();
    if(target == NULL || indev == NULL) return 0.0f;
    lv_point_t point;
    lv_indev_get_point(indev, &point);
    lv_area_t coords;
    lv_obj_get_coords(target, &coords);
    int width = lv_area_get_width(&coords);
    if(width <= 0) return 0.0f;
    float ratio = (float)(point.x - coords.x1) / (float)width;
    return ratio < 0.0f ? 0.0f : ratio > 1.0f ? 1.0f : ratio;
}

static void seek_event_cb(lv_event_t * event)
{
    lv_event_code_t code = lv_event_get_code(event);
    if(code != LV_EVENT_PRESSED && code != LV_EVENT_PRESSING) return;
    spectrum_seek(pointer_ratio(event));
    refresh_progress();
}

static void volume_event_cb(lv_event_t * event)
{
    lv_event_code_t code = lv_event_get_code(event);
    if(code != LV_EVENT_PRESSED && code != LV_EVENT_PRESSING) return;
    spectrum_set_volume(pointer_ratio(event));
    refresh_volume();
}

/* ------------------------------------------------------------- refresh */

void spectrum_page_refresh_track(void)
{
    const spectrum_track_t * track = spectrum_track();
    char buffer[24];

    lv_label_set_text(title_label, track->title);
    lv_label_set_text(artist_label, track->artist);
    snprintf(buffer, sizeof(buffer), "%d BPM", track->bpm);
    lv_label_set_text(bpm_top_label, buffer);
    snprintf(buffer, sizeof(buffer), "%d", track->bpm);
    lv_label_set_text(bpm_big_label, buffer);
    lv_label_set_text(key_value, track->key);
    spectrum_format_time(buffer, sizeof(buffer), (float)track->duration);
    lv_label_set_text(time_total, buffer);

    refresh_queue_active();
    spectrum_page_refresh_theme();
    spectrum_page_refresh_play();
    spectrum_viz_reset();
}

void spectrum_page_refresh_mode(void)
{
    const spectrum_palette_t * pal = spectrum_palette();
    int mode = spectrum_state.mode;
    lv_label_set_text(mode_tag, kModeTags[mode]);
    lv_label_set_text(sweep_tag, mode == SPECTRUM_MODE_SONAR ? "SWEEP 12.4 Hz" :
                                 mode == SPECTRUM_MODE_STARS ? "WARP 0.9" :
                                 mode == SPECTRUM_MODE_SPIRAL ? "NODES 240" :
                                 mode == SPECTRUM_MODE_RADIAL ? "BANDS 72" :
                                 mode == SPECTRUM_MODE_DUAL ? "CCW / CW" : "ORBIT 0.84");

    for(int i = 0; i < SPECTRUM_MODE_COUNT; i++) {
        bool active = (i == mode);
        lv_obj_set_style_border_color(mode_buttons[i], lv_color_hex(active ? pal->a : 0xFFFFFF), 0);
        lv_obj_set_style_border_opa(mode_buttons[i], active ? 140 : 18, 0);
        lv_obj_set_style_bg_color(mode_buttons[i], lv_color_hex(active ? pal->a : 0xFFFFFF), 0);
        lv_obj_set_style_bg_opa(mode_buttons[i], active ? 26 : 6, 0);
        lv_obj_set_style_image_recolor(mode_icons[i], lv_color_hex(active ? 0xFFFFFF : 0x5C5C5C), 0);
        lv_obj_set_style_text_color(mode_labels[i], lv_color_hex(active ? 0xFFFFFF : 0x5C5C5C), 0);
        lv_obj_set_style_shadow_width(mode_buttons[i], active ? 12 : 0, 0);
        lv_obj_set_style_shadow_color(mode_buttons[i], lv_color_hex(pal->a), 0);
        lv_obj_set_style_shadow_opa(mode_buttons[i], active ? 46 : 0, 0);
    }
}

void spectrum_page_refresh_play(void)
{
    const spectrum_palette_t * pal = spectrum_palette();
    spectrum_set_icon(play_icon,
                      spectrum_sim.playing ? SPECTRUM_ICON_PAUSE : SPECTRUM_ICON_PLAY,
                      18, pal->a);
    lv_obj_set_style_border_color(play_button, lv_color_hex(pal->a), 0);
    lv_obj_set_style_border_opa(play_button, 140, 0);
}

void spectrum_page_refresh_theme(void)
{
    const spectrum_palette_t * pal = spectrum_palette();
    lv_color_t accent = lv_color_hex(pal->a);
    lv_color_t accent_b = lv_color_hex(pal->b);

    lv_obj_set_style_bg_color(lv_screen_active(), lv_color_hex(pal->bg1), 0);
    lv_obj_set_style_bg_grad_color(lv_screen_active(), lv_color_hex(pal->bg0), 0);
    lv_obj_set_style_bg_grad_dir(lv_screen_active(), LV_GRAD_DIR_VER, 0);

    lv_obj_t * panels[2] = {left_panel, right_panel};
    for(int i = 0; i < 2; i++) {
        lv_obj_set_style_border_color(panels[i], accent, 0);
        lv_obj_set_style_border_opa(panels[i], 42, 0);
        lv_obj_set_style_border_width(panels[i], 1, 0);
    }
    for(int i = 0; i < 4; i++) {
        lv_obj_set_style_bg_color(left_accent[i], accent, 0);
        lv_obj_set_style_bg_color(right_accent[i], accent, 0);
    }
    lv_obj_set_style_text_color(left_count, accent, 0);
    lv_obj_set_style_text_color(right_count, accent, 0);
    lv_obj_set_style_text_color(bpm_top_label, accent, 0);
    lv_obj_set_style_text_color(bpm_big_label, accent, 0);
    lv_obj_set_style_text_color(level_value, accent, 0);
    lv_obj_set_style_text_color(mode_tag, accent, 0);
    lv_obj_set_style_text_color(sys_label, accent, 0);
    lv_obj_set_style_bg_color(status_dot, accent, 0);
    lv_obj_set_style_shadow_color(status_dot, accent, 0);
    lv_obj_set_style_image_recolor(brand_icon, accent, 0);
    lv_obj_set_style_image_recolor(palette_icon, accent, 0);
    lv_obj_set_style_bg_color(seek_fill, accent, 0);
    lv_obj_set_style_bg_color(vol_fill, accent, 0);
    for(int i = 0; i < 3; i++) {
        lv_obj_set_style_bg_color(meter_fill[i], accent_b, 0);
        lv_obj_set_style_bg_grad_color(meter_fill[i], accent, 0);
        lv_obj_set_style_shadow_width(meter_fill[i], 7, 0);
        lv_obj_set_style_shadow_color(meter_fill[i], accent, 0);
        lv_obj_set_style_shadow_opa(meter_fill[i], 128, 0);
    }

    for(int i = 0; i < SPECTRUM_MINI_BARS; i++) {
        lv_obj_set_style_bg_color(mini_bars[i], accent, 0);
        lv_obj_set_style_bg_grad_color(mini_bars[i], accent_b, 0);
        lv_obj_set_style_shadow_width(mini_bars[i], 5, 0);
        lv_obj_set_style_shadow_color(mini_bars[i], accent, 0);
        lv_obj_set_style_shadow_opa(mini_bars[i], 64, 0);
    }

    lv_obj_set_style_shadow_width(seek_fill, 10, 0);
    lv_obj_set_style_shadow_color(seek_fill, accent, 0);
    lv_obj_set_style_shadow_opa(seek_fill, 128, 0);
    lv_obj_set_style_shadow_width(seek_knob, 12, 0);
    lv_obj_set_style_shadow_color(seek_knob, accent, 0);
    lv_obj_set_style_shadow_opa(seek_knob, 255, 0);
    lv_obj_set_style_shadow_width(vol_fill, 9, 0);
    lv_obj_set_style_shadow_color(vol_fill, accent, 0);
    lv_obj_set_style_shadow_opa(vol_fill, 102, 0);
    lv_obj_set_style_shadow_width(vol_knob, 9, 0);
    lv_obj_set_style_shadow_color(vol_knob, accent, 0);
    lv_obj_set_style_shadow_opa(vol_knob, 255, 0);
    lv_obj_set_style_shadow_width(play_button, 24, 0);
    lv_obj_set_style_shadow_color(play_button, accent, 0);
    lv_obj_set_style_shadow_opa(play_button, 64, 0);

    refresh_queue_active();
    refresh_auto_button();
    refresh_like_button();
    spectrum_page_refresh_mode();
    spectrum_page_refresh_play();
}

void spectrum_page_refresh_meters(void)
{
    const spectrum_palette_t * pal = spectrum_palette();
    char buffer[24];

    float db = spectrum_db();
    snprintf(buffer, sizeof(buffer), "%.1f", db);
    lv_label_set_text(level_value, buffer);
    snprintf(buffer, sizeof(buffer), "%.1f dB", db + 8.4f);
    lv_label_set_text(peak_value, buffer);
    snprintf(buffer, sizeof(buffer), "%.1f dB", db - 5.7f);
    lv_label_set_text(rms_value, buffer);
    snprintf(buffer, sizeof(buffer), "%d%%", (int)(92.0f + spectrum_sim.energy * 7.0f));
    lv_label_set_text(sync_value, buffer);

    int low = (int)(spectrum_sim.low * 100.0 + 0.5);
    int mid = (int)(spectrum_sim.mid * 100.0 + 0.5);
    int high = (int)(spectrum_sim.high * 100.0 + 0.5);
    if(low < 0) low = 0;
    if(low > 100) low = 100;
    if(mid < 0) mid = 0;
    if(mid > 100) mid = 100;
    if(high < 0) high = 0;
    if(high > 100) high = 100;
    lv_obj_set_width(meter_fill[0], (int)(low * 0.77f));
    lv_obj_set_width(meter_fill[1], (int)(mid * 0.77f));
    lv_obj_set_width(meter_fill[2], (int)(high * 0.77f));
    snprintf(buffer, sizeof(buffer), "%02d", low);
    lv_label_set_text(meter_value[0], buffer);
    snprintf(buffer, sizeof(buffer), "%02d", mid);
    lv_label_set_text(meter_value[1], buffer);
    snprintf(buffer, sizeof(buffer), "%02d", high);
    lv_label_set_text(meter_value[2], buffer);

    float level = (spectrum_sim.energy - 0.08f) / 0.62f;
    if(level < 0.0f) level = 0.0f;
    if(level > 1.0f) level = 1.0f;
    int lit = (int)(level * (float)SPECTRUM_LOUD_SEGMENTS + 0.5f);
    for(int i = 0; i < SPECTRUM_LOUD_SEGMENTS; i++) {
        bool on = i < lit;
        uint32_t top = i >= 12 ? 0xFF3B5C : (i >= 9 ? pal->c : pal->a);
        uint32_t bottom = i >= 12 ? 0xFF3B5C : (i >= 9 ? pal->a : pal->b);
        lv_obj_set_style_bg_color(loud_segments[i], lv_color_hex(top), 0);
        lv_obj_set_style_bg_grad_color(loud_segments[i], lv_color_hex(bottom), 0);
        lv_obj_set_style_bg_opa(loud_segments[i], on ? LV_OPA_COVER : 19, 0);
        lv_obj_set_style_shadow_width(loud_segments[i], i <= 8 && on ? 7 : 0, 0);
        lv_obj_set_style_shadow_color(loud_segments[i], lv_color_hex(pal->a), 0);
        lv_obj_set_style_shadow_opa(loud_segments[i], on ? 102 : 0, 0);
    }

    for(int i = 0; i < SPECTRUM_MINI_BARS; i++) {
        float f = (float)i / (float)(SPECTRUM_MINI_BARS - 1);
        float pos = f * (float)(SPECTRUM_BAND_COUNT - 1);
        int bi = (int)pos;
        int bj = bi + 1 < SPECTRUM_BAND_COUNT ? bi + 1 : SPECTRUM_BAND_COUNT - 1;
        float frac = pos - (float)bi;
        float value = spectrum_sim.bands[bi] +
                      (spectrum_sim.bands[bj] - spectrum_sim.bands[bi]) * frac;
        if(value < 0.0f) value = 0.0f;
        if(value > 1.0f) value = 1.0f;
        int height = 3 + (int)(powf(value, 0.7f) * 27.0f + 0.5f);
        lv_obj_set_height(mini_bars[i], height);
        lv_obj_set_y(mini_bars[i], 236 - height);
    }

    int opacity = 150 + (int)(95.0f * (0.5f + 0.5f * sinf(spectrum_sim.time * 2.2f)));
    lv_obj_set_style_opa(status_dot, (lv_opa_t)opacity, 0);

    int mode = spectrum_state.mode;
    if(mode == SPECTRUM_MODE_SONAR) {
        snprintf(buffer, sizeof(buffer), "SWEEP %.1f Hz", 8.0f + spectrum_sim.energy * 22.0f);
        lv_label_set_text(sweep_tag, buffer);
    }
    else if(mode == SPECTRUM_MODE_STARS) {
        snprintf(buffer, sizeof(buffer), "WARP %.1f", 0.4f + spectrum_sim.energy * 1.8f);
        lv_label_set_text(sweep_tag, buffer);
    }
    else if(mode == SPECTRUM_MODE_ORBIT) {
        snprintf(buffer, sizeof(buffer), "ORBIT %.2f", 0.6f + spectrum_sim.energy);
        lv_label_set_text(sweep_tag, buffer);
    }
}

/* --------------------------------------------------------------- timer */

static void tick_cb(lv_timer_t * timer)
{
    (void)timer;
    uint32_t now = lv_tick_get();
    uint32_t elapsed = lv_tick_elaps(last_tick);
    last_tick = now;
    if(elapsed > 120) elapsed = 120;
    double dt = (double)elapsed / 1000.0;

    bool track_changed = spectrum_sim_update(dt);
    if(track_changed) {
        spectrum_page_refresh_track();
        spectrum_page_refresh_meters();
    }

    if(spectrum_state.auto_cycle) {
        spectrum_state.auto_clock += (float)dt;
        if(spectrum_state.auto_clock >= 8.0f) {
            spectrum_state.auto_clock = 0.0f;
            spectrum_set_mode(spectrum_state.mode + 1);
            spectrum_page_refresh_mode();
        }
    }

    spectrum_viz_update(dt);

    ui_clock += (float)dt;
    if(ui_clock >= 0.06f) {
        ui_clock = 0.0f;
        refresh_progress();
        spectrum_page_refresh_meters();
    }
}

/* ---------------------------------------------------------------- page */

static void build_topbar(lv_obj_t * screen)
{
    const spectrum_palette_t * pal = spectrum_palette();
    brand_icon = spectrum_icon_obj(screen, SPECTRUM_ICON_LOGO, 22, 21, 22, pal->a);

    lv_obj_t * wordmark = spectrum_label(screen, "ORBITAL", SPECTRUM_FONT_SANS_14,
                                         0xFFFFFF, 50, 18, 200, 17);
    lv_obj_set_style_text_letter_space(wordmark, 4, 0);
    lv_obj_t * subtitle = spectrum_label(screen, "SPECTRUM ARRAY / MK-IV",
                                         SPECTRUM_FONT_MONO_7, SP_DIM,
                                         50, 39, 220, 10);
    lv_obj_set_style_text_letter_space(subtitle, 2, 0);

    title_label = spectrum_label_align(screen, "NEON SKYLINE",
                                       SPECTRUM_FONT_SANS_14, 0xFFFFFF,
                                       250, 21, 300, 17, LV_TEXT_ALIGN_CENTER);
    lv_obj_set_style_text_letter_space(title_label, 2, 0);
    artist_label = spectrum_label_align(screen, "AURORA WAVE",
                                        SPECTRUM_FONT_MONO_8, SP_DIM,
                                        250, 42, 300, 10, LV_TEXT_ALIGN_CENTER);
    lv_obj_set_style_text_letter_space(artist_label, 2, 0);

    status_dot = spectrum_card(screen, 618, 20, 5, 5, LV_RADIUS_CIRCLE, pal->a, 255);
    lv_obj_set_style_shadow_width(status_dot, 6, 0);
    lv_obj_set_style_shadow_color(status_dot, lv_color_hex(pal->a), 0);
    lv_obj_set_style_shadow_opa(status_dot, 100, 0);

    sys_label = spectrum_label(screen, "SYS ONLINE", SPECTRUM_FONT_MONO_8,
                               pal->a, 629, 18, 76, 10);
    spectrum_label(screen, "48 kHz", SPECTRUM_FONT_MONO_8, SP_DIM,
                   697, 18, 42, 10);
    bpm_top_label = spectrum_label(screen, "141 BPM", SPECTRUM_FONT_MONO_8,
                                   pal->a, 745, 18, 42, 10);
}

static void build_left_panel(lv_obj_t * screen)
{
    left_panel = make_panel(screen, SPECTRUM_LEFT_X, SPECTRUM_PANEL_Y,
                            SPECTRUM_PANEL_W, SPECTRUM_PANEL_H);

    spectrum_label(left_panel, "PLAY QUEUE", SPECTRUM_FONT_MONO_8, SP_DIM,
                   10, 10, 100, 10);
    left_count = spectrum_label_align(left_panel, "03", SPECTRUM_FONT_MONO_8,
                                      spectrum_palette()->a, 114, 10, 26, 10,
                                      LV_TEXT_ALIGN_RIGHT);
    spectrum_divider(left_panel, 10, 28, 130);

    left_accent[0] = spectrum_box(left_panel, 0, 0, 12, 2);
    left_accent[1] = spectrum_box(left_panel, 0, 0, 2, 12);
    left_accent[2] = spectrum_box(left_panel, 140, 402, 12, 2);
    left_accent[3] = spectrum_box(left_panel, 150, 390, 2, 12);
    for(int i = 0; i < 4; i++) {
        lv_obj_set_style_bg_color(left_accent[i],
                                  lv_color_hex(spectrum_palette()->a), 0);
    }

    for(int i = 0; i < SPECTRUM_TRACK_COUNT; i++) {
        lv_obj_t * row = spectrum_card(left_panel, 10, 35 + i * 36, 130, 32,
                                       2, spectrum_palette()->a, 0);
        lv_obj_set_style_border_width(row, 1, 0);
        lv_obj_set_style_border_color(row, lv_color_hex(spectrum_palette()->a), 0);
        lv_obj_set_style_border_opa(row, 0, 0);
        spectrum_clickable(row, i == 0 ? "spectrum_queue_0" :
                                i == 1 ? "spectrum_queue_1" : "spectrum_queue_2");
        lv_obj_add_event_cb(row, queue_event_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        queue_rows[i] = row;

        char number[4];
        snprintf(number, sizeof(number), "%02d", i + 1);
        lv_obj_t * index = spectrum_label(row, number, SPECTRUM_FONT_MONO_8,
                                          0x565656, 6, 11, 18, 9);
        lv_obj_set_style_text_letter_space(index, 0, 0);
        queue_titles[i] = spectrum_label(row, spectrum_tracks[i].title,
                                         SPECTRUM_FONT_MONO_9B, 0xDCDCDC,
                                         27, 7, 100, 11);
        queue_artists[i] = spectrum_label(row, spectrum_tracks[i].artist,
                                          SPECTRUM_FONT_MONO_7, 0x5C5C5C,
                                          27, 17, 100, 8);
    }

    spectrum_label(left_panel, "SIGNAL", SPECTRUM_FONT_MONO_7, 0x505050,
                   10, 276, 80, 9);
    spectrum_label(left_panel, "PEAK", SPECTRUM_FONT_MONO_7, 0x505050,
                   10, 289, 50, 9);
    spectrum_label(left_panel, "RMS", SPECTRUM_FONT_MONO_7, 0x505050,
                   10, 302, 50, 9);
    spectrum_label(left_panel, "SYNC", SPECTRUM_FONT_MONO_7, 0x505050,
                   10, 315, 50, 9);
    peak_value = spectrum_label_align(left_panel, "-3.2 dB", SPECTRUM_FONT_MONO_7,
                                      0xA8A8A8, 70, 289, 70, 9, LV_TEXT_ALIGN_RIGHT);
    rms_value = spectrum_label_align(left_panel, "-14.8 dB", SPECTRUM_FONT_MONO_7,
                                     0xA8A8A8, 70, 302, 70, 9, LV_TEXT_ALIGN_RIGHT);
    sync_value = spectrum_label_align(left_panel, "96%", SPECTRUM_FONT_MONO_7,
                                      0xA8A8A8, 70, 315, 70, 9, LV_TEXT_ALIGN_RIGHT);

    spectrum_divider(left_panel, 10, 331, 130);
    spectrum_label(left_panel, "SOURCE", SPECTRUM_FONT_MONO_7, 0x505050, 10, 345, 58, 9);
    spectrum_label_align(left_panel, "SYNTHETIC", SPECTRUM_FONT_MONO_7, 0xA8A8A8,
                         68, 345, 72, 9, LV_TEXT_ALIGN_RIGHT);
    spectrum_label(left_panel, "FFT SIZE", SPECTRUM_FONT_MONO_7, 0x505050, 10, 358, 58, 9);
    spectrum_label_align(left_panel, "2048", SPECTRUM_FONT_MONO_7, 0xA8A8A8,
                         68, 358, 72, 9, LV_TEXT_ALIGN_RIGHT);
    spectrum_label(left_panel, "WINDOW", SPECTRUM_FONT_MONO_7, 0x505050, 10, 371, 58, 9);
    spectrum_label_align(left_panel, "HANN", SPECTRUM_FONT_MONO_7, 0xA8A8A8,
                         68, 371, 72, 9, LV_TEXT_ALIGN_RIGHT);
    spectrum_label(left_panel, "OVERLAP", SPECTRUM_FONT_MONO_7, 0x505050, 10, 384, 58, 9);
    spectrum_label_align(left_panel, "75%", SPECTRUM_FONT_MONO_7, 0xA8A8A8,
                         68, 384, 72, 9, LV_TEXT_ALIGN_RIGHT);
}

static void build_right_panel(lv_obj_t * screen)
{
    right_panel = make_panel(screen, SPECTRUM_RIGHT_X, SPECTRUM_PANEL_Y,
                             SPECTRUM_PANEL_W, SPECTRUM_PANEL_H);

    spectrum_label(right_panel, "TELEMETRY", SPECTRUM_FONT_MONO_8, SP_DIM,
                   10, 10, 100, 10);
    right_count = spectrum_label_align(right_panel, "01", SPECTRUM_FONT_MONO_8,
                                       spectrum_palette()->a, 114, 10, 26, 10,
                                       LV_TEXT_ALIGN_RIGHT);
    spectrum_divider(right_panel, 10, 28, 130);

    right_accent[0] = spectrum_box(right_panel, 0, 0, 12, 2);
    right_accent[1] = spectrum_box(right_panel, 0, 0, 2, 12);
    right_accent[2] = spectrum_box(right_panel, 140, 402, 12, 2);
    right_accent[3] = spectrum_box(right_panel, 150, 390, 2, 12);
    for(int i = 0; i < 4; i++) {
        lv_obj_set_style_bg_color(right_accent[i],
                                  lv_color_hex(spectrum_palette()->a), 0);
    }

    bpm_big_label = spectrum_label(right_panel, "141", SPECTRUM_FONT_MONO_32,
                                   spectrum_palette()->a, 10, 35, 90, 38);
    spectrum_label(right_panel, "BPM", SPECTRUM_FONT_MONO_7, SP_DIM,
                   69, 55, 34, 9);

    key_label = spectrum_label(right_panel, "KEY", SPECTRUM_FONT_MONO_7, SP_DIM,
                               10, 72, 40, 9);
    (void)key_label;
    key_value = spectrum_label_align(right_panel, "8A", SPECTRUM_FONT_MONO_7,
                                     0xC8C8C8, 64, 72, 76, 9, LV_TEXT_ALIGN_RIGHT);
    level_label = spectrum_label(right_panel, "LEVEL", SPECTRUM_FONT_MONO_7, SP_DIM,
                                 10, 86, 48, 9);
    (void)level_label;
    level_value = spectrum_label_align(right_panel, "-12.4", SPECTRUM_FONT_MONO_7,
                                       spectrum_palette()->a, 64, 86, 76, 9,
                                       LV_TEXT_ALIGN_RIGHT);

    spectrum_divider(right_panel, 10, 106, 130);

    const char * meter_names[3] = {"LOW", "MID", "HIGH"};
    for(int i = 0; i < 3; i++) {
        int y = 120 + i * 13;
        lv_obj_t * name = spectrum_label(right_panel, meter_names[i],
                                         SPECTRUM_FONT_MONO_7, 0x4B4B4B, 10, y, 25, 9);
        lv_obj_set_style_text_letter_space(name, 0, 0);
        lv_obj_t * track = spectrum_box(right_panel, 40, y + 2, 77, 3);
        lv_obj_set_style_bg_color(track, lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_bg_opa(track, 20, 0);
        meter_fill[i] = spectrum_box(right_panel, 40, y + 2, 0, 3);
        lv_obj_set_style_bg_opa(meter_fill[i], LV_OPA_COVER, 0);
        lv_obj_set_style_bg_grad_dir(meter_fill[i], LV_GRAD_DIR_HOR, 0);
        meter_value[i] = spectrum_label_align(right_panel, "00",
                                              SPECTRUM_FONT_MONO_7, 0x8F8F8F,
                                              110, y, 30, 9, LV_TEXT_ALIGN_RIGHT);
        lv_obj_set_style_text_letter_space(meter_value[i], 0, 0);
    }

    spectrum_divider(right_panel, 10, 163, 130);

    spectrum_label(right_panel, "LOUDNESS", SPECTRUM_FONT_MONO_7, 0x505050,
                   10, 172, 80, 9);
    for(int i = 0; i < SPECTRUM_LOUD_SEGMENTS; i++) {
        int x = 10 + (i * 942) / 100;
        loud_segments[i] = spectrum_box(right_panel, x, 186, 7, 7);
        lv_obj_set_style_bg_opa(loud_segments[i], 19, 0);
        lv_obj_set_style_bg_color(loud_segments[i], lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_bg_grad_dir(loud_segments[i], LV_GRAD_DIR_VER, 0);
    }

    spectrum_divider(right_panel, 10, 202, 130);
    for(int i = 0; i < SPECTRUM_MINI_BARS; i++) {
        int x = 10 + (i * 130 + 8) / SPECTRUM_MINI_BARS;
        mini_bars[i] = spectrum_box(right_panel, x, 233, 6, 3);
        lv_obj_set_style_bg_opa(mini_bars[i], LV_OPA_COVER, 0);
        lv_obj_set_style_bg_grad_dir(mini_bars[i], LV_GRAD_DIR_VER, 0);
    }

    spectrum_divider(right_panel, 10, 245, 130);
    for(int i = 0; i < SPECTRUM_MODE_COUNT; i++) {
        int col = i % 2;
        int row = i / 2;
        lv_obj_t * button = make_button(right_panel,
                                        10 + col * 67, 255 + row * 30,
                                        63, 26, 2, "spectrum_mode_0");
        char name[24];
        snprintf(name, sizeof(name), "spectrum_mode_%d", i);
        lv_obj_set_name(button, name);
        lv_obj_add_event_cb(button, mode_event_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        mode_buttons[i] = button;
        mode_icons[i] = spectrum_icon_obj(button, kModeIcons[i], 5, 7, 11, 0x5C5C5C);
        mode_labels[i] = spectrum_label(button, kModeNames[i],
                                        SPECTRUM_FONT_MONO_7, 0x5C5C5C,
                                        20, 8, 38, 11);
        lv_obj_set_style_text_letter_space(mode_labels[i], 0, 0);
    }
}

static void build_center(lv_obj_t * screen)
{
    spectrum_viz_create(screen);

    mode_tag = spectrum_label(screen, "MODE // ORBIT RING",
                              SPECTRUM_FONT_MONO_7, spectrum_palette()->a,
                              193, 81, 200, 9);
    sweep_tag = spectrum_label_align(screen, "ORBIT 0.84",
                                     SPECTRUM_FONT_MONO_7, SP_DIM,
                                     427, 81, 180, 9, LV_TEXT_ALIGN_RIGHT);

    static const int freq_center[9] = {196, 247, 300, 354, 404, 453, 502, 550, 601};
    for(int i = 0; i < 9; i++) {
        lv_obj_t * freq = spectrum_label_align(screen, kFreqLabels[i],
                                               SPECTRUM_FONT_MONO_8, SP_DIM,
                                               freq_center[i] - 10, 490, 20, 10,
                                               LV_TEXT_ALIGN_CENTER);
        lv_obj_set_style_text_letter_space(freq, 0, 0);
    }
}

static void build_transport(lv_obj_t * screen)
{
    time_now = spectrum_label(screen, "0:00", SPECTRUM_FONT_MONO_9, SP_DIM,
                              184, 514, 32, 10);
    time_total = spectrum_label_align(screen, "3:58", SPECTRUM_FONT_MONO_9, SP_DIM,
                                      584, 514, 32, 10, LV_TEXT_ALIGN_RIGHT);

    lv_obj_t * seek_track = spectrum_box(screen, SEEK_X, SEEK_Y, SEEK_W, 2);
    lv_obj_set_style_bg_color(seek_track, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_bg_opa(seek_track, 22, 0);
    seek_fill = spectrum_box(screen, SEEK_X, SEEK_Y - 1, 0, 4);
    lv_obj_set_style_radius(seek_fill, 2, 0);
    lv_obj_set_style_bg_opa(seek_fill, LV_OPA_COVER, 0);
    seek_knob = spectrum_card(screen, SEEK_X - 5, SEEK_Y - 4, 10, 10,
                              LV_RADIUS_CIRCLE, 0xFFFFFF, 217);

    lv_obj_t * seek_hit = spectrum_box(screen, SEEK_X, SEEK_Y - 8, SEEK_W, 18);
    spectrum_clickable(seek_hit, "spectrum_seek");
    lv_obj_add_event_cb(seek_hit, seek_event_cb, LV_EVENT_PRESSED, NULL);
    lv_obj_add_event_cb(seek_hit, seek_event_cb, LV_EVENT_PRESSING, NULL);

    lv_obj_t * palette_button = make_button(screen, 184, 545, 30, 30, 3,
                                            "spectrum_palette");
    lv_obj_add_event_cb(palette_button, palette_event_cb, LV_EVENT_CLICKED, NULL);
    palette_icon = spectrum_icon_obj(palette_button, SPECTRUM_ICON_PALETTE,
                                     8, 8, 14, spectrum_palette()->a);

    auto_button = make_button(screen, 221, 546, 54, 28, 3, "spectrum_auto");
    lv_obj_add_event_cb(auto_button, auto_event_cb, LV_EVENT_CLICKED, NULL);
    auto_icon = spectrum_icon_obj(auto_button, SPECTRUM_ICON_AUTO,
                                  9, 8, 11, SP_DIM);
    auto_label = spectrum_label(auto_button, "AUTO", SPECTRUM_FONT_MONO_7,
                                SP_DIM, 25, 8, 30, 10);

    lv_obj_t * prev_button = make_button(screen, 320, 545, 30, 30, 3,
                                         "spectrum_prev");
    lv_obj_add_event_cb(prev_button, prev_event_cb, LV_EVENT_CLICKED, NULL);
    spectrum_icon_obj(prev_button, SPECTRUM_ICON_PREV, 8, 8, 14, SP_DIM);

    play_button = spectrum_card(screen, 363, 537, 46, 46, LV_RADIUS_CIRCLE,
                                SP_BUTTON_BG, 220);
    lv_obj_set_style_border_width(play_button, 1, 0);
    lv_obj_set_style_border_color(play_button, lv_color_hex(spectrum_palette()->a), 0);
    lv_obj_set_style_border_opa(play_button, 140, 0);
    spectrum_clickable(play_button, "spectrum_play");
    lv_obj_add_event_cb(play_button, play_event_cb, LV_EVENT_CLICKED, NULL);
    play_icon = spectrum_icon_obj(play_button, SPECTRUM_ICON_PAUSE,
                                  14, 14, 18, spectrum_palette()->a);

    lv_obj_t * next_button = make_button(screen, 422, 545, 30, 30, 3,
                                         "spectrum_next");
    lv_obj_add_event_cb(next_button, next_event_cb, LV_EVENT_CLICKED, NULL);
    spectrum_icon_obj(next_button, SPECTRUM_ICON_NEXT, 8, 8, 14, SP_DIM);

    lv_obj_t * like_button = make_button(screen, 496, 545, 30, 30, 3,
                                         "spectrum_like");
    lv_obj_add_event_cb(like_button, like_event_cb, LV_EVENT_CLICKED, NULL);
    like_icon = spectrum_icon_obj(like_button, SPECTRUM_ICON_HEART,
                                  8, 7, 15, SP_DIM);

    spectrum_icon_obj(screen, SPECTRUM_ICON_VOLUME, 533, 552, 13, SP_DIM);
    lv_obj_t * vol_track = spectrum_box(screen, VOL_X, VOL_Y, VOL_W, 2);
    lv_obj_set_style_bg_color(vol_track, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_bg_opa(vol_track, 22, 0);
    vol_fill = spectrum_box(screen, VOL_X, VOL_Y, 0, 4);
    lv_obj_set_style_radius(vol_fill, 2, 0);
    lv_obj_set_style_bg_opa(vol_fill, LV_OPA_COVER, 0);
    vol_knob = spectrum_card(screen, VOL_X - 4, VOL_Y - 3, 9, 9,
                             LV_RADIUS_CIRCLE, 0xFFFFFF, LV_OPA_COVER);

    lv_obj_t * vol_hit = spectrum_box(screen, VOL_X - 6, VOL_Y - 9, VOL_W + 12, 20);
    spectrum_clickable(vol_hit, "spectrum_volume");
    lv_obj_add_event_cb(vol_hit, volume_event_cb, LV_EVENT_PRESSED, NULL);
    lv_obj_add_event_cb(vol_hit, volume_event_cb, LV_EVENT_PRESSING, NULL);
}

void spectrum_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    spectrum_sim.playing = true;
    spectrum_sim.time = 0.0f;
    spectrum_state.track_index = 0;
    spectrum_state.palette_index = spectrum_tracks[0].palette;
    spectrum_state.palette_locked = false;
    spectrum_state.mode = SPECTRUM_MODE_ORBIT;
    spectrum_state.auto_cycle = false;
    spectrum_state.auto_clock = 0.0f;
    spectrum_state.like = false;
    spectrum_state.volume = 0.72f;
    spectrum_sim_reset();

    lv_obj_set_style_radius(screen, 0, 0);
    lv_obj_set_style_border_width(screen, 0, 0);
    lv_obj_set_style_pad_all(screen, 0, 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(screen, lv_color_hex(spectrum_palette()->bg1), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_hex(spectrum_palette()->bg0), 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);
    lv_obj_set_scrollable(screen, false);
    lv_obj_set_scrollbar_mode(screen, LV_SCROLLBAR_MODE_OFF);

    /* The HUD canvas is now full-screen, so it must exist before the panels
     * and bars that sit above it. */
    build_center(screen);
    build_topbar(screen);
    build_left_panel(screen);
    build_right_panel(screen);
    build_transport(screen);

    spectrum_page_refresh_track();
    spectrum_page_refresh_mode();
    spectrum_page_refresh_play();
    spectrum_page_refresh_theme();
    spectrum_page_refresh_meters();
    refresh_progress();
    refresh_volume();

    last_tick = lv_tick_get();
    lv_timer_create(tick_cb, 16, NULL);
}

#endif /* LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6 */
