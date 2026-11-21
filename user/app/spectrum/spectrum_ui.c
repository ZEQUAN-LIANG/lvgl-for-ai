
#include "app.h"
#include "spectrum.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "spectrum_assets.h"

#define SP_PI 3.14159265358979323846

spectrum_state_t spectrum_state;
spectrum_sim_t spectrum_sim;

const spectrum_track_t spectrum_tracks[SPECTRUM_TRACK_COUNT] = {
    {"NEON SKYLINE", "AURORA WAVE", 141, 238, "8A", 11, SPECTRUM_PALETTE_ION},
    {"MIDNIGHT CIRCUIT", "VOLT RUNNER", 128, 252, "6B", 29,
     SPECTRUM_PALETTE_MAGMA},
    {"SOLAR DRIFT", "LUMEN FIELD", 96, 306, "9A", 47, SPECTRUM_PALETTE_VERDANT},
};

const spectrum_palette_t spectrum_palettes[SPECTRUM_PALETTE_COUNT] = {
    {"ION", 0x03060F, 0x0A1430, 0x25E7FF, 0x7C5CFF, 0xFF4FD8, 0xA9F7FF,
     0x7E91B8},
    {"MAGMA", 0x100308, 0x2A0A1C, 0xFF4F8B, 0xFF8A3D, 0xFFD166, 0xFFC2D6,
     0xBD8FA4},
    {"VERDANT", 0x020D0A, 0x07261F, 0x5DFFB0, 0x29D7FF, 0xD4FF4D, 0xC4FFE4,
     0x7FB5A5},
};

const lv_font_t * spectrum_font(spectrum_font_id_t id)
{
    switch(id) {
        case SPECTRUM_FONT_SANS_14:
            return &spectrum_sans_14;
        case SPECTRUM_FONT_MONO_7:
            return &spectrum_mono_7;
        case SPECTRUM_FONT_MONO_8:
            return &spectrum_mono_8;
        case SPECTRUM_FONT_MONO_9:
            return &spectrum_mono_9;
        case SPECTRUM_FONT_MONO_9B:
            return &spectrum_mono_9b;
        case SPECTRUM_FONT_MONO_32:
            return &spectrum_mono_32;
        default:
            return &spectrum_mono_8;
    }
}

const lv_image_dsc_t * spectrum_icon(spectrum_icon_id_t id)
{
    switch(id) {
        case SPECTRUM_ICON_LOGO:
            return &spectrum_icon_logo;
        case SPECTRUM_ICON_PLAY:
            return &spectrum_icon_play;
        case SPECTRUM_ICON_PAUSE:
            return &spectrum_icon_pause;
        case SPECTRUM_ICON_PREV:
            return &spectrum_icon_prev;
        case SPECTRUM_ICON_NEXT:
            return &spectrum_icon_next;
        case SPECTRUM_ICON_HEART:
            return &spectrum_icon_heart;
        case SPECTRUM_ICON_HEART_FILLED:
            return &spectrum_icon_heart_filled;
        case SPECTRUM_ICON_PALETTE:
            return &spectrum_icon_palette;
        case SPECTRUM_ICON_AUTO:
            return &spectrum_icon_auto;
        case SPECTRUM_ICON_VOLUME:
            return &spectrum_icon_volume;
        case SPECTRUM_ICON_ORBIT:
            return &spectrum_icon_orbit;
        case SPECTRUM_ICON_DUAL:
            return &spectrum_icon_dual;
        case SPECTRUM_ICON_RADIAL:
            return &spectrum_icon_radial;
        case SPECTRUM_ICON_SPIRAL:
            return &spectrum_icon_spiral;
        case SPECTRUM_ICON_SONAR:
            return &spectrum_icon_sonar;
        case SPECTRUM_ICON_STARS:
            return &spectrum_icon_stars;
        default:
            return &spectrum_icon_logo;
    }
}

const lv_image_dsc_t * spectrum_cover(int track, int palette)
{
    track = (track + SPECTRUM_TRACK_COUNT) % SPECTRUM_TRACK_COUNT;
    palette = (palette + SPECTRUM_PALETTE_COUNT) % SPECTRUM_PALETTE_COUNT;
    static const lv_image_dsc_t * const
        covers[SPECTRUM_TRACK_COUNT][SPECTRUM_PALETTE_COUNT] = {
            {&spectrum_cover_t0_p0, &spectrum_cover_t0_p1,
             &spectrum_cover_t0_p2},
            {&spectrum_cover_t1_p0, &spectrum_cover_t1_p1,
             &spectrum_cover_t1_p2},
            {&spectrum_cover_t2_p0, &spectrum_cover_t2_p1,
             &spectrum_cover_t2_p2},
    };
    return covers[track][palette];
}

const lv_image_dsc_t * spectrum_cover_spin(int track, int palette)
{
    track = (track + SPECTRUM_TRACK_COUNT) % SPECTRUM_TRACK_COUNT;
    palette = (palette + SPECTRUM_PALETTE_COUNT) % SPECTRUM_PALETTE_COUNT;
    static const lv_image_dsc_t * const
        covers[SPECTRUM_TRACK_COUNT][SPECTRUM_PALETTE_COUNT] = {
            {&spectrum_cover_spin_t0_p0, &spectrum_cover_spin_t0_p1,
             &spectrum_cover_spin_t0_p2},
            {&spectrum_cover_spin_t1_p0, &spectrum_cover_spin_t1_p1,
             &spectrum_cover_spin_t1_p2},
            {&spectrum_cover_spin_t2_p0, &spectrum_cover_spin_t2_p1,
             &spectrum_cover_spin_t2_p2},
    };
    return covers[track][palette];
}

const lv_image_dsc_t * spectrum_cover_spin96(int track, int palette)
{
    track = (track + SPECTRUM_TRACK_COUNT) % SPECTRUM_TRACK_COUNT;
    palette = (palette + SPECTRUM_PALETTE_COUNT) % SPECTRUM_PALETTE_COUNT;
    static const lv_image_dsc_t * const
        covers[SPECTRUM_TRACK_COUNT][SPECTRUM_PALETTE_COUNT] = {
            {&spectrum_cover_spin96_t0_p0, &spectrum_cover_spin96_t0_p1,
             &spectrum_cover_spin96_t0_p2},
            {&spectrum_cover_spin96_t1_p0, &spectrum_cover_spin96_t1_p1,
             &spectrum_cover_spin96_t1_p2},
            {&spectrum_cover_spin96_t2_p0, &spectrum_cover_spin96_t2_p1,
             &spectrum_cover_spin96_t2_p2},
    };
    return covers[track][palette];
}

const lv_image_dsc_t * spectrum_cover_spin88(int track, int palette)
{
    track = (track + SPECTRUM_TRACK_COUNT) % SPECTRUM_TRACK_COUNT;
    palette = (palette + SPECTRUM_PALETTE_COUNT) % SPECTRUM_PALETTE_COUNT;
    static const lv_image_dsc_t * const
        covers[SPECTRUM_TRACK_COUNT][SPECTRUM_PALETTE_COUNT] = {
            {&spectrum_cover_spin88_t0_p0, &spectrum_cover_spin88_t0_p1,
             &spectrum_cover_spin88_t0_p2},
            {&spectrum_cover_spin88_t1_p0, &spectrum_cover_spin88_t1_p1,
             &spectrum_cover_spin88_t1_p2},
            {&spectrum_cover_spin88_t2_p0, &spectrum_cover_spin88_t2_p1,
             &spectrum_cover_spin88_t2_p2},
    };
    return covers[track][palette];
}

const lv_image_dsc_t * spectrum_cover_spin78(int track, int palette)
{
    track = (track + SPECTRUM_TRACK_COUNT) % SPECTRUM_TRACK_COUNT;
    palette = (palette + SPECTRUM_PALETTE_COUNT) % SPECTRUM_PALETTE_COUNT;
    static const lv_image_dsc_t * const
        covers[SPECTRUM_TRACK_COUNT][SPECTRUM_PALETTE_COUNT] = {
            {&spectrum_cover_spin78_t0_p0, &spectrum_cover_spin78_t0_p1,
             &spectrum_cover_spin78_t0_p2},
            {&spectrum_cover_spin78_t1_p0, &spectrum_cover_spin78_t1_p1,
             &spectrum_cover_spin78_t1_p2},
            {&spectrum_cover_spin78_t2_p0, &spectrum_cover_spin78_t2_p1,
             &spectrum_cover_spin78_t2_p2},
    };
    return covers[track][palette];
}

const lv_image_dsc_t * spectrum_cover_base88(int track, int palette)
{
    track = (track + SPECTRUM_TRACK_COUNT) % SPECTRUM_TRACK_COUNT;
    palette = (palette + SPECTRUM_PALETTE_COUNT) % SPECTRUM_PALETTE_COUNT;
    static const lv_image_dsc_t * const
        covers[SPECTRUM_TRACK_COUNT][SPECTRUM_PALETTE_COUNT] = {
            {&spectrum_cover_base88_t0_p0, &spectrum_cover_base88_t0_p1,
             &spectrum_cover_base88_t0_p2},
            {&spectrum_cover_base88_t1_p0, &spectrum_cover_base88_t1_p1,
             &spectrum_cover_base88_t1_p2},
            {&spectrum_cover_base88_t2_p0, &spectrum_cover_base88_t2_p1,
             &spectrum_cover_base88_t2_p2},
    };
    return covers[track][palette];
}

const lv_image_dsc_t * spectrum_cover_base78(int track, int palette)
{
    track = (track + SPECTRUM_TRACK_COUNT) % SPECTRUM_TRACK_COUNT;
    palette = (palette + SPECTRUM_PALETTE_COUNT) % SPECTRUM_PALETTE_COUNT;
    static const lv_image_dsc_t * const
        covers[SPECTRUM_TRACK_COUNT][SPECTRUM_PALETTE_COUNT] = {
            {&spectrum_cover_base78_t0_p0, &spectrum_cover_base78_t0_p1,
             &spectrum_cover_base78_t0_p2},
            {&spectrum_cover_base78_t1_p0, &spectrum_cover_base78_t1_p1,
             &spectrum_cover_base78_t1_p2},
            {&spectrum_cover_base78_t2_p0, &spectrum_cover_base78_t2_p1,
             &spectrum_cover_base78_t2_p2},
    };
    return covers[track][palette];
}

const lv_image_dsc_t * spectrum_glow_asset(void)
{
    return &spectrum_glow;
}

lv_obj_t * spectrum_box(lv_obj_t * parent, int x, int y, int w, int h)
{
    lv_obj_t * obj = lv_obj_create(parent);
    lv_obj_set_pos(obj, x, y);
    lv_obj_set_size(obj, w, h);
    lv_obj_set_style_pad_all(obj, 0, 0);
    lv_obj_set_style_radius(obj, 0, 0);
    lv_obj_set_style_border_width(obj, 0, 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_TRANSP, 0);
    app_obj_set_scrollable(obj, false);
    app_obj_set_clickable(obj, false);
    lv_obj_set_scrollbar_mode(obj, LV_SCROLLBAR_MODE_OFF);
    return obj;
}

lv_obj_t * spectrum_card(lv_obj_t * parent, int x, int y, int w, int h,
                         int radius, uint32_t bg, lv_opa_t bg_opa)
{
    lv_obj_t * obj = spectrum_box(parent, x, y, w, h);
    lv_obj_set_style_radius(obj, radius, 0);
    lv_obj_set_style_bg_color(obj, lv_color_hex(bg), 0);
    lv_obj_set_style_bg_opa(obj, bg_opa, 0);
    return obj;
}

lv_obj_t * spectrum_label_align(lv_obj_t * parent, const char * text,
                                spectrum_font_id_t font, uint32_t color, int x,
                                int y, int w, int h, lv_text_align_t align)
{
    lv_obj_t * label = lv_label_create(parent);
    lv_obj_set_pos(label, x, y);
    lv_obj_set_size(label, w, h);
    lv_label_set_text(label, text);
    lv_label_set_long_mode(label, LV_LABEL_LONG_MODE_DOTS);
    lv_obj_set_style_text_font(label, spectrum_font(font), 0);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    lv_obj_set_style_text_align(label, align, 0);
    lv_obj_set_style_text_letter_space(
        label,
        (font == SPECTRUM_FONT_MONO_7 || font == SPECTRUM_FONT_MONO_8) ? 1 : 0,
        0);
    lv_obj_set_style_pad_all(label, 0, 0);
    app_obj_set_clickable(label, false);
    return label;
}

lv_obj_t * spectrum_label(lv_obj_t * parent, const char * text,
                          spectrum_font_id_t font, uint32_t color, int x, int y,
                          int w, int h)
{
    return spectrum_label_align(parent, text, font, color, x, y, w, h,
                                LV_TEXT_ALIGN_LEFT);
}

void spectrum_set_icon(lv_obj_t * image, spectrum_icon_id_t icon, int size,
                       uint32_t color)
{
    if(image == NULL) return;
    lv_image_set_src(image, spectrum_icon(icon));
    lv_image_set_scale(image, (uint32_t)((256 * size) / 28));
    lv_obj_set_size(image, 28, 28);
    lv_obj_set_style_image_recolor(image, lv_color_hex(color), 0);
    lv_obj_set_style_image_recolor_opa(image, LV_OPA_COVER, 0);
    app_obj_set_clickable(image, false);
}

lv_obj_t * spectrum_icon_obj(lv_obj_t * parent, spectrum_icon_id_t icon, int x,
                             int y, int size, uint32_t color)
{
    lv_obj_t * image = lv_image_create(parent);
    lv_image_set_src(image, spectrum_icon(icon));
    lv_image_set_scale(image, (uint32_t)((256 * size) / 28));
    lv_obj_set_size(image, 28, 28);
    lv_obj_set_pos(image, x - (28 - size) / 2, y - (28 - size) / 2);
    lv_obj_set_style_image_recolor(image, lv_color_hex(color), 0);
    lv_obj_set_style_image_recolor_opa(image, LV_OPA_COVER, 0);
    app_obj_set_clickable(image, false);
    return image;
}

void spectrum_clickable(lv_obj_t * obj, const char * name)
{
    app_obj_set_clickable(obj, true);
    lv_obj_set_name(obj, name);
}

void spectrum_divider(lv_obj_t * parent, int x, int y, int w)
{
    lv_obj_t * line = spectrum_box(parent, x, y, w, 1);
    lv_obj_set_style_bg_color(line, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_bg_opa(line, 18, 0);
}

static double sp_clamp(double value, double lo, double hi)
{
    return value < lo ? lo : value > hi ? hi : value;
}

static double sp_hash1(double n)
{
    double s = sin(n * 127.1 + 311.7) * 43758.5453123;
    return s - floor(s);
}

static double sp_noise1(double x)
{
    double i = floor(x);
    double f = x - i;
    double u = f * f * (3.0 - 2.0 * f);
    return sp_hash1(i) * (1.0 - u) + sp_hash1(i + 1.0) * u;
}

uint32_t spectrum_mix(uint32_t first, uint32_t second, float t)
{
    t = sp_clamp(t, 0.0f, 1.0f);
    uint32_t ar = (first >> 16) & 0xFF, ag = (first >> 8) & 0xFF,
             ab = first & 0xFF;
    uint32_t br = (second >> 16) & 0xFF, bg = (second >> 8) & 0xFF,
             bb = second & 0xFF;
    uint32_t r = (uint32_t)((float)ar + ((float)br - (float)ar) * t);
    uint32_t g = (uint32_t)((float)ag + ((float)bg - (float)ag) * t);
    uint32_t b = (uint32_t)((float)ab + ((float)bb - (float)ab) * t);
    return (r << 16) | (g << 8) | b;
}

const spectrum_track_t * spectrum_track(void)
{
    return &spectrum_tracks[spectrum_state.track_index];
}

const spectrum_palette_t * spectrum_palette(void)
{
    return &spectrum_palettes[spectrum_state.palette_index];
}

float spectrum_db(void)
{
    return -32.0f + sp_clamp(spectrum_sim.energy, 0.0f, 1.0f) * 30.0f;
}

void spectrum_format_time(char * buffer, size_t size, float seconds)
{
    int total = (int)seconds;
    if(total < 0) total = 0;
    snprintf(buffer, size, "%d:%02d", total / 60, total % 60);
}

void spectrum_sim_reset(void)
{
    const spectrum_track_t * track = spectrum_track();
    spectrum_sim.playhead = 0.0f;
    spectrum_sim.duration = (float)track->duration;
    spectrum_sim.bpm = (float)track->bpm;
    spectrum_sim.beat = 0;
    spectrum_sim.beat_phase = 0.0f;
    spectrum_sim.beat_pulse = 0.0f;
    spectrum_sim.drop = 0.0f;
    spectrum_sim.just_beat = false;
    spectrum_sim.just_drop = false;
    spectrum_sim.burst = 0.0;
    spectrum_sim.low = 0.1f;
    spectrum_sim.mid = 0.1f;
    spectrum_sim.high = 0.1f;
    spectrum_sim.energy = 0.1f;
    for(int i = 0; i < SPECTRUM_BAND_COUNT; i++) {
        spectrum_sim.bands[i] = 0.08f;
        spectrum_sim.targets[i] = 0.08f;
        spectrum_sim.peaks[i] = 0.1f;
    }
    for(int i = 0; i < SPECTRUM_WAVE_COUNT; i++) spectrum_sim.wave[i] = 0.0f;
}

void spectrum_track_select(int index)
{
    index = (index + SPECTRUM_TRACK_COUNT) % SPECTRUM_TRACK_COUNT;
    if(index == spectrum_state.track_index) return;
    spectrum_state.track_index = index;
    if(!spectrum_state.palette_locked) {
        spectrum_state.palette_index = spectrum_tracks[index].palette;
    }
    spectrum_sim_reset();
}

void spectrum_track_next(void)
{
    spectrum_state.track_index =
        (spectrum_state.track_index + 1) % SPECTRUM_TRACK_COUNT;
    if(!spectrum_state.palette_locked) {
        spectrum_state.palette_index =
            spectrum_tracks[spectrum_state.track_index].palette;
    }
    spectrum_sim_reset();
}

void spectrum_track_prev(void)
{
    spectrum_state.track_index =
        (spectrum_state.track_index + SPECTRUM_TRACK_COUNT - 1) %
        SPECTRUM_TRACK_COUNT;
    if(!spectrum_state.palette_locked) {
        spectrum_state.palette_index =
            spectrum_tracks[spectrum_state.track_index].palette;
    }
    spectrum_sim_reset();
}

void spectrum_toggle_play(void)
{
    spectrum_sim.playing = !spectrum_sim.playing;
}

void spectrum_seek(float ratio)
{
    ratio = sp_clamp(ratio, 0.0f, 1.0f);
    spectrum_sim.playhead = ratio * spectrum_sim.duration;
    spectrum_sim.beat =
        (int)floorf((spectrum_sim.playhead * spectrum_sim.bpm) / 60.0f);
    spectrum_sim.beat_phase = 0.0f;
    spectrum_sim.just_beat = false;
    spectrum_sim.just_drop = false;
}

void spectrum_cycle_palette(void)
{
    spectrum_state.palette_index =
        (spectrum_state.palette_index + 1) % SPECTRUM_PALETTE_COUNT;
    spectrum_state.palette_locked = true;
}

void spectrum_set_mode(int mode)
{
    if(mode < 0) mode = SPECTRUM_MODE_COUNT - 1;
    spectrum_state.mode = mode % SPECTRUM_MODE_COUNT;
}

void spectrum_toggle_auto(void)
{
    spectrum_state.auto_cycle = !spectrum_state.auto_cycle;
    spectrum_state.auto_clock = 0.0f;
}

void spectrum_toggle_like(void)
{
    spectrum_state.like = !spectrum_state.like;
}

void spectrum_set_volume(float ratio)
{
    spectrum_state.volume = sp_clamp(ratio, 0.0f, 1.0f);
}

bool spectrum_sim_update(double dt)
{
    dt = sp_clamp(dt, 0.0, 0.08);
    spectrum_sim.time += dt;
    spectrum_sim.just_beat = false;
    spectrum_sim.just_drop = false;
    spectrum_sim.burst =
        spectrum_sim.burst > dt * 2.2 ? spectrum_sim.burst - dt * 2.2 : 0.0;

    if(spectrum_sim.playing) {
        spectrum_sim.playhead += dt;
        if(spectrum_sim.playhead >= spectrum_sim.duration) {
            spectrum_track_next();
            return true;
        }
        double beats = (spectrum_sim.playhead * spectrum_sim.bpm) / 60.0;
        int b = (int)floor(beats);
        spectrum_sim.beat_phase = beats - (double)b;
        if(b != spectrum_sim.beat) {
            spectrum_sim.beat = b;
            spectrum_sim.just_beat = true;
            if(b > 0 && (b % 8) == 0) {
                spectrum_sim.just_drop = true;
                spectrum_sim.drop = 1.0;
            }
        }
        spectrum_sim.beat_pulse = exp(-spectrum_sim.beat_phase * 5.2);
        spectrum_sim.drop = sp_clamp(spectrum_sim.drop - dt * 0.55, 0.0, 1.0);
    }
    else {
        spectrum_sim.beat_pulse *= exp(-dt * 7.0);
        spectrum_sim.drop = sp_clamp(spectrum_sim.drop - dt * 0.9, 0.0, 1.0);
    }

    const double t = spectrum_sim.time;
    const double kick = spectrum_sim.beat_pulse;
    const double play = spectrum_sim.playing ? 1.0 : 0.2;
    double low_sum = 0.0;
    double mid_sum = 0.0;
    double high_sum = 0.0;

    for(int i = 0; i < SPECTRUM_BAND_COUNT; i++) {
        double f = (double)i / (double)(SPECTRUM_BAND_COUNT - 1);
        double v = 0.1 + 0.36 * exp(-f * 2.0);

        double m1 = 0.16 + 0.15 * sin(t * 0.31) + 0.10 * sin(t * 0.17 + 1.3);
        double m2 = 0.60 + 0.16 * sin(t * 0.23 + 2.1);
        v += 0.52 * exp(-pow((f - m1) / 0.05, 2.0));
        v += 0.34 * exp(-pow((f - m2) / 0.075, 2.0));
        v += 0.11 * sin((double)i * 1.7 + t * 2.3) *
             sin((double)i * 0.29 + t * 0.8);
        v += 0.09 * (sp_noise1((double)i * 0.37 + t * 1.9) - 0.5);
        v *= 0.78 + 0.22 * sin((double)i * 0.55 + t * 3.8 + sin(t * 0.6) * 2.0);

        if(i < 9) v += kick * 0.55 * (1.0 - (double)i / 11.0);
        v += kick * 0.14 * exp(-pow((f - 0.35) / 0.18, 2.0));
        v += pow(spectrum_sim.beat_phase, 3.0) * 0.22 *
             exp(-pow((f - 0.82) / 0.18, 2.0));
        v += spectrum_sim.drop * 0.28 *
             (0.45 + 0.55 * sin(t * 2.6 + (double)i * 0.5));

        v = sp_clamp(
            v *
                (0.55 + 0.65 * (spectrum_sim.energy > 0.1 ? spectrum_sim.energy
                                                          : 0.1)) *
                play,
            0.02, 1.2);
        spectrum_sim.targets[i] = (float)v;

        float current = spectrum_sim.bands[i];
        double k = v > current ? 1.0 - exp(-dt / 0.028) : 1.0 - exp(-dt / 0.2);
        spectrum_sim.bands[i] =
            (float)((double)current + (v - (double)current) * k);

        float bv = spectrum_sim.bands[i];
        if(bv >= spectrum_sim.peaks[i]) spectrum_sim.peaks[i] = bv;
        else
            spectrum_sim.peaks[i] =
                bv > spectrum_sim.peaks[i] - (float)(dt * 0.62)
                    ? bv
                    : spectrum_sim.peaks[i] - (float)(dt * 0.62);

        if(i < 12) low_sum += bv;
        else if(i < 32)
            mid_sum += bv;
        else
            high_sum += bv;
    }

    spectrum_sim.low = low_sum / 12.0;
    spectrum_sim.mid = mid_sum / 20.0;
    spectrum_sim.high = high_sum / (double)(SPECTRUM_BAND_COUNT - 32);
    spectrum_sim.energy = spectrum_sim.low * 0.5 + spectrum_sim.mid * 0.3 +
                          spectrum_sim.high * 0.2;

    double amp = 0.10 + spectrum_sim.energy * 0.55 +
                 spectrum_sim.beat_pulse * 0.22 + spectrum_sim.burst * 0.18;
    for(int j = 0; j < SPECTRUM_WAVE_COUNT; j++) {
        double p = (double)j / (double)(SPECTRUM_WAVE_COUNT - 1);
        double y =
            sin(p * SP_PI * 4.0 + t * 3.8 +
                sin(p * SP_PI * 2.8 + t * 1.5) * 1.6) *
                0.55 +
            sin(p * SP_PI * 10.0 - t * 2.7 + sin(t * 1.1) * 0.8) * 0.28 +
            sin(p * SP_PI * 22.0 + t * 5.2) * 0.08 * (0.4 + spectrum_sim.high) +
            sin(p * SP_PI * 46.0 - t * 7.0) * 0.03;
        spectrum_sim.wave[j] =
            (float)(y * amp * (spectrum_sim.playing ? 1.0 : 0.35));
    }

    return false;
}

#endif
