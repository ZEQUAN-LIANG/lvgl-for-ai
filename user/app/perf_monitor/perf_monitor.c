#include "perf_monitor.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include "app.h"

#include "perf_font_mono_10.h"
#include "perf_font_mono_8.h"
#include "perf_font_num_14.h"
#include "perf_font_num_22.h"
#include "perf_font_num_26.h"
#include "perf_font_num_46.h"
#include "perf_font_num_52.h"
#include "perf_font_num_60.h"

#include <stdio.h>
#include <string.h>

#define PERF_W                172
#define PERF_H                320
#define PERF_LAND_W           320
#define PERF_LAND_H           172
#define PERF_HISTORY          60
#define PERF_THREADS          16
#define PERF_THREAD_BAR_H     18
#define PERF_THREAD_SPAN      156
#define PERF_THREAD_GAP       4
#define PERF_CPU_CHART_H      33
#define PERF_LAND_CPU_CHART_H 30
#define PERF_NET_CHART_H      18

#define COL_BG        0x0B0906
#define COL_STATUS    0x0E0B07
#define COL_TAPE      0x0D0A07
#define COL_INK       0xEFE7D3
#define COL_MUTED     0x978D78
#define COL_DIM       0x6B6250
#define COL_LINE      0x2A241A
#define COL_LINE_SOFT 0x1A1710
#define COL_ACCENT    0xFF5A2C
#define COL_WARN      0xF0B347

typedef struct {
    lv_obj_t * host;
    lv_obj_t * clock;
    lv_obj_t * cpu_value;
    lv_obj_t * cpu_trend;
    lv_obj_t * cpu_meta;
    lv_obj_t * cpu_unit;
    lv_obj_t * cpu_freq;
    lv_obj_t * cpu_temp;
    lv_obj_t * cpu_canvas;
    lv_obj_t * cpu_axis_start;
    lv_obj_t * tape_tag;
    lv_obj_t * net_canvas;
    lv_obj_t * mem_value;
    lv_obj_t * mem_sub;
    lv_obj_t * mem_unit;
    lv_obj_t * mem_bar;
    lv_obj_t * gpu_value;
    lv_obj_t * gpu_sub;
    lv_obj_t * gpu_unit;
    lv_obj_t * gpu_bar;
    lv_obj_t * down;
    lv_obj_t * up;
    lv_obj_t * ping;
    lv_obj_t * peak;
    lv_obj_t * state;
    lv_obj_t * footer_mid;
    lv_obj_t * pulse;
    lv_obj_t * thread_track[PERF_THREADS];
    lv_obj_t * thread_fill[PERF_THREADS];
    int cpu_chart_w;
    int cpu_chart_h;
    int net_chart_w;
    int net_chart_h;
    int thread_x;
    int thread_y;
    int thread_span;
    int thread_gap;
    int thread_bar_h;
    int thread_max_w;
} perf_ui_t;

static perf_ui_t s_ui;
static perf_sample_t s_sample;
static uint8_t s_cpu_hist[PERF_HISTORY];
static uint8_t s_down_hist[PERF_HISTORY];
static uint8_t s_up_hist[PERF_HISTORY];
static uint16_t s_cpu_fb[PERF_LAND_W * PERF_CPU_CHART_H];
static uint16_t s_net_fb[PERF_W * PERF_NET_CHART_H];
static lv_obj_t * s_screen;
static lv_timer_t * s_timer;
static uint32_t s_tick;
static uint32_t s_last_live_ms;
static uint32_t s_live_period_ms = 300u;
static uint32_t s_rng = 0x13579BDFu;
static uint32_t s_demo_seq;
static uint32_t s_demo_tick;
static uint32_t s_demo_minutes = 20u * 60u + 48u;
static int s_demo_cpu = 47;
static int s_demo_gpu = 29;
static int s_demo_down = 12000;
static int s_demo_up = 800;
static bool s_ready;
static bool s_landscape;
static bool s_demo = true;
static bool s_have_live;
static bool s_link_lost;
static uint16_t s_last_seq;

static int clamp_int(int value, int lo, int hi)
{
    if(value < lo) return lo;
    if(value > hi) return hi;
    return value;
}

static uint32_t random_u32(void)
{
    s_rng ^= s_rng << 13;
    s_rng ^= s_rng >> 17;
    s_rng ^= s_rng << 5;
    return s_rng;
}

static int random_between(int lo, int hi)
{
    return lo + (int)(random_u32() % (uint32_t)(hi - lo + 1));
}

static void history_push(uint8_t * history, uint8_t value)
{
    memmove(history, history + 1, PERF_HISTORY - 1);
    history[PERF_HISTORY - 1] = value;
}

static uint32_t net_norm(uint32_t kib_s, uint32_t full_kib_s)
{
    uint32_t value = (kib_s * 100u) / full_kib_s;
    return value > 100u ? 100u : value;
}

/* ------------------------------------------------------------------ */
/* drawing primitives                                                 */
/* ------------------------------------------------------------------ */

static void draw_line(lv_layer_t * layer, int x1, int y1, int x2, int y2,
                      uint32_t color, int width, lv_opa_t opa, int dash_width,
                      int dash_gap)
{
    lv_draw_line_dsc_t dsc;

    lv_draw_line_dsc_init(&dsc);
    dsc.color = lv_color_hex(color);
    dsc.width = width;
    dsc.opa = opa;
    dsc.p1.x = x1;
    dsc.p1.y = y1;
    dsc.p2.x = x2;
    dsc.p2.y = y2;
    dsc.dash_width = dash_width;
    dsc.dash_gap = dash_gap;
    lv_draw_line(layer, &dsc);
}

static void draw_rect(lv_layer_t * layer, int x, int y, int w, int h,
                      uint32_t color, lv_opa_t opa)
{
    lv_draw_rect_dsc_t dsc;
    lv_area_t area;

    if(w <= 0 || h <= 0) return;
    lv_draw_rect_dsc_init(&dsc);
    dsc.bg_color = lv_color_hex(color);
    dsc.bg_opa = opa;
    dsc.radius = 0;
    area.x1 = x;
    area.y1 = y;
    area.x2 = x + w - 1;
    area.y2 = y + h - 1;
    lv_draw_rect(layer, &dsc, &area);
}

static void draw_dot(lv_layer_t * layer, int cx, int cy, int radius,
                     uint32_t color, lv_opa_t opa)
{
    lv_draw_rect_dsc_t dsc;
    lv_area_t area;

    lv_draw_rect_dsc_init(&dsc);
    dsc.bg_color = lv_color_hex(color);
    dsc.bg_opa = opa;
    dsc.radius = LV_RADIUS_CIRCLE;
    area.x1 = cx - radius;
    area.y1 = cy - radius;
    area.x2 = cx + radius;
    area.y2 = cy + radius;
    lv_draw_rect(layer, &dsc, &area);
}

/* ------------------------------------------------------------------ */
/* charts                                                             */
/* ------------------------------------------------------------------ */

static void draw_cpu_chart(void)
{
    lv_layer_t layer;
    const int w = s_ui.cpu_chart_w;
    const int h = s_ui.cpu_chart_h;
    const int top = 2;
    const int bottom = h - 3;

    if(s_ui.cpu_canvas == NULL || w <= 0 || h <= 0) return;

    lv_canvas_fill_bg(s_ui.cpu_canvas, lv_color_hex(COL_TAPE), LV_OPA_COVER);
    lv_canvas_init_layer(s_ui.cpu_canvas, &layer);

    for(int i = 10; i < PERF_HISTORY; i += 10) {
        int x = (i * w) / PERF_HISTORY;
        draw_line(&layer, x, 0, x, h - 1, COL_INK, 1, LV_OPA_10, 0, 0);
    }

    int threshold_y = top + ((100 - 80) * (bottom - top)) / 100;
    draw_line(&layer, 0, threshold_y, w - 1, threshold_y, COL_INK, 1, LV_OPA_30,
              2, 3);

    for(int i = 0; i < PERF_HISTORY; i++) {
        int x0 = (i * w) / PERF_HISTORY;
        int x1 = ((i + 1) * w) / PERF_HISTORY;
        int y = bottom - ((int)s_cpu_hist[i] * (bottom - top)) / 100;

        draw_rect(&layer, x0, y, x1 - x0, h - y, COL_INK, LV_OPA_10);
    }

    for(int i = 0; i < PERF_HISTORY; i++) {
        int x0 = (i * w) / PERF_HISTORY;
        int x1 = ((i + 1) * w) / PERF_HISTORY;
        int y = bottom - ((int)s_cpu_hist[i] * (bottom - top)) / 100;

        draw_line(&layer, x0, y, x1 - 1, y, COL_INK, 1, LV_OPA_80, 0, 0);
        if(i > 0) {
            int prev = bottom - ((int)s_cpu_hist[i - 1] * (bottom - top)) / 100;
            draw_line(&layer, x0, prev, x0, y, COL_INK, 1, LV_OPA_80, 0, 0);
        }
    }

    int head_y =
        bottom - ((int)s_cpu_hist[PERF_HISTORY - 1] * (bottom - top)) / 100;
    draw_line(&layer, w - 1, 0, w - 1, h - 1, COL_ACCENT, 1, LV_OPA_30, 0, 0);
    draw_dot(&layer, w - 4, head_y, 4, COL_ACCENT, LV_OPA_20);
    draw_dot(&layer, w - 4, head_y, 2, COL_ACCENT, LV_OPA_COVER);

    lv_canvas_finish_layer(s_ui.cpu_canvas, &layer);
    lv_obj_invalidate(s_ui.cpu_canvas);
}

static void draw_net_chart(void)
{
    lv_layer_t layer;
    const int w = s_ui.net_chart_w;
    const int h = s_ui.net_chart_h;
    const int mid = h / 2;
    const int amp = mid - 2;

    if(s_ui.net_canvas == NULL || w <= 0 || h <= 0) return;

    lv_canvas_fill_bg(s_ui.net_canvas, lv_color_hex(COL_BG), LV_OPA_COVER);
    lv_canvas_init_layer(s_ui.net_canvas, &layer);

    draw_line(&layer, 0, mid, w - 1, mid, COL_INK, 1, LV_OPA_10, 0, 0);

    for(int i = 0; i < PERF_HISTORY; i++) {
        int x0 = (i * w) / PERF_HISTORY;
        int x1 = ((i + 1) * w) / PERF_HISTORY;
        int down_y = mid - ((int)s_down_hist[i] * amp) / 100;
        int up_y = mid + ((int)s_up_hist[i] * amp) / 100;

        draw_rect(&layer, x0, down_y, x1 - x0, mid - down_y, COL_INK,
                  LV_OPA_10);
        draw_rect(&layer, x0, mid, x1 - x0, up_y - mid, COL_ACCENT, LV_OPA_10);
    }

    for(int i = 0; i < PERF_HISTORY; i++) {
        int x0 = (i * w) / PERF_HISTORY;
        int x1 = ((i + 1) * w) / PERF_HISTORY;
        int down_y = mid - ((int)s_down_hist[i] * amp) / 100;
        int up_y = mid + ((int)s_up_hist[i] * amp) / 100;

        draw_line(&layer, x0, down_y, x1 - 1, down_y, COL_INK, 1, LV_OPA_80, 0,
                  0);
        draw_line(&layer, x0, up_y, x1 - 1, up_y, COL_ACCENT, 1, LV_OPA_90, 0,
                  0);
        if(i > 0) {
            int prev_down = mid - ((int)s_down_hist[i - 1] * amp) / 100;
            int prev_up = mid + ((int)s_up_hist[i - 1] * amp) / 100;
            draw_line(&layer, x0, prev_down, x0, down_y, COL_INK, 1, LV_OPA_80,
                      0, 0);
            draw_line(&layer, x0, prev_up, x0, up_y, COL_ACCENT, 1, LV_OPA_90,
                      0, 0);
        }
    }

    int last_down = mid - ((int)s_down_hist[PERF_HISTORY - 1] * amp) / 100;
    int last_up = mid + ((int)s_up_hist[PERF_HISTORY - 1] * amp) / 100;
    draw_dot(&layer, w - 4, last_down, 1, COL_INK, LV_OPA_COVER);
    draw_dot(&layer, w - 4, last_up, 1, COL_ACCENT, LV_OPA_COVER);

    lv_canvas_finish_layer(s_ui.net_canvas, &layer);
    lv_obj_invalidate(s_ui.net_canvas);
}

/* ------------------------------------------------------------------ */
/* UI builders                                                        */
/* ------------------------------------------------------------------ */

static lv_obj_t * make_label(lv_obj_t * parent, const char * text,
                             const lv_font_t * font, uint32_t color, int x,
                             int y, int width, lv_text_align_t align,
                             int letter_space)
{
    lv_obj_t * label = lv_label_create(parent);

    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    lv_obj_set_pos(label, x, y);
    if(width > 0) {
        lv_obj_set_width(label, width);
        lv_obj_set_style_text_align(label, align, 0);
    }
    if(letter_space > 0) {
        lv_obj_set_style_text_letter_space(label, letter_space, 0);
    }
    return label;
}

static lv_obj_t * make_line(lv_obj_t * parent, int x, int y, int w)
{
    lv_obj_t * line = lv_obj_create(parent);

    lv_obj_remove_style_all(line);
    lv_obj_set_pos(line, x, y);
    lv_obj_set_size(line, w, 1);
    lv_obj_set_style_bg_color(line, lv_color_hex(COL_LINE), 0);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);
    app_obj_set_scrollable(line, false);
    return line;
}

static lv_obj_t * make_vline(lv_obj_t * parent, int x, int y, int h)
{
    lv_obj_t * line = lv_obj_create(parent);

    lv_obj_remove_style_all(line);
    lv_obj_set_pos(line, x, y);
    lv_obj_set_size(line, 1, h);
    lv_obj_set_style_bg_color(line, lv_color_hex(COL_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);
    app_obj_set_scrollable(line, false);
    return line;
}

static lv_obj_t * make_bar(lv_obj_t * parent, int x, int y, int w, int h)
{
    lv_obj_t * bar = lv_bar_create(parent);

    lv_obj_set_pos(bar, x, y);
    lv_obj_set_size(bar, w, h);
    lv_bar_set_range(bar, 0, 100);
    lv_bar_set_value(bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_radius(bar, 0, 0);
    lv_obj_set_style_radius(bar, 0, LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(bar, lv_color_hex(COL_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(bar, lv_color_hex(COL_INK), LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(bar, LV_OPA_80, LV_PART_INDICATOR);
    app_obj_set_scrollable(bar, false);
    return bar;
}

static lv_obj_t * make_canvas(lv_obj_t * parent, int x, int y, int w, int h,
                              uint16_t * buffer, const char * name)
{
    lv_obj_t * canvas = lv_canvas_create(parent);

    lv_obj_set_pos(canvas, x, y);
    lv_obj_set_size(canvas, w, h);
    lv_obj_set_style_pad_all(canvas, 0, 0);
    lv_obj_set_style_border_width(canvas, 0, 0);
    lv_obj_set_style_radius(canvas, 0, 0);
    lv_obj_set_style_bg_opa(canvas, LV_OPA_TRANSP, 0);
    app_obj_set_scrollable(canvas, false);
    lv_canvas_set_buffer(canvas, buffer, w, h, LV_COLOR_FORMAT_RGB565);
    app_obj_set_name(canvas, name);
    return canvas;
}

static void build_status(lv_obj_t * screen)
{
    lv_obj_t * background = lv_obj_create(screen);

    lv_obj_remove_style_all(background);
    lv_obj_set_pos(background, 0, 0);
    lv_obj_set_size(background, PERF_W, 26);
    lv_obj_set_style_bg_color(background, lv_color_hex(COL_STATUS), 0);
    lv_obj_set_style_bg_opa(background, LV_OPA_COVER, 0);
    app_obj_set_scrollable(background, false);

    lv_obj_t * mark = lv_obj_create(screen);
    lv_obj_remove_style_all(mark);
    lv_obj_set_pos(mark, 8, 11);
    lv_obj_set_size(mark, 4, 4);
    lv_obj_set_style_bg_color(mark, lv_color_hex(COL_ACCENT), 0);
    lv_obj_set_style_bg_opa(mark, LV_OPA_COVER, 0);
    app_obj_set_scrollable(mark, false);
    app_obj_set_name(mark, "perf_mark");

    lv_obj_t * brand = make_label(screen, "PERF", &perf_font_mono_8, COL_INK,
                                  15, 9, 0, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(brand, "perf_brand");

    s_ui.host = make_label(screen, "DESKTOP-01", &perf_font_mono_8, COL_DIM, 50,
                           9, 64, LV_TEXT_ALIGN_CENTER, 0);
    app_obj_set_name(s_ui.host, "perf_host");

    s_ui.clock = make_label(screen, "20:48", &perf_font_mono_10, COL_INK, 120,
                            8, 44, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.clock, "perf_clock");

    make_line(screen, 0, 26, PERF_W);
}

static void build_cpu(lv_obj_t * screen)
{
    lv_obj_t * label;

    s_ui.cpu_chart_w = PERF_W;
    s_ui.cpu_chart_h = PERF_CPU_CHART_H;

    label = make_label(screen, "CPU LOAD", &perf_font_mono_8, COL_MUTED, 8, 30,
                       0, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(label, "perf_cpu_label");

    s_ui.cpu_trend = make_label(screen, "+2", &perf_font_mono_8, COL_ACCENT,
                                112, 30, 20, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.cpu_trend, "perf_cpu_trend");

    s_ui.cpu_meta = make_label(screen, " · 8T", &perf_font_mono_8, COL_DIM, 136,
                               30, 30, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.cpu_meta, "perf_cpu_meta");

    s_ui.cpu_value = make_label(screen, "47", &perf_font_num_60, COL_INK, 8, 33,
                                0, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.cpu_value, "perf_cpu_value");

    s_ui.cpu_unit = make_label(screen, "%", &perf_font_mono_8, COL_MUTED, 81,
                               49, 0, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.cpu_unit, "perf_cpu_unit");

    lv_obj_t * hairline = lv_obj_create(screen);
    lv_obj_remove_style_all(hairline);
    lv_obj_set_pos(hairline, 123, 48);
    lv_obj_set_size(hairline, 1, 45);
    lv_obj_set_style_bg_color(hairline, lv_color_hex(COL_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(hairline, LV_OPA_COVER, 0);
    app_obj_set_scrollable(hairline, false);

    s_ui.cpu_freq = make_label(screen, "3.48", &perf_font_num_14, COL_INK, 124,
                               50, 29, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.cpu_freq, "perf_cpu_freq");
    label = make_label(screen, "GHz", &perf_font_mono_8, COL_MUTED, 154, 53, 0,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_cpu_freq_unit");

    s_ui.cpu_temp = make_label(screen, "63", &perf_font_num_14, COL_INK, 124,
                               68, 29, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.cpu_temp, "perf_cpu_temp");
    label = make_label(screen, "°C", &perf_font_mono_8, COL_MUTED, 154, 71, 0,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_cpu_temp_unit");

    make_line(screen, 0, 104, PERF_W);

    s_ui.cpu_canvas = make_canvas(screen, 0, 105, PERF_W, PERF_CPU_CHART_H,
                                  s_cpu_fb, "perf_cpu_chart");

    label = make_label(screen, "80", &perf_font_mono_8, COL_DIM, 151, 106, 13,
                       LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_set_style_bg_color(label, lv_color_hex(COL_TAPE), 0);
    lv_obj_set_style_bg_opa(label, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_hor(label, 1, 0);
    app_obj_set_name(label, "perf_cpu_threshold");

    s_ui.cpu_axis_start = make_label(screen, "-18S", &perf_font_mono_8, COL_DIM,
                                     6, 136, 0, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(s_ui.cpu_axis_start, "perf_cpu_axis_start");
    label = make_label(screen, "NOW", &perf_font_mono_8, COL_DIM, 144, 136, 22,
                       LV_TEXT_ALIGN_RIGHT, 1);
    app_obj_set_name(label, "perf_cpu_axis_now");
}

static void build_split(lv_obj_t * screen)
{
    make_line(screen, 0, 146, PERF_W);
    make_line(screen, 0, 200, PERF_W);

    lv_obj_t * divider = lv_obj_create(screen);
    lv_obj_remove_style_all(divider);
    lv_obj_set_pos(divider, 86, 153);
    lv_obj_set_size(divider, 1, 41);
    lv_obj_set_style_bg_color(divider, lv_color_hex(COL_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);
    app_obj_set_scrollable(divider, false);

    lv_obj_t * label;

    label = make_label(screen, "MEM", &perf_font_mono_8, COL_MUTED, 8, 152, 0,
                       LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(label, "perf_mem_label");
    s_ui.mem_sub = make_label(screen, "11.5/32G", &perf_font_mono_8, COL_DIM,
                              32, 152, 46, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.mem_sub, "perf_mem_sub");
    s_ui.mem_value = make_label(screen, "36", &perf_font_num_26, COL_INK, 8,
                                157, 0, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.mem_value, "perf_mem_value");
    s_ui.mem_unit = make_label(screen, "%", &perf_font_mono_8, COL_MUTED, 46,
                               162, 0, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.mem_unit, "perf_mem_unit");
    s_ui.mem_bar = make_bar(screen, 8, 190, 70, 3);
    app_obj_set_name(s_ui.mem_bar, "perf_mem_bar");

    label = make_label(screen, "GPU", &perf_font_mono_8, COL_MUTED, 94, 152, 0,
                       LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(label, "perf_gpu_label");
    s_ui.gpu_sub = make_label(screen, "55°C", &perf_font_mono_8, COL_DIM, 120,
                              152, 44, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.gpu_sub, "perf_gpu_sub");
    s_ui.gpu_value = make_label(screen, "29", &perf_font_num_26, COL_INK, 94,
                                157, 0, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.gpu_value, "perf_gpu_value");
    s_ui.gpu_unit = make_label(screen, "%", &perf_font_mono_8, COL_MUTED, 132,
                               162, 0, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.gpu_unit, "perf_gpu_unit");
    s_ui.gpu_bar = make_bar(screen, 94, 190, 70, 3);
    app_obj_set_name(s_ui.gpu_bar, "perf_gpu_bar");
}

static void build_net(lv_obj_t * screen)
{
    lv_obj_t * label;

    s_ui.net_chart_w = PERF_W;
    s_ui.net_chart_h = PERF_NET_CHART_H;

    label = make_label(screen, "NET", &perf_font_mono_8, COL_MUTED, 8, 205, 0,
                       LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(label, "perf_net_label");
    s_ui.ping = make_label(screen, "PING 15 MS", &perf_font_mono_8, COL_DIM,
                           104, 205, 60, LV_TEXT_ALIGN_RIGHT, 1);
    app_obj_set_name(s_ui.ping, "perf_ping");

    label = make_label(screen, "↓", &perf_font_mono_8, COL_MUTED, 8, 217, 0,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_down_arrow");
    s_ui.down = make_label(screen, "11.9", &perf_font_num_22, COL_INK, 16, 211,
                           52, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.down, "perf_down");
    label = make_label(screen, "MB/S", &perf_font_mono_8, COL_DIM, 63, 216, 0,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_down_unit");

    label = make_label(screen, "↑", &perf_font_mono_8, COL_ACCENT, 111, 217, 0,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_up_arrow");
    s_ui.up = make_label(screen, "0.7", &perf_font_num_22, COL_INK, 119, 211,
                         30, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.up, "perf_up");
    label = make_label(screen, "MB/S", &perf_font_mono_8, COL_DIM, 149, 216, 0,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_up_unit");

    s_ui.net_canvas = make_canvas(screen, 0, 238, PERF_W, PERF_NET_CHART_H,
                                  s_net_fb, "perf_net_chart");
}

static void build_threads(lv_obj_t * screen)
{
    lv_obj_t * label;

    s_ui.thread_x = 8;
    s_ui.thread_y = 275;
    s_ui.thread_span = PERF_THREAD_SPAN;
    s_ui.thread_gap = PERF_THREAD_GAP;
    s_ui.thread_bar_h = PERF_THREAD_BAR_H;
    s_ui.thread_max_w = 18;

    label = make_label(screen, "THREADS", &perf_font_mono_8, COL_MUTED, 8, 260,
                       0, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(label, "perf_threads_label");
    s_ui.peak = make_label(screen, "PEAK 61%", &perf_font_mono_8, COL_DIM, 100,
                           260, 64, LV_TEXT_ALIGN_RIGHT, 1);
    app_obj_set_name(s_ui.peak, "perf_threads_peak");

    for(int i = 0; i < PERF_THREADS; i++) {
        char name[24];
        lv_obj_t * track = lv_obj_create(screen);
        lv_obj_remove_style_all(track);
        lv_obj_set_pos(track, 8 + i * 10, 275);
        lv_obj_set_size(track, 6, PERF_THREAD_BAR_H);
        lv_obj_set_style_bg_color(track, lv_color_hex(COL_LINE_SOFT), 0);
        lv_obj_set_style_bg_opa(track, LV_OPA_COVER, 0);
        app_obj_set_scrollable(track, false);
        snprintf(name, sizeof(name), "perf_thread_%02d", i);
        app_obj_set_name(track, name);
        s_ui.thread_track[i] = track;

        lv_obj_t * fill = lv_obj_create(track);
        lv_obj_remove_style_all(fill);
        lv_obj_set_size(fill, 6, 3);
        lv_obj_align(fill, LV_ALIGN_BOTTOM_MID, 0, 0);
        lv_obj_set_style_bg_color(fill, lv_color_hex(COL_INK), 0);
        lv_obj_set_style_bg_opa(fill, LV_OPA_COVER, 0);
        app_obj_set_scrollable(fill, false);
        s_ui.thread_fill[i] = fill;
    }

    make_line(screen, 0, 296, PERF_W);
}

static void build_footer(lv_obj_t * screen)
{
    lv_obj_t * dot = lv_obj_create(screen);

    lv_obj_remove_style_all(dot);
    lv_obj_set_pos(dot, 8, 305);
    lv_obj_set_size(dot, 4, 4);
    lv_obj_set_style_bg_color(dot, lv_color_hex(COL_ACCENT), 0);
    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    app_obj_set_scrollable(dot, false);
    s_ui.pulse = dot;
    app_obj_set_name(dot, "perf_pulse");

    s_ui.state = make_label(screen, "SIM", &perf_font_mono_8, COL_MUTED, 15,
                            303, 34, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(s_ui.state, "perf_state");

    s_ui.footer_mid = make_label(screen, "SIM · 0.3S", &perf_font_mono_8,
                                 COL_DIM, 52, 303, 70, LV_TEXT_ALIGN_CENTER, 1);
    app_obj_set_name(s_ui.footer_mid, "perf_footer_mid");

    lv_obj_t * right = make_label(screen, "C6/01", &perf_font_mono_8, COL_DIM,
                                  140, 303, 24, LV_TEXT_ALIGN_RIGHT, 1);
    app_obj_set_name(right, "perf_footer_right");
}

/* ------------------------------------------------------------------ */
/* landscape builders — 320 x 172                                     */
/* ------------------------------------------------------------------ */

static void build_status_landscape(lv_obj_t * screen)
{
    lv_obj_t * background = lv_obj_create(screen);

    lv_obj_remove_style_all(background);
    lv_obj_set_pos(background, 0, 0);
    lv_obj_set_size(background, PERF_LAND_W, 20);
    lv_obj_set_style_bg_color(background, lv_color_hex(COL_STATUS), 0);
    lv_obj_set_style_bg_opa(background, LV_OPA_COVER, 0);
    app_obj_set_scrollable(background, false);

    lv_obj_t * mark = lv_obj_create(screen);

    lv_obj_remove_style_all(mark);
    lv_obj_set_pos(mark, 8, 8);
    lv_obj_set_size(mark, 4, 4);
    lv_obj_set_style_bg_color(mark, lv_color_hex(COL_ACCENT), 0);
    lv_obj_set_style_bg_opa(mark, LV_OPA_COVER, 0);
    app_obj_set_scrollable(mark, false);
    app_obj_set_name(mark, "perf_mark");

    lv_obj_t * brand = make_label(screen, "PERF", &perf_font_mono_8, COL_INK,
                                  15, 6, 0, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(brand, "perf_brand");

    s_ui.host = make_label(screen, "DESKTOP-01", &perf_font_mono_8, COL_DIM, 64,
                           6, 96, LV_TEXT_ALIGN_CENTER, 0);
    app_obj_set_name(s_ui.host, "perf_host");

    s_ui.clock = make_label(screen, "20:48", &perf_font_mono_10, COL_INK, 268,
                            5, 44, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.clock, "perf_clock");

    make_line(screen, 0, 20, PERF_LAND_W);
}

static void build_cpu_landscape(lv_obj_t * screen)
{
    lv_obj_t * label;

    s_ui.cpu_chart_w = PERF_LAND_W;
    s_ui.cpu_chart_h = PERF_LAND_CPU_CHART_H;

    label = make_label(screen, "CPU LOAD", &perf_font_mono_8, COL_MUTED, 8, 24,
                       0, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(label, "perf_cpu_label");

    s_ui.cpu_trend = make_label(screen, "+2", &perf_font_mono_8, COL_ACCENT, 78,
                                24, 24, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.cpu_trend, "perf_cpu_trend");

    s_ui.cpu_meta = make_label(screen, " · 8T", &perf_font_mono_8, COL_DIM, 104,
                               24, 30, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.cpu_meta, "perf_cpu_meta");

    s_ui.cpu_value = make_label(screen, "47", &perf_font_num_52, COL_INK, 8, 32,
                                0, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.cpu_value, "perf_cpu_value");

    s_ui.cpu_unit = make_label(screen, "%", &perf_font_mono_8, COL_MUTED, 8, 39,
                               0, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.cpu_unit, "perf_cpu_unit");

    make_vline(screen, 84, 37, 45);

    s_ui.cpu_freq = make_label(screen, "3.48", &perf_font_num_14, COL_INK, 86,
                               37, 29, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.cpu_freq, "perf_cpu_freq");
    label = make_label(screen, "GHz", &perf_font_mono_8, COL_MUTED, 116, 40, 0,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_cpu_freq_unit");

    s_ui.cpu_temp = make_label(screen, "63", &perf_font_num_14, COL_INK, 86, 56,
                               29, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.cpu_temp, "perf_cpu_temp");
    label = make_label(screen, "°C", &perf_font_mono_8, COL_MUTED, 116, 59, 0,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_cpu_temp_unit");

    make_line(screen, 0, 90, PERF_LAND_W);

    s_ui.cpu_canvas =
        make_canvas(screen, 0, 91, PERF_LAND_W, PERF_LAND_CPU_CHART_H, s_cpu_fb,
                    "perf_cpu_chart");

    s_ui.tape_tag = make_label(screen, "CPU · 18S", &perf_font_mono_8, COL_DIM,
                               4, 92, 0, LV_TEXT_ALIGN_LEFT, 1);
    lv_obj_set_style_bg_color(s_ui.tape_tag, lv_color_hex(COL_TAPE), 0);
    lv_obj_set_style_bg_opa(s_ui.tape_tag, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_hor(s_ui.tape_tag, 2, 0);
    app_obj_set_name(s_ui.tape_tag, "perf_tape_tag");

    label = make_label(screen, "80", &perf_font_mono_8, COL_DIM, 296, 92, 20,
                       LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_set_style_bg_color(label, lv_color_hex(COL_TAPE), 0);
    lv_obj_set_style_bg_opa(label, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_hor(label, 1, 0);
    app_obj_set_name(label, "perf_cpu_threshold");

    s_ui.cpu_axis_start = make_label(screen, "-18S", &perf_font_mono_8, COL_DIM,
                                     8, 121, 0, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(s_ui.cpu_axis_start, "perf_cpu_axis_start");
    label = make_label(screen, "NOW", &perf_font_mono_8, COL_DIM, 290, 121, 24,
                       LV_TEXT_ALIGN_RIGHT, 1);
    app_obj_set_name(label, "perf_cpu_axis_now");
}

static void build_metric_landscape(lv_obj_t * screen, bool memory)
{
    int x = memory ? 142 : 198;
    const char * label_text = memory ? "MEM" : "GPU";
    const char * sub_text = memory ? "11.5/32G" : "55°C";

    lv_obj_t * label = make_label(screen, label_text, &perf_font_mono_8,
                                  COL_MUTED, x, 24, 0, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(label, memory ? "perf_mem_label" : "perf_gpu_label");

    lv_obj_t * value = make_label(screen, "36", &perf_font_num_26, COL_INK, x,
                                  34, 0, LV_TEXT_ALIGN_LEFT, 0);
    lv_obj_t * unit = make_label(screen, "%", &perf_font_mono_8, COL_MUTED, x,
                                 41, 0, LV_TEXT_ALIGN_LEFT, 0);
    lv_obj_t * sub = make_label(screen, sub_text, &perf_font_mono_8, COL_DIM, x,
                                64, 50, LV_TEXT_ALIGN_LEFT, 0);
    lv_obj_t * bar = make_bar(screen, x, 82, 44, 3);

    if(memory) {
        s_ui.mem_value = value;
        s_ui.mem_unit = unit;
        s_ui.mem_sub = sub;
        s_ui.mem_bar = bar;
        app_obj_set_name(value, "perf_mem_value");
        app_obj_set_name(unit, "perf_mem_unit");
        app_obj_set_name(sub, "perf_mem_sub");
        app_obj_set_name(bar, "perf_mem_bar");
    }
    else {
        s_ui.gpu_value = value;
        s_ui.gpu_unit = unit;
        s_ui.gpu_sub = sub;
        s_ui.gpu_bar = bar;
        app_obj_set_name(value, "perf_gpu_value");
        app_obj_set_name(unit, "perf_gpu_unit");
        app_obj_set_name(sub, "perf_gpu_sub");
        app_obj_set_name(bar, "perf_gpu_bar");
    }
}

static void build_split_landscape(lv_obj_t * screen)
{
    make_vline(screen, 136, 28, 54);
    make_vline(screen, 192, 28, 54);

    build_metric_landscape(screen, true);
    build_metric_landscape(screen, false);
}

static void build_net_landscape(lv_obj_t * screen)
{
    lv_obj_t * label;

    s_ui.net_chart_w = 72;
    s_ui.net_chart_h = PERF_NET_CHART_H;

    label = make_label(screen, "NET", &perf_font_mono_8, COL_MUTED, 252, 24, 16,
                       LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(label, "perf_net_label");
    s_ui.ping = make_label(screen, "PING 15 MS", &perf_font_mono_8, COL_DIM,
                           272, 24, 42, LV_TEXT_ALIGN_RIGHT, 0);
    app_obj_set_name(s_ui.ping, "perf_ping");

    label = make_label(screen, "↓", &perf_font_mono_8, COL_MUTED, 254, 40, 0,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_down_arrow");
    s_ui.down = make_label(screen, "11.9", &perf_font_num_14, COL_INK, 262, 34,
                           30, LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.down, "perf_down");
    label = make_label(screen, "MB/S", &perf_font_mono_8, COL_DIM, 294, 39, 20,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_down_unit");

    label = make_label(screen, "↑", &perf_font_mono_8, COL_ACCENT, 254, 57, 0,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_up_arrow");
    s_ui.up = make_label(screen, "0.7", &perf_font_num_14, COL_INK, 262, 51, 30,
                         LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(s_ui.up, "perf_up");
    label = make_label(screen, "MB/S", &perf_font_mono_8, COL_DIM, 294, 56, 20,
                       LV_TEXT_ALIGN_LEFT, 0);
    app_obj_set_name(label, "perf_up_unit");

    make_vline(screen, 248, 28, 44);

    s_ui.net_canvas = make_canvas(screen, 248, 72, 72, PERF_NET_CHART_H,
                                  s_net_fb, "perf_net_chart");
}

static void build_threads_landscape(lv_obj_t * screen)
{
    lv_obj_t * label;

    s_ui.thread_x = 8;
    s_ui.thread_y = 143;
    s_ui.thread_span = 304;
    s_ui.thread_gap = 4;
    s_ui.thread_bar_h = 12;
    s_ui.thread_max_w = 34;

    make_line(screen, 0, 130, PERF_LAND_W);

    label = make_label(screen, "THREADS", &perf_font_mono_8, COL_MUTED, 8, 134,
                       0, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(label, "perf_threads_label");
    s_ui.peak = make_label(screen, "PEAK 61%", &perf_font_mono_8, COL_DIM, 236,
                           134, 76, LV_TEXT_ALIGN_RIGHT, 1);
    app_obj_set_name(s_ui.peak, "perf_threads_peak");

    for(int i = 0; i < PERF_THREADS; i++) {
        char name[24];
        lv_obj_t * track = lv_obj_create(screen);
        lv_obj_remove_style_all(track);
        lv_obj_set_pos(track, 8 + i * 10, 146);
        lv_obj_set_size(track, 6, 12);
        lv_obj_set_style_bg_color(track, lv_color_hex(COL_LINE_SOFT), 0);
        lv_obj_set_style_bg_opa(track, LV_OPA_COVER, 0);
        app_obj_set_scrollable(track, false);
        snprintf(name, sizeof(name), "perf_thread_%02d", i);
        app_obj_set_name(track, name);
        s_ui.thread_track[i] = track;

        lv_obj_t * fill = lv_obj_create(track);
        lv_obj_remove_style_all(fill);
        lv_obj_set_size(fill, 6, 3);
        lv_obj_align(fill, LV_ALIGN_BOTTOM_MID, 0, 0);
        lv_obj_set_style_bg_color(fill, lv_color_hex(COL_INK), 0);
        lv_obj_set_style_bg_opa(fill, LV_OPA_COVER, 0);
        app_obj_set_scrollable(fill, false);
        s_ui.thread_fill[i] = fill;
    }

    make_line(screen, 0, 156, PERF_LAND_W);
}

static void build_footer_landscape(lv_obj_t * screen)
{
    lv_obj_t * dot = lv_obj_create(screen);

    lv_obj_remove_style_all(dot);
    lv_obj_set_pos(dot, 8, 164);
    lv_obj_set_size(dot, 3, 3);
    lv_obj_set_style_bg_color(dot, lv_color_hex(COL_ACCENT), 0);
    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    app_obj_set_scrollable(dot, false);
    s_ui.pulse = dot;
    app_obj_set_name(dot, "perf_pulse");

    s_ui.state = make_label(screen, "SIM", &perf_font_mono_8, COL_MUTED, 14,
                            161, 32, LV_TEXT_ALIGN_LEFT, 1);
    app_obj_set_name(s_ui.state, "perf_state");

    s_ui.footer_mid =
        make_label(screen, "SIM · 0.3S", &perf_font_mono_8, COL_DIM, 120, 161,
                   80, LV_TEXT_ALIGN_CENTER, 1);
    app_obj_set_name(s_ui.footer_mid, "perf_footer_mid");

    lv_obj_t * right = make_label(screen, "C6/01", &perf_font_mono_8, COL_DIM,
                                  284, 161, 28, LV_TEXT_ALIGN_RIGHT, 1);
    app_obj_set_name(right, "perf_footer_right");
}

static void build_ui(bool landscape)
{
    lv_obj_t * old_screen = s_screen;
    lv_obj_t * screen = lv_obj_create(NULL);

    memset(&s_ui, 0, sizeof(s_ui));

    lv_obj_set_style_bg_color(screen, lv_color_hex(COL_BG), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(screen, 0, 0);
    app_obj_set_scrollable(screen, false);
    app_obj_set_name(screen, "perf_monitor");

    if(landscape) {
        build_status_landscape(screen);
        build_cpu_landscape(screen);
        build_split_landscape(screen);
        build_net_landscape(screen);
        build_threads_landscape(screen);
        build_footer_landscape(screen);
    }
    else {
        build_status(screen);
        build_cpu(screen);
        build_split(screen);
        build_net(screen);
        build_threads(screen);
        build_footer(screen);
    }

    lv_screen_load(screen);
    if(old_screen != NULL) lv_obj_delete(old_screen);
    s_screen = screen;
}

/* ------------------------------------------------------------------ */
/* state rendering                                                    */
/* ------------------------------------------------------------------ */

static void update_state_labels(void)
{
    char middle[24];
    const char * state;
    uint32_t state_color;
    uint32_t dot_color;

    if(s_demo) {
        state = "SIM";
        snprintf(middle, sizeof(middle), "SIM · 0.3S");
        state_color = COL_MUTED;
        dot_color = COL_MUTED;
    }
    else if(s_have_live && s_link_lost) {
        state = "LOST";
        snprintf(middle, sizeof(middle), "USB · LOST");
        state_color = COL_WARN;
        dot_color = COL_WARN;
    }
    else if(s_have_live) {
        state = "LIVE";
        snprintf(middle, sizeof(middle), "USB · %.1fS",
                 s_live_period_ms / 1000.0);
        state_color = COL_ACCENT;
        dot_color = COL_ACCENT;
    }
    else {
        state = "WAIT";
        snprintf(middle, sizeof(middle), "USB · WAIT");
        state_color = COL_MUTED;
        dot_color = COL_MUTED;
    }

    if(s_ui.state != NULL) {
        lv_label_set_text(s_ui.state, state);
        lv_obj_set_style_text_color(s_ui.state, lv_color_hex(state_color), 0);
    }
    if(s_ui.footer_mid != NULL) lv_label_set_text(s_ui.footer_mid, middle);
    if(s_ui.pulse != NULL) {
        lv_obj_set_style_bg_color(s_ui.pulse, lv_color_hex(dot_color), 0);
    }
}

static void update_ui(void)
{
    char text[32];
    unsigned cpu = s_sample.cpu;
    unsigned gpu = s_sample.gpu;
    unsigned mem_percent = 0;
    unsigned mem_total_gb = 0;
    unsigned peak = 0;
    unsigned thread_count;
    size_t peak_index = 0;
    uint32_t cpu_color;

    if(!s_ready) return;
    thread_count = s_sample.thread_count;
    if(thread_count < 1u || thread_count > PERF_THREADS) {
        thread_count = PERF_THREADS;
    }

    cpu_color = cpu >= 90 ? COL_ACCENT : cpu >= 75 ? COL_WARN : COL_INK;
    snprintf(text, sizeof(text), "%02u", cpu);
    lv_label_set_text(s_ui.cpu_value, text);
    if(s_landscape) {
        lv_obj_set_style_text_font(
            s_ui.cpu_value, cpu >= 100 ? &perf_font_num_46 : &perf_font_num_52,
            0);
    }
    lv_obj_set_style_text_color(s_ui.cpu_value, lv_color_hex(cpu_color), 0);
    lv_obj_update_layout(s_ui.cpu_value);
    int cpu_width = lv_obj_get_width(s_ui.cpu_value);
    int cpu_max_width = s_landscape ? 74 : 110;
    if(cpu_width > cpu_max_width) cpu_width = cpu_max_width;
    lv_obj_set_x(s_ui.cpu_unit, lv_obj_get_x(s_ui.cpu_value) + cpu_width + 1);
    snprintf(text, sizeof(text), " · %uT", thread_count);
    lv_label_set_text(s_ui.cpu_meta, text);

    int trend = (int)s_sample.cpu - (int)s_cpu_hist[PERF_HISTORY - 6];
    if(trend > 0) snprintf(text, sizeof(text), "+%d", trend);
    else if(trend < 0)
        snprintf(text, sizeof(text), "-%d", -trend);
    else
        snprintf(text, sizeof(text), "0");
    lv_label_set_text(s_ui.cpu_trend, text);
    lv_obj_set_style_text_color(
        s_ui.cpu_trend, lv_color_hex(trend > 0 ? COL_ACCENT : COL_MUTED), 0);

    if(s_sample.freq_mhz == 0) snprintf(text, sizeof(text), "--");
    else
        snprintf(text, sizeof(text), "%.2f", s_sample.freq_mhz / 1000.0);
    lv_label_set_text(s_ui.cpu_freq, text);

    if(s_sample.temp_c == PERF_TEMP_UNKNOWN) snprintf(text, sizeof(text), "--");
    else
        snprintf(text, sizeof(text), "%d", (int)s_sample.temp_c);
    lv_label_set_text(s_ui.cpu_temp, text);

    if(s_sample.mem_total_mb > 0) {
        mem_percent = (unsigned)(((uint64_t)s_sample.mem_mb * 100u +
                                  s_sample.mem_total_mb / 2u) /
                                 s_sample.mem_total_mb);
        mem_total_gb = (s_sample.mem_total_mb + 512u) / 1024u;
        if(mem_total_gb == 0) mem_total_gb = 1;
        snprintf(text, sizeof(text), "%.1f/%uG", s_sample.mem_mb / 1024.0,
                 mem_total_gb);
    }
    else {
        snprintf(text, sizeof(text), "--");
    }
    lv_label_set_text(s_ui.mem_sub, text);
    snprintf(text, sizeof(text), "%02u", mem_percent);
    lv_label_set_text(s_ui.mem_value, text);
    lv_obj_update_layout(s_ui.mem_value);
    lv_obj_set_x(s_ui.mem_unit, lv_obj_get_x(s_ui.mem_value) +
                                    lv_obj_get_width(s_ui.mem_value) + 1);
    lv_bar_set_value(s_ui.mem_bar, (int32_t)mem_percent, LV_ANIM_OFF);

    if(gpu == PERF_GPU_UNKNOWN) {
        snprintf(text, sizeof(text), "--");
        lv_label_set_text(s_ui.gpu_value, text);
        lv_bar_set_value(s_ui.gpu_bar, 0, LV_ANIM_OFF);
    }
    else {
        snprintf(text, sizeof(text), "%02u", gpu);
        lv_label_set_text(s_ui.gpu_value, text);
        lv_bar_set_value(s_ui.gpu_bar, (int32_t)gpu, LV_ANIM_OFF);
    }
    lv_obj_update_layout(s_ui.gpu_value);
    lv_obj_set_x(s_ui.gpu_unit, lv_obj_get_x(s_ui.gpu_value) +
                                    lv_obj_get_width(s_ui.gpu_value) + 1);
    if(s_sample.gpu_temp_c == PERF_TEMP_UNKNOWN) {
        snprintf(text, sizeof(text), "--");
    }
    else {
        snprintf(text, sizeof(text), "%d°C", (int)s_sample.gpu_temp_c);
    }
    lv_label_set_text(s_ui.gpu_sub, text);

    snprintf(text, sizeof(text), "%.1f", s_sample.down_kib_s / 1024.0);
    lv_label_set_text(s_ui.down, text);
    snprintf(text, sizeof(text), "%.1f", s_sample.up_kib_s / 1024.0);
    lv_label_set_text(s_ui.up, text);

    if(s_sample.ping_ms == PERF_PING_UNKNOWN) {
        snprintf(text, sizeof(text), s_landscape ? "PING --" : "PING -- MS");
    }
    else if(s_landscape || s_sample.ping_ms >= 1000) {
        snprintf(text, sizeof(text), "PING %u", (unsigned)s_sample.ping_ms);
    }
    else {
        snprintf(text, sizeof(text), "PING %u MS", (unsigned)s_sample.ping_ms);
    }
    lv_label_set_text(s_ui.ping, text);

    for(unsigned i = 0; i < thread_count; i++) {
        unsigned value = s_sample.bars[i];
        if(value > peak) {
            peak = value;
            peak_index = (size_t)i;
        }
    }

    int bar_width =
        (s_ui.thread_span - ((int)thread_count - 1) * s_ui.thread_gap) /
        (int)thread_count;
    if(bar_width < 6) bar_width = 6;
    if(bar_width > s_ui.thread_max_w) bar_width = s_ui.thread_max_w;
    int group_width = (int)thread_count * bar_width +
                      ((int)thread_count - 1) * s_ui.thread_gap;
    int start_x = s_ui.thread_x + (s_ui.thread_span - group_width) / 2;

    for(int i = 0; i < PERF_THREADS; i++) {
        bool visible = (unsigned)i < thread_count;
        lv_obj_set_hidden(s_ui.thread_track[i], !visible);
        if(!visible) continue;

        lv_obj_set_pos(s_ui.thread_track[i],
                       start_x + i * (bar_width + s_ui.thread_gap),
                       s_ui.thread_y);
        lv_obj_set_size(s_ui.thread_track[i], bar_width, s_ui.thread_bar_h);
        lv_obj_set_width(s_ui.thread_fill[i], bar_width);
        lv_obj_align(s_ui.thread_fill[i], LV_ALIGN_BOTTOM_MID, 0, 0);

        int height = ((int)s_sample.bars[i] * s_ui.thread_bar_h) / 100;
        if(height < 1) height = 1;
        if(height > s_ui.thread_bar_h) height = s_ui.thread_bar_h;
        lv_obj_set_height(s_ui.thread_fill[i], height);
        lv_obj_set_style_bg_color(s_ui.thread_fill[i],
                                  lv_color_hex(i == (int)peak_index && peak > 0
                                                   ? COL_ACCENT
                                                   : COL_INK),
                                  0);
    }
    snprintf(text, sizeof(text), "PEAK %u%%", peak);
    lv_label_set_text(s_ui.peak, text);

    if(s_sample.hhmm == PERF_TIME_UNKNOWN) {
        snprintf(text, sizeof(text), "--:--");
    }
    else {
        snprintf(text, sizeof(text), "%02u:%02u", s_sample.hhmm / 100u,
                 s_sample.hhmm % 100u);
    }
    lv_label_set_text(s_ui.clock, text);
    lv_label_set_text(s_ui.host,
                      s_sample.host[0] != '\0' ? s_sample.host : "DESKTOP");

    unsigned window_s = 60;
    if(s_live_period_ms > 0) {
        window_s = (unsigned)((PERF_HISTORY * s_live_period_ms + 500u) / 1000u);
        if(window_s < 10) window_s = 10;
        if(window_s > 999) window_s = 999;
    }
    snprintf(text, sizeof(text), "-%uS", window_s);
    lv_label_set_text(s_ui.cpu_axis_start, text);
    if(s_ui.tape_tag != NULL) {
        snprintf(text, sizeof(text), "CPU · %uS", window_s);
        lv_label_set_text(s_ui.tape_tag, text);
    }

    update_state_labels();
    draw_cpu_chart();
    draw_net_chart();
}

static void apply_sample(const perf_sample_t * sample, bool live)
{
    bool first_live = live && !s_have_live;
    uint8_t down = (uint8_t)net_norm(sample->down_kib_s, 40u * 1024u);
    uint8_t up = (uint8_t)net_norm(sample->up_kib_s, 8u * 1024u);

    s_sample = *sample;
    s_last_seq = sample->seq;

    if(first_live) {
        for(int i = 0; i < PERF_HISTORY; i++) {
            s_cpu_hist[i] = sample->cpu;
            s_down_hist[i] = down;
            s_up_hist[i] = up;
        }
    }

    if(live) {
        uint32_t now = lv_tick_get();
        if(s_have_live) {
            uint32_t elapsed = lv_tick_elaps(s_last_live_ms);
            if(elapsed >= 200u && elapsed <= 60000u) {
                s_live_period_ms = elapsed;
            }
        }
        s_demo = false;
        s_have_live = true;
        s_link_lost = false;
        s_last_live_ms = now;
    }

    history_push(s_cpu_hist, sample->cpu);
    history_push(s_down_hist, down);
    history_push(s_up_hist, up);
    update_ui();
}

/* ------------------------------------------------------------------ */
/* demo data                                                          */
/* ------------------------------------------------------------------ */

static void demo_sample(void)
{
    perf_sample_t sample;
    int i;

    perf_sample_init(&sample);
    sample.thread_count = 8;

    s_demo_tick++;
    s_demo_cpu = clamp_int(s_demo_cpu + random_between(-6, 6), 10, 92);
    if(s_demo_tick % 29u == 0u) {
        s_demo_cpu = clamp_int(s_demo_cpu + 22, 35, 98);
    }
    s_demo_gpu = clamp_int(s_demo_gpu + random_between(-5, 5), 4, 88);
    s_demo_down =
        clamp_int(s_demo_down + random_between(-1800, 1800), 1800, 26000);
    s_demo_up = clamp_int(s_demo_up + random_between(-220, 220), 120, 3200);
    s_demo_minutes = (s_demo_minutes + 1u) % (24u * 60u);

    sample.seq = (uint16_t)(++s_demo_seq);
    sample.cpu = (uint8_t)s_demo_cpu;
    sample.gpu = (uint8_t)s_demo_gpu;
    sample.mem_total_mb = 32768u;
    sample.mem_mb = 11200u + (s_demo_tick * 37u) % 1400u;
    sample.freq_mhz = (uint16_t)clamp_int(
        2000 + s_demo_cpu * 30 + random_between(-30, 30), 1200, 6000);
    sample.temp_c = (int16_t)clamp_int(
        38 + s_demo_cpu / 2 + random_between(-2, 2), 30, 100);
    sample.gpu_temp_c = (int16_t)clamp_int(
        41 + s_demo_gpu / 2 + random_between(-2, 2), 30, 100);
    sample.down_kib_s = (uint32_t)s_demo_down;
    sample.up_kib_s = (uint32_t)s_demo_up;
    sample.ping_ms = (uint16_t)random_between(8, 28);
    sample.hhmm =
        (uint16_t)((s_demo_minutes / 60u) * 100u + (s_demo_minutes % 60u));
    memcpy(sample.host, "DESKTOP-01", 11);

    for(i = 0; i < PERF_THREADS; i++) {
        sample.bars[i] =
            (uint8_t)clamp_int(s_demo_cpu + random_between(-30, 30), 1, 100);
    }

    apply_sample(&sample, false);
}

static void seed_history(void)
{
    int cpu = 45;
    int down = 26;
    int up = 10;

    for(int i = 0; i < PERF_HISTORY; i++) {
        cpu = clamp_int(cpu + random_between(-5, 5), 18, 78);
        down = clamp_int(down + random_between(-6, 6), 6, 55);
        up = clamp_int(up + random_between(-4, 4), 2, 28);
        s_cpu_hist[i] = (uint8_t)cpu;
        s_down_hist[i] = (uint8_t)down;
        s_up_hist[i] = (uint8_t)up;
    }
    s_cpu_hist[PERF_HISTORY - 1] = 47;
    for(int i = 54; i < PERF_HISTORY - 1; i++) {
        s_cpu_hist[i] = (uint8_t)(43 + (i - 54));
    }
}

/* ------------------------------------------------------------------ */
/* lifecycle                                                          */
/* ------------------------------------------------------------------ */

static void monitor_timer_cb(lv_timer_t * timer)
{
    (void)timer;

    s_tick++;
    lv_obj_set_style_opa(s_ui.pulse,
                         (s_tick & 1u) != 0 ? LV_OPA_COVER : LV_OPA_20, 0);

    if(s_demo) {
        demo_sample();
        return;
    }

    if(s_have_live && !s_link_lost && lv_tick_elaps(s_last_live_ms) > 5000u) {
        s_link_lost = true;
        update_state_labels();
        printf("[perf_monitor] link lost\n");
        fflush(stdout);
    }
}

void perf_monitor_create(void)
{
    perf_sample_t sample;

    s_ready = false;
    s_tick = 0;
    s_demo = true;
    s_have_live = false;
    s_link_lost = false;
    s_live_period_ms = 300u;
    s_last_seq = 0;
    s_demo_seq = 0;
    s_demo_tick = 0;
    s_demo_cpu = 47;
    s_demo_gpu = 29;
    s_demo_down = 12000;
    s_demo_up = 800;
    s_demo_minutes = 20u * 60u + 48u;

    seed_history();

    lv_display_t * display = lv_display_get_default();
    int32_t width = lv_display_get_horizontal_resolution(display);
    int32_t height = lv_display_get_vertical_resolution(display);
    s_landscape = width > height;
    build_ui(s_landscape);

    perf_sample_init(&sample);
    sample.thread_count = 8;
    sample.seq = 0;
    sample.cpu = 47;
    sample.gpu = 29;
    sample.mem_total_mb = 32768u;
    sample.mem_mb = 11500u;
    sample.freq_mhz = 3480u;
    sample.temp_c = 63;
    sample.gpu_temp_c = 55;
    sample.down_kib_s = 12000u;
    sample.up_kib_s = 800u;
    sample.ping_ms = 15;
    sample.hhmm =
        (uint16_t)((s_demo_minutes / 60u) * 100u + (s_demo_minutes % 60u));
    memcpy(sample.host, "DESKTOP-01", 11);
    for(int i = 0; i < PERF_THREADS; i++) {
        sample.bars[i] =
            (uint8_t)clamp_int(47 + random_between(-30, 30), 1, 100);
    }
    s_sample = sample;

    s_ready = true;
    update_ui();

    if(s_timer == NULL) {
        s_timer = lv_timer_create(monitor_timer_cb, 300, NULL);
    }

    printf("[perf_monitor] created %s %dx%d demo=1\n",
           s_landscape ? "landscape" : "portrait", (int)width, (int)height);
    fflush(stdout);
}

static void set_orientation(bool landscape)
{
    lv_display_t * display;

    if(landscape == s_landscape) return;

    display = lv_display_get_default();
    if(display != NULL) {
        int32_t original_w =
            lv_display_get_original_horizontal_resolution(display);
        int32_t original_h =
            lv_display_get_original_vertical_resolution(display);
        bool original_landscape = original_w > original_h;
        lv_display_rotation_t rotation = landscape == original_landscape
                                             ? LV_DISPLAY_ROTATION_0
                                             : LV_DISPLAY_ROTATION_90;

        lv_display_set_rotation(display, rotation);
    }

    s_landscape = landscape;
    build_ui(landscape);
    update_ui();
    printf("[perf_monitor] layout=%s", landscape ? "landscape" : "portrait");
    fputc('\n', stdout);
    fflush(stdout);
}

perf_parse_result_t perf_monitor_ingest(const char * line, size_t len)
{
    perf_sample_t sample;
    perf_parse_result_t result;

    if(!s_ready) return PERF_PARSE_BAD_FIELD;

    result = perf_protocol_parse(line, len, &sample);
    switch(result) {
        case PERF_PARSE_OK:
            printf("[perf_monitor] live seq=%u cpu=%u freq=%u temp=%d\n",
                   (unsigned)sample.seq, (unsigned)sample.cpu,
                   (unsigned)sample.freq_mhz, (int)sample.temp_c);
            fflush(stdout);
            apply_sample(&sample, true);
            break;
        case PERF_PARSE_HELLO:
            printf("[perf_monitor] hello\n");
            fflush(stdout);
            break;
        case PERF_PARSE_DEMO:
            s_demo = true;
            s_have_live = false;
            s_link_lost = false;
            s_live_period_ms = 300u;
            printf("[perf_monitor] demo mode\n");
            fflush(stdout);
            seed_history();
            update_state_labels();
            demo_sample();
            break;
        case PERF_PARSE_LIVE:
            s_demo = false;
            s_have_live = false;
            s_link_lost = false;
            s_live_period_ms = 300u;
            printf("[perf_monitor] live mode waiting for data\n");
            fflush(stdout);
            update_state_labels();
            break;
        case PERF_PARSE_PING:
            printf("[perf_monitor] ping\n");
            fflush(stdout);
            break;
        case PERF_PARSE_PORTRAIT:
            set_orientation(false);
            break;
        case PERF_PARSE_LANDSCAPE:
            set_orientation(true);
            break;
        case PERF_PARSE_NOT_PERF:
            break;
        default:
            printf("[perf_monitor] frame error=%s\n",
                   perf_parse_result_name(result));
            fflush(stdout);
            break;
    }

    return result;
}

uint16_t perf_monitor_last_seq(void)
{
    return s_last_seq;
}

bool perf_monitor_is_live(void)
{
    return s_have_live && !s_demo;
}

#endif
