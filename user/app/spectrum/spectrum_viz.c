
#include "app.h"
#include "spectrum.h"

#include <math.h>
#include <string.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#define SP_PI         3.14159265358979323846f
#define VIZ_W         SPECTRUM_VIZ_W
#define VIZ_H         SPECTRUM_VIZ_H
#define VIZ_CX        SPECTRUM_VIZ_CX
#define VIZ_CY        SPECTRUM_VIZ_CY
#define STAR_COUNT    260
#define BG_STAR_COUNT 130
#define SHOCK_COUNT   6
#define GLOW_COUNT    4

LV_DRAW_BUF_DEFINE_STATIC(viz_draw_buf, VIZ_W, VIZ_H, LV_COLOR_FORMAT_XRGB8888);

/* LVGL has no radial gradients, so the canvas backdrop's static parts
 * (diagonal gradient, 40/160 px grid, vignette, scanline overlay) are baked
 * into an XRGB buffer, and the four radial glows are added per frame from
 * precomputed alpha masks. */
typedef struct {
    int x;
    int y;
    int radius;
} viz_glow_t;

static const viz_glow_t viz_glows[GLOW_COUNT] = {
    {120, 96, 330},
    {690, 150, 380},
    {400, 660, 430},
    {400, 280, 260},
};

static uint32_t viz_bg_base[VIZ_W * VIZ_H];
static uint8_t viz_glow_masks[GLOW_COUNT][VIZ_W * VIZ_H];
static uint32_t viz_overlay_pixels[VIZ_W * VIZ_H];
static lv_image_dsc_t viz_overlay_dsc;
static int viz_bg_palette = -1;

typedef struct {
    double angle;
    double radius;
    double speed;
    double size;
    uint8_t color;
} viz_star_t;

typedef struct {
    float radius;
    float life;
    uint32_t color;
} viz_shock_t;

typedef struct {
    float x;
    float y;
    float radius;
    float phase;
    float speed;
} viz_bg_star_t;

static lv_obj_t * viz_canvas;
static lv_obj_t * viz_cover_base;
static lv_obj_t * viz_cover_spin;
static lv_obj_t * viz_ring_inner;
static lv_obj_t * viz_ring_outer;
static lv_obj_t * viz_overlay;
static bool viz_ready;
static int viz_last_track = -1;

static viz_star_t viz_stars[STAR_COUNT];
static viz_bg_star_t viz_bg_stars[BG_STAR_COUNT];
static viz_shock_t viz_shocks[SHOCK_COUNT];
static int viz_shock_count;
static uint32_t viz_rng = 911u;
static uint32_t bg_rng = 23u;

static const int cover_sizes[SPECTRUM_MODE_COUNT] = {146, 124, 118,
                                                     88,  78,  118};
static const float cover_speed[SPECTRUM_MODE_COUNT] = {0.28f,  -0.20f, 0.16f,
                                                       -0.30f, 0.24f,  0.32f};

static float viz_clamp(float value, float lo, float hi)
{
    return value < lo ? lo : value > hi ? hi : value;
}

static double viz_rand(void)
{
    viz_rng += 0x6D2B79F5u;
    uint32_t t = viz_rng;
    t = (t ^ (t >> 15)) * (t | 1u);
    t ^= t + (t ^ (t >> 7)) * (t | 61u);
    return (double)((t ^ (t >> 14)) >> 0) / 4294967296.0;
}

static float bg_rand(void)
{
    bg_rng += 0x6D2B79F5u;
    uint32_t t = bg_rng;
    t = (t ^ (t >> 15)) * (t | 1u);
    t ^= t + (t ^ (t >> 7)) * (t | 61u);
    return (float)((t ^ (t >> 14)) >> 0) / 4294967296.0f;
}

static float band_at(const float * values, float f)
{
    float x = viz_clamp(f, 0.0f, 1.0f) * (float)(SPECTRUM_BAND_COUNT - 1);
    int i = (int)x;
    float t = x - (float)i;
    int j = i + 1 < SPECTRUM_BAND_COUNT ? i + 1 : SPECTRUM_BAND_COUNT - 1;
    return values[i] + (values[j] - values[i]) * t;
}

static void draw_line(lv_layer_t * layer, int x1, int y1, int x2, int y2,
                      uint32_t color, int width, int opa)
{
    lv_draw_line_dsc_t dsc;
    lv_draw_line_dsc_init(&dsc);
    dsc.color = lv_color_hex(color);
    dsc.width = width;
    dsc.opa = (lv_opa_t)opa;
    dsc.round_start = 1;
    dsc.round_end = 1;
    dsc.p1.x = x1;
    dsc.p1.y = y1;
    dsc.p2.x = x2;
    dsc.p2.y = y2;
    lv_draw_line(layer, &dsc);
}

static void draw_line_caps(lv_layer_t * layer, int x1, int y1, int x2, int y2,
                           uint32_t color, int width, int opa, int round_start,
                           int round_end)
{
    lv_draw_line_dsc_t dsc;
    lv_draw_line_dsc_init(&dsc);
    dsc.color = lv_color_hex(color);
    dsc.width = width;
    dsc.opa = (lv_opa_t)opa;
    dsc.round_start = round_start;
    dsc.round_end = round_end;
    dsc.p1.x = x1;
    dsc.p1.y = y1;
    dsc.p2.x = x2;
    dsc.p2.y = y2;
    lv_draw_line(layer, &dsc);
}

static void draw_rect(lv_layer_t * layer, int x, int y, int w, int h,
                      int radius, uint32_t color, int opa)
{
    lv_draw_rect_dsc_t dsc;
    lv_draw_rect_dsc_init(&dsc);
    dsc.bg_color = lv_color_hex(color);
    dsc.bg_opa = (lv_opa_t)opa;
    dsc.radius = radius;
    lv_area_t area = {x, y, x + w - 1, y + h - 1};
    lv_draw_rect(layer, &dsc, &area);
}

static void draw_circle(lv_layer_t * layer, int cx, int cy, int radius,
                        uint32_t color, int opa)
{
    draw_rect(layer, cx - radius, cy - radius, radius * 2, radius * 2,
              LV_RADIUS_CIRCLE, color, opa);
}

static void draw_ring(lv_layer_t * layer, int cx, int cy, int radius, int width,
                      uint32_t color, int opa)
{
    lv_draw_arc_dsc_t dsc;
    lv_draw_arc_dsc_init(&dsc);
    dsc.center.x = cx;
    dsc.center.y = cy;
    dsc.radius = (uint16_t)radius;
    dsc.start_angle = 0;
    dsc.end_angle = 359;
    dsc.width = width;
    dsc.color = lv_color_hex(color);
    dsc.opa = (lv_opa_t)opa;
    dsc.rounded = 0;
    lv_draw_arc(layer, &dsc);
}

static void draw_arc_segment(lv_layer_t * layer, int cx, int cy, int radius,
                             int start, int end, int width, uint32_t color,
                             int opa)
{
    lv_draw_arc_dsc_t dsc;
    lv_draw_arc_dsc_init(&dsc);
    dsc.center.x = cx;
    dsc.center.y = cy;
    dsc.radius = (uint16_t)radius;
    dsc.start_angle = start;
    dsc.end_angle = end;
    dsc.width = width;
    dsc.color = lv_color_hex(color);
    dsc.opa = (lv_opa_t)opa;
    dsc.rounded = 0;
    lv_draw_arc(layer, &dsc);
}

static void draw_dashed_circle(lv_layer_t * layer, int cx, int cy, int radius,
                               uint32_t color, int opa, int dash, int gap,
                               float rotation)
{
    lv_point_precise_t points[97];
    for(int i = 0; i <= 96; i++) {
        float a = rotation + (float)i * (SP_PI * 2.0f / 96.0f);
        points[i].x = cx + (int)(cosf(a) * (float)radius);
        points[i].y = cy + (int)(sinf(a) * (float)radius);
    }

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 5
    /* 9.5 replaced the two-point line with a polyline. */
    lv_draw_line_dsc_t dsc;
    lv_draw_line_dsc_init(&dsc);
    dsc.color = lv_color_hex(color);
    dsc.width = 1;
    dsc.opa = (lv_opa_t)opa;
    dsc.points = points;
    dsc.point_cnt = 97;
    dsc.dash_width = dash;
    dsc.dash_gap = gap;
    lv_draw_line(layer, &dsc);
#else
    /* 9.4 draws one segment at a time; the dash pattern is recreated by
     * walking the ring and emitting only the "on" spans. */
    for(int i = 0; i < 97; i++) {
        int span = i % (dash + gap);
        if(span >= dash) continue;
        lv_draw_line_dsc_t dsc;
        lv_draw_line_dsc_init(&dsc);
        dsc.color = lv_color_hex(color);
        dsc.width = 1;
        dsc.opa = (lv_opa_t)opa;
        dsc.p1 = points[i];
        dsc.p2 = points[(i + 1) % 97];
        lv_draw_line(layer, &dsc);
    }
#endif
}

static void viz_apply_white(uint32_t * pixel, float alpha)
{
    uint32_t c = *pixel;
    int r = (int)(c >> 16) & 0xFF;
    int g = (int)(c >> 8) & 0xFF;
    int b = (int)c & 0xFF;
    r = (int)((float)r * (1.0f - alpha) + 255.0f * alpha + 0.5f);
    g = (int)((float)g * (1.0f - alpha) + 255.0f * alpha + 0.5f);
    b = (int)((float)b * (1.0f - alpha) + 255.0f * alpha + 0.5f);
    *pixel = 0x00FFFFFFu & ((uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b);
}

static void viz_apply_black(uint32_t * pixel, float alpha)
{
    uint32_t c = *pixel;
    int r = (int)((float)((c >> 16) & 0xFF) * (1.0f - alpha) + 0.5f);
    int g = (int)((float)((c >> 8) & 0xFF) * (1.0f - alpha) + 0.5f);
    int b = (int)((float)(c & 0xFF) * (1.0f - alpha) + 0.5f);
    *pixel = 0x00FFFFFFu & ((uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b);
}

static uint32_t viz_mix_rgb(uint32_t first, uint32_t second, float t)
{
    if(t < 0.0f) t = 0.0f;
    if(t > 1.0f) t = 1.0f;
    int ar = (int)(first >> 16) & 0xFF;
    int ag = (int)(first >> 8) & 0xFF;
    int ab = (int)first & 0xFF;
    int br = (int)(second >> 16) & 0xFF;
    int bg = (int)(second >> 8) & 0xFF;
    int bb = (int)second & 0xFF;
    int r = (int)((float)ar + ((float)br - (float)ar) * t + 0.5f);
    int g = (int)((float)ag + ((float)bg - (float)ag) * t + 0.5f);
    int b = (int)((float)ab + ((float)bb - (float)ab) * t + 0.5f);
    return ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b;
}

static float viz_css_linear_alpha(float f)
{
    if(f <= 0.0f) return 0.88f;
    if(f < 0.16f) return 0.88f + (0.16f - 0.88f) * (f / 0.16f);
    if(f < 0.30f) return 0.16f * (1.0f - (f - 0.16f) / 0.14f);
    if(f < 0.82f) return 0.0f;
    if(f < 1.0f) return 0.82f * ((f - 0.82f) / 0.18f);
    return 0.82f;
}

static void viz_init_glow_masks(void)
{
    memset(viz_glow_masks, 0, sizeof(viz_glow_masks));
    for(int g = 0; g < GLOW_COUNT; g++) {
        const viz_glow_t * glow = &viz_glows[g];
        int x0 = glow->x - glow->radius;
        int y0 = glow->y - glow->radius;
        int x1 = glow->x + glow->radius;
        int y1 = glow->y + glow->radius;
        if(x0 < 0) x0 = 0;
        if(y0 < 0) y0 = 0;
        if(x1 >= VIZ_W) x1 = VIZ_W - 1;
        if(y1 >= VIZ_H) y1 = VIZ_H - 1;
        for(int y = y0; y <= y1; y++) {
            for(int x = x0; x <= x1; x++) {
                float dx = (float)(x - glow->x);
                float dy = (float)(y - glow->y);
                float t = sqrtf(dx * dx + dy * dy) / (float)glow->radius;
                if(t >= 1.0f) continue;
                float profile = t < 0.45f
                                    ? 1.0f - 0.66f * (t / 0.45f)
                                    : 0.34f * (1.0f - (t - 0.45f) / 0.55f);
                int mask = (int)(profile * 255.0f + 0.5f);
                if(mask < 0) mask = 0;
                if(mask > 255) mask = 255;
                viz_glow_masks[g][y * VIZ_W + x] = (uint8_t)mask;
            }
        }
    }
}

static void viz_build_base(const spectrum_palette_t * pal)
{
    const float vx = 320.0f;
    const float vy = 600.0f;
    const float vv = vx * vx + vy * vy;
    for(int y = 0; y < VIZ_H; y++) {
        for(int x = 0; x < VIZ_W; x++) {
            float t = ((float)x * vx + (float)y * vy) / vv;
            if(t < 0.0f) t = 0.0f;
            if(t > 1.0f) t = 1.0f;
            viz_bg_base[y * VIZ_W + x] =
                t < 0.5f ? viz_mix_rgb(pal->bg1, pal->bg0, t * 2.0f)
                         : viz_mix_rgb(pal->bg0, 0x010207, (t - 0.5f) * 2.0f);
        }
    }

    for(int x = 0; x < VIZ_W; x += 40) {
        for(int y = 0; y < VIZ_H; y++)
            viz_apply_white(&viz_bg_base[y * VIZ_W + x], 0.026f);
    }
    for(int y = 0; y < VIZ_H; y += 40) {
        for(int x = 0; x < VIZ_W; x++)
            viz_apply_white(&viz_bg_base[y * VIZ_W + x], 0.026f);
    }
    for(int x = 0; x < VIZ_W; x += 160) {
        for(int y = 0; y < VIZ_H; y++)
            viz_apply_white(&viz_bg_base[y * VIZ_W + x], 0.045f);
    }
    for(int y = 0; y < VIZ_H; y += 160) {
        for(int x = 0; x < VIZ_W; x++)
            viz_apply_white(&viz_bg_base[y * VIZ_W + x], 0.045f);
    }

    for(int y = 0; y < VIZ_H; y++) {
        for(int x = 0; x < VIZ_W; x++) {
            float dx = (float)(x - 400);
            float dy = (float)(y - 288);
            float t = (sqrtf(dx * dx + dy * dy) - 120.0f) / 400.0f;
            if(t <= 0.0f) continue;
            if(t > 1.0f) t = 1.0f;
            float alpha = t < 0.62f ? 0.16f * (t / 0.62f)
                                    : 0.16f + 0.46f * ((t - 0.62f) / 0.38f);
            viz_apply_black(&viz_bg_base[y * VIZ_W + x], alpha);
        }
    }
}

static void viz_build_overlay(void)
{
    const float radius = sqrtf(400.0f * 400.0f + 330.0f * 330.0f);
    for(int y = 0; y < VIZ_H; y++) {
        float a_lin = viz_css_linear_alpha((float)y / (float)VIZ_H);
        for(int x = 0; x < VIZ_W; x++) {
            float dx = (float)(x - 400);
            float dy = (float)(y - 270);
            float t = sqrtf(dx * dx + dy * dy) / radius;
            float a_rad;
            if(t <= 0.38f) a_rad = 0.0f;
            else if(t >= 1.0f)
                a_rad = 0.42f;
            else
                a_rad = 0.42f * (t - 0.38f) / 0.62f;

            float scan = (y % 3 == 0) ? 0.0143f : 0.0f;
            float a_vig = a_lin + a_rad * (1.0f - a_lin);
            float out_a = a_vig + scan * (1.0f - a_vig);
            float pr = 2.0f * a_lin + 255.0f * scan * (1.0f - a_vig);
            float pg = 6.0f * a_lin + 255.0f * scan * (1.0f - a_vig);
            float pb = 15.0f * a_lin + 255.0f * scan * (1.0f - a_vig);
            uint32_t pixel = 0;
            if(out_a > 0.0001f) {
                int r = (int)(pr / out_a + 0.5f);
                int g = (int)(pg / out_a + 0.5f);
                int b = (int)(pb / out_a + 0.5f);
                int a = (int)(out_a * 255.0f + 0.5f);
                if(r > 255) r = 255;
                if(g > 255) g = 255;
                if(b > 255) b = 255;
                if(a > 255) a = 255;
                pixel = ((uint32_t)a << 24) | ((uint32_t)r << 16) |
                        ((uint32_t)g << 8) | (uint32_t)b;
            }
            viz_overlay_pixels[y * VIZ_W + x] = pixel;
        }
    }
}

static void viz_prepare_backdrop(const spectrum_palette_t * pal)
{
    if(viz_bg_palette != spectrum_state.palette_index) {
        viz_build_base(pal);
        viz_bg_palette = spectrum_state.palette_index;
    }

    uint32_t * dst = (uint32_t *)viz_draw_buf.data;
    memcpy(dst, viz_bg_base, sizeof(viz_bg_base));

    float beat = spectrum_sim.beat_pulse;
    float drop = spectrum_sim.drop;
    float alpha[GLOW_COUNT] = {
        0.10f + beat * 0.05f + drop * 0.06f,
        0.10f + beat * 0.04f,
        0.05f + drop * 0.05f,
        0.028f + beat * 0.02f,
    };
    uint32_t colors[GLOW_COUNT] = {pal->a, pal->b, pal->c, pal->a};

    for(int g = 0; g < GLOW_COUNT; g++) {
        const viz_glow_t * glow = &viz_glows[g];
        int x0 = glow->x - glow->radius;
        int y0 = glow->y - glow->radius;
        int x1 = glow->x + glow->radius;
        int y1 = glow->y + glow->radius;
        if(x0 < 0) x0 = 0;
        if(y0 < 0) y0 = 0;
        if(x1 >= VIZ_W) x1 = VIZ_W - 1;
        if(y1 >= VIZ_H) y1 = VIZ_H - 1;
        int cr = (int)(colors[g] >> 16) & 0xFF;
        int cg = (int)(colors[g] >> 8) & 0xFF;
        int cb = (int)colors[g] & 0xFF;
        uint8_t add_r[256];
        uint8_t add_g[256];
        uint8_t add_b[256];
        for(int m = 0; m < 256; m++) {
            float k = (float)m / 255.0f * alpha[g];
            add_r[m] = (uint8_t)((float)cr * k + 0.5f);
            add_g[m] = (uint8_t)((float)cg * k + 0.5f);
            add_b[m] = (uint8_t)((float)cb * k + 0.5f);
        }
        for(int y = y0; y <= y1; y++) {
            const uint8_t * mask_row = &viz_glow_masks[g][y * VIZ_W];
            uint32_t * row = &dst[y * VIZ_W];
            for(int x = x0; x <= x1; x++) {
                uint8_t m = mask_row[x];
                if(m == 0) continue;
                uint32_t c = row[x];
                int r = (int)((c >> 16) & 0xFF) + add_r[m];
                int gg = (int)((c >> 8) & 0xFF) + add_g[m];
                int b = (int)(c & 0xFF) + add_b[m];
                if(r > 255) r = 255;
                if(gg > 255) gg = 255;
                if(b > 255) b = 255;
                row[x] =
                    ((uint32_t)r << 16) | ((uint32_t)gg << 8) | (uint32_t)b;
            }
        }
    }
}

static void viz_create_overlay(lv_obj_t * parent)
{
    viz_build_overlay();
    memset(&viz_overlay_dsc, 0, sizeof(viz_overlay_dsc));
    viz_overlay_dsc.header.magic = LV_IMAGE_HEADER_MAGIC;
    viz_overlay_dsc.header.cf = LV_COLOR_FORMAT_ARGB8888;
    viz_overlay_dsc.header.w = VIZ_W;
    viz_overlay_dsc.header.h = VIZ_H;
    viz_overlay_dsc.header.stride = VIZ_W * 4;
    viz_overlay_dsc.data_size = sizeof(viz_overlay_pixels);
    viz_overlay_dsc.data = (const uint8_t *)viz_overlay_pixels;

    viz_overlay = lv_image_create(parent);
    lv_image_set_src(viz_overlay, &viz_overlay_dsc);
    lv_obj_set_pos(viz_overlay, 0, 0);
    lv_obj_set_size(viz_overlay, VIZ_W, VIZ_H);
    app_obj_set_clickable(viz_overlay, false);
    app_obj_set_scrollable(viz_overlay, false);
}

static void init_visuals(void)
{
    viz_rng = 911u;
    for(int i = 0; i < STAR_COUNT; i++) {
        viz_stars[i].angle = viz_rand() * SP_PI * 2.0;
        viz_stars[i].radius = 12.0 + viz_rand() * 212.0;
        viz_stars[i].speed = 0.4 + viz_rand() * 1.6;
        viz_stars[i].size = 0.5 + viz_rand() * 1.6;
        double color_pick = viz_rand();
        viz_stars[i].color = color_pick < 0.25f ? 2 : color_pick < 0.6f ? 0 : 1;
    }
    bg_rng = 23u;
    for(int i = 0; i < BG_STAR_COUNT; i++) {
        viz_bg_stars[i].x = bg_rand() * (float)VIZ_W;
        viz_bg_stars[i].y = bg_rand() * (float)VIZ_H;
        viz_bg_stars[i].radius = 0.4f + bg_rand() * 1.5f;
        viz_bg_stars[i].phase = bg_rand() * SP_PI * 2.0f;
        viz_bg_stars[i].speed = 0.6f + bg_rand() * 2.0f;
    }
    viz_shock_count = 0;
    viz_init_glow_masks();
}

static void draw_background(lv_layer_t * layer, const spectrum_palette_t * pal)
{
    for(int i = 0; i < BG_STAR_COUNT; i++) {
        viz_bg_star_t * star = &viz_bg_stars[i];
        float tw = 0.18f +
                   0.55f * (0.5f + 0.5f * sinf(spectrum_sim.time * star->speed +
                                               star->phase));
        int alpha = (int)(tw * (0.35f + spectrum_sim.high) * 255.0f);
        draw_circle(layer, (int)star->x, (int)star->y,
                    star->radius < 1.0f ? 1 : 2,
                    (i % 5 == 0) ? pal->soft : 0xFFFFFF, alpha);
    }

    draw_line(layer, 196, VIZ_CY, 604, VIZ_CY, pal->dim, 1, 18);
    draw_line(layer, VIZ_CX, 88, VIZ_CX, 456, pal->dim, 1, 14);

    for(int r = 0; r < 4; r++) {
        int radius = 64 + r * 48;
        draw_ring(layer, VIZ_CX, VIZ_CY, radius, 1, pal->dim, 26);
    }

    for(int i = 0; i < 72; i++) {
        float a =
            -spectrum_sim.time * 0.04f + (float)i * (SP_PI * 2.0f / 72.0f);
        int r0 = 220;
        int r1 = (i % 6 == 0) ? 227 : 223;
        draw_line(layer, VIZ_CX + (int)(cosf(a) * r0),
                  VIZ_CY + (int)(sinf(a) * r0), VIZ_CX + (int)(cosf(a) * r1),
                  VIZ_CY + (int)(sinf(a) * r1), pal->dim, 1,
                  (i % 6 == 0) ? 56 : 23);
    }
}

static void viz_add_halo(const spectrum_palette_t * pal, int size)
{
    const lv_image_dsc_t * glow = spectrum_glow_asset();
    int gw = glow->header.w;
    int gh = glow->header.h;
    const uint32_t * src = (const uint32_t *)glow->data;
    int radius = (int)((float)size * 0.95f);
    if(radius <= 0) return;
    int cr = (int)(pal->b >> 16) & 0xFF;
    int cg = (int)(pal->b >> 8) & 0xFF;
    int cb = (int)pal->b & 0xFF;
    float alpha = 0.16f + (float)spectrum_sim.beat_pulse * 0.10f;
    uint32_t * dst = (uint32_t *)viz_draw_buf.data;

    for(int y = VIZ_CY - radius; y < VIZ_CY + radius; y++) {
        if(y < 0 || y >= VIZ_H) continue;
        float gy = ((float)(y + 0.5f) - (float)(VIZ_CY - radius)) /
                   (float)(2 * radius) * (float)(gh - 1);
        int y0 = (int)gy;
        int y1 = y0 + 1 < gh ? y0 + 1 : gh - 1;
        float fy = gy - (float)y0;
        uint32_t * row = &dst[y * VIZ_W];
        for(int x = VIZ_CX - radius; x < VIZ_CX + radius; x++) {
            if(x < 0 || x >= VIZ_W) continue;
            float gx = ((float)(x + 0.5f) - (float)(VIZ_CX - radius)) /
                       (float)(2 * radius) * (float)(gw - 1);
            int x0 = (int)gx;
            int x1 = x0 + 1 < gw ? x0 + 1 : gw - 1;
            float fx = gx - (float)x0;
            float a00 = (float)((src[y0 * gw + x0] >> 24) & 0xFF);
            float a10 = (float)((src[y0 * gw + x1] >> 24) & 0xFF);
            float a01 = (float)((src[y1 * gw + x0] >> 24) & 0xFF);
            float a11 = (float)((src[y1 * gw + x1] >> 24) & 0xFF);
            float a = (a00 * (1.0f - fx) + a10 * fx) * (1.0f - fy) +
                      (a01 * (1.0f - fx) + a11 * fx) * fy;
            float k = a / 255.0f * alpha;
            if(k <= 0.0f) continue;
            uint32_t c = row[x];
            int r = (int)((c >> 16) & 0xFF) + (int)((float)cr * k + 0.5f);
            int g = (int)((c >> 8) & 0xFF) + (int)((float)cg * k + 0.5f);
            int b = (int)(c & 0xFF) + (int)((float)cb * k + 0.5f);
            if(r > 255) r = 255;
            if(g > 255) g = 255;
            if(b > 255) b = 255;
            row[x] = ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b;
        }
    }
}

static void draw_orbit(lv_layer_t * layer, const spectrum_palette_t * pal)
{
    const int n = 64;
    const int inner = 124;
    const int max_len = 76;

    for(int k = 0; k < n; k++) {
        float f = (float)k / (float)(n - 1);
        float v =
            powf(viz_clamp(band_at(spectrum_sim.bands, f), 0.0f, 1.0f), 1.3f);
        float a = -SP_PI / 2.0f + (float)k * (SP_PI * 2.0f / (float)n);
        float ca = cosf(a);
        float sa = sinf(a);
        int x0 = VIZ_CX + (int)(ca * inner);
        int y0 = VIZ_CY + (int)(sa * inner);
        int x1 = VIZ_CX + (int)(ca * (inner + 8 + v * max_len));
        int y1 = VIZ_CY + (int)(sa * (inner + 8 + v * max_len));
        uint32_t color = (k % 4 == 0) ? pal->c : (k % 3 == 0) ? pal->b : pal->a;

        draw_line(layer, x0, y0, x1, y1, color, 9, 25 + (int)(v * 46.0f));
        draw_line(layer, x0, y0, x1, y1, color, 2, 115 + (int)(v * 127.0f));
    }

    draw_ring(layer, VIZ_CX, VIZ_CY, 214, 1, pal->a, 76);

    for(int k = 0; k < 3; k++) {
        float a = spectrum_sim.time * (0.35f + (float)k * 0.06f) +
                  (float)k * (SP_PI * 2.0f / 3.0f);
        int ox = VIZ_CX + (int)(cosf(a) * 214.0f);
        int oy = VIZ_CY + (int)(sinf(a) * 214.0f);
        uint32_t col = (k == 1) ? pal->c : pal->a;
        draw_ring(layer, ox, oy, 6, 9, col, 40);
        draw_ring(layer, ox, oy, 10, 6, col, 24);
        draw_circle(layer, ox, oy, 2, 0xFFFFFF, 255);
    }

    int wave_r = inner - 14 + (int)(spectrum_sim.beat_phase * 44.0f);
    draw_ring(layer, VIZ_CX, VIZ_CY, wave_r, 1, pal->c,
              (int)((1.0f - spectrum_sim.beat_phase) * 70.0f));
}

static void draw_dual(lv_layer_t * layer, const spectrum_palette_t * pal)
{
    float outer_rot = spectrum_sim.time * 0.10f;
    float inner_rot = -spectrum_sim.time * 0.17f;

    for(int k = 0; k < 64; k++) {
        float f = (float)k / 63.0f;
        float v = viz_clamp(band_at(spectrum_sim.bands, f), 0.0f, 1.0f);
        float a = -SP_PI / 2.0f + (float)k * (SP_PI * 2.0f / 64.0f) + outer_rot;
        int x0 = VIZ_CX + (int)(cosf(a) * 190.0f);
        int y0 = VIZ_CY + (int)(sinf(a) * 190.0f);
        int x1 = VIZ_CX + (int)(cosf(a) * (190.0f + 10.0f + v * 38.0f));
        int y1 = VIZ_CY + (int)(sinf(a) * (190.0f + 10.0f + v * 38.0f));
        uint32_t color = (k % 5 == 0) ? pal->c : pal->a;
        draw_line(layer, x0, y0, x1, y1, color, 2, 70 + (int)(v * 150.0f));
    }

    for(int k = 0; k < 48; k++) {
        float f = (float)k / 47.0f;
        float v = viz_clamp(band_at(spectrum_sim.bands, 1.0f - f), 0.0f, 1.0f);
        float a = -SP_PI / 2.0f + (float)k * (SP_PI * 2.0f / 48.0f) + inner_rot;
        int x0 = VIZ_CX + (int)(cosf(a) * 126.0f);
        int y0 = VIZ_CY + (int)(sinf(a) * 126.0f);
        int x1 = VIZ_CX + (int)(cosf(a) * (126.0f - 6.0f - v * 44.0f));
        int y1 = VIZ_CY + (int)(sinf(a) * (126.0f - 6.0f - v * 44.0f));
        uint32_t color = (k % 4 == 0) ? pal->c : pal->b;
        draw_line(layer, x0, y0, x1, y1, color, 2, 82 + (int)(v * 140.0f));
    }

    draw_dashed_circle(layer, VIZ_CX, VIZ_CY, 170, pal->dim, 76, 1, 7, 0.0f);
    for(int i = 0; i < 6; i++) {
        float a = outer_rot * 2.0f + (float)i * (SP_PI * 2.0f / 6.0f);
        draw_line(layer, VIZ_CX + (int)(cosf(a) * 136.0f),
                  VIZ_CY + (int)(sinf(a) * 136.0f),
                  VIZ_CX + (int)(cosf(a) * 184.0f),
                  VIZ_CY + (int)(sinf(a) * 184.0f), pal->a, 1, 30);
    }
}

static void draw_radial(lv_layer_t * layer, const spectrum_palette_t * pal)
{
    const int n = 72;
    const int inner = 102;
    for(int k = 0; k < n; k++) {
        float f = (float)k / (float)(n - 1);
        float v =
            powf(viz_clamp(band_at(spectrum_sim.bands, f), 0.0f, 1.0f), 1.2f);
        float peak = viz_clamp(band_at(spectrum_sim.peaks, f), 0.0f, 1.0f);
        float a = -SP_PI / 2.0f + (float)k * (SP_PI * 2.0f / (float)n);
        float ca = cosf(a);
        float sa = sinf(a);
        float len = 12.0f + v * 118.0f;
        const float stops[7] = {0.0f,        1.0f / 6.0f, 2.0f / 6.0f,
                                3.0f / 6.0f, 4.0f / 6.0f, 5.0f / 6.0f,
                                1.0f};
        for(int seg = 0; seg < 6; seg++) {
            float mid = (stops[seg] + stops[seg + 1]) * 0.5f;
            uint32_t color =
                mid < 0.6f ? spectrum_mix(pal->b, pal->a, mid / 0.6f)
                           : spectrum_mix(pal->a, pal->c, (mid - 0.6f) / 0.4f);
            float r0 = inner + len * stops[seg];
            float r1 = inner + len * stops[seg + 1];
            draw_line_caps(layer, VIZ_CX + (int)(ca * r0),
                           VIZ_CY + (int)(sa * r0), VIZ_CX + (int)(ca * r1),
                           VIZ_CY + (int)(sa * r1), color, 3, LV_OPA_COVER, 0,
                           seg == 5 ? 1 : 0);
        }

        float peak_len = powf(peak, 1.2f) * 118.0f;
        int px = VIZ_CX + (int)(ca * (inner + 12.0f + peak_len + 5.0f));
        int py = VIZ_CY + (int)(sa * (inner + 12.0f + peak_len + 5.0f));
        draw_circle(layer, px, py, 1, pal->c, 230);
    }

    draw_ring(layer, VIZ_CX, VIZ_CY, 244, 1, pal->dim, 46);
    draw_ring(layer, VIZ_CX, VIZ_CY,
              78 + (int)(spectrum_sim.beat_phase * 32.0f), 1, pal->a,
              (int)((1.0f - spectrum_sim.beat_phase) * 76.0f));
}

static void draw_spiral(lv_layer_t * layer, const spectrum_palette_t * pal)
{
    const int nodes = 240;
    int prev_x = 0;
    int prev_y = 0;
    for(int i = 0; i < nodes; i++) {
        float f = (float)i / (float)(nodes - 1);
        float radius = 34.0f + f * 224.0f;
        float a = f * SP_PI * 2.0f * 3.4f + spectrum_sim.time * 0.14f;
        int x = VIZ_CX + (int)(cosf(a) * radius);
        int y = VIZ_CY + (int)(sinf(a) * radius);
        float v = viz_clamp(band_at(spectrum_sim.bands, f), 0.0f, 1.0f);
        uint32_t color = f < 0.45f ? pal->b : (f < 0.8f ? pal->a : pal->c);
        if(i > 0) {
            draw_line(layer, prev_x, prev_y, x, y, color, 1,
                      20 + (int)(v * 41.0f));
        }
        if(i % 2 == 0) {
            int size = 1 + (int)(v * 2.0f);
            draw_circle(layer, x, y, size, color, 64 + (int)(v * 178.0f));
        }
        if(i % 5 == 0) {
            draw_ring(layer, x, y, 5 + (int)(v * 8.0f), 1, color,
                      64 + (int)(v * 77.0f));
        }
        prev_x = x;
        prev_y = y;
    }
    draw_ring(layer, VIZ_CX, VIZ_CY, 248, 1, pal->dim, 33);
}

static void draw_sonar(lv_layer_t * layer, const spectrum_palette_t * pal)
{
    const int radius = 224;
    const float sweep = spectrum_sim.time * 0.75f;

    for(int k = 0; k < 26; k++) {
        float a = sweep - (float)k * 0.017f;
        int opa = (int)((1.0f - (float)k / 26.0f) * 40.0f);
        draw_line(layer, VIZ_CX, VIZ_CY, VIZ_CX + (int)(cosf(a) * radius),
                  VIZ_CY + (int)(sinf(a) * radius), pal->a, k == 0 ? 2 : 1,
                  opa);
    }

    for(int i = 0; i < 20; i++) {
        float f = (float)i / 19.0f;
        float v = viz_clamp(band_at(spectrum_sim.bands, f), 0.0f, 1.0f);
        float a =
            (float)i * (SP_PI * 2.0f / 20.0f) + sinf((float)i * 2.1f) * 0.22f;
        int r = 54 + (int)(v * 168.0f);
        int x = VIZ_CX + (int)(cosf(a) * r);
        int y = VIZ_CY + (int)(sinf(a) * r);
        uint32_t color = (i % 3 == 0) ? pal->c : pal->a;
        draw_ring(layer, x, y, 8 + (int)(v * 8.0f), 1, color,
                  40 + (int)(v * 70.0f));
        draw_ring(layer, x, y, 13 + (int)(v * 10.0f), 1, color,
                  18 + (int)(v * 40.0f));
        draw_circle(layer, x, y, 2 + (int)(v * 2.0f), color,
                    128 + (int)(v * 127.0f));
        draw_arc_segment(layer, VIZ_CX, VIZ_CY, r,
                         (int)((a - 0.18f) * 57.29578f) % 360,
                         (int)((a + 0.18f) * 57.29578f) % 360, 1, pal->a,
                         26 + (int)(v * 38.0f));
    }

    draw_line(layer, VIZ_CX, VIZ_CY, VIZ_CX + (int)(cosf(sweep) * radius),
              VIZ_CY + (int)(sinf(sweep) * radius), pal->a, 2, 89);
}

static void draw_stars(lv_layer_t * layer, const spectrum_palette_t * pal,
                       double dt)
{
    double warp =
        0.55 + spectrum_sim.energy * 2.2 + spectrum_sim.beat_pulse * 0.7;

    if(spectrum_sim.just_beat && viz_shock_count < SHOCK_COUNT) {
        viz_shocks[viz_shock_count].radius = 70.0f;
        viz_shocks[viz_shock_count].life = 1.0f;
        viz_shocks[viz_shock_count].color = pal->c;
        viz_shock_count++;
    }

    for(int i = 0; i < STAR_COUNT; i++) {
        viz_star_t * star = &viz_stars[i];
        double previous = star->radius;
        star->radius += dt * (28.0 + star->speed * 96.0) * warp;
        star->angle += dt * 0.1 * ((i % 2) ? 1.0 : -1.0);
        if(star->radius > 220.0f) {
            star->radius = 12.0f + viz_rand() * 20.0f;
            star->angle = viz_rand() * SP_PI * 2.0f;
        }
        double ca = cos(star->angle);
        double sa = sin(star->angle);
        int x0 = VIZ_CX + (int)(ca * previous);
        int y0 = VIZ_CY + (int)(sa * previous);
        int x1 = VIZ_CX + (int)(ca * star->radius);
        int y1 = VIZ_CY + (int)(sa * star->radius);
        uint32_t color = star->color == 0   ? pal->a
                         : star->color == 1 ? pal->b
                                            : pal->c;
        double near = star->radius / 220.0;
        int alpha = 20 + (int)(near * 199.0);
        draw_line(layer, x0, y0, x1, y1, color, star->size > 1.4 ? 2 : 1,
                  alpha);
        if(near > 0.82f) {
            draw_circle(layer, x1, y1, 1, color, alpha);
        }
    }

    for(int i = viz_shock_count - 1; i >= 0; i--) {
        viz_shocks[i].radius += dt * 260.0f;
        viz_shocks[i].life -= dt * 1.2f;
        if(viz_shocks[i].life <= 0.0f) {
            viz_shocks[i] = viz_shocks[viz_shock_count - 1];
            viz_shock_count--;
            continue;
        }
        draw_ring(layer, VIZ_CX, VIZ_CY, (int)viz_shocks[i].radius, 1,
                  viz_shocks[i].color, (int)(viz_shocks[i].life * 76.0f));
    }

    draw_ring(layer, VIZ_CX, VIZ_CY, 228, 1, pal->a, 56);
}

void spectrum_viz_reset(void)
{
    viz_last_track = -1;
    viz_shock_count = 0;
}

void spectrum_viz_create(lv_obj_t * parent)
{
    if(viz_ready) return;
    viz_ready = true;
    init_visuals();

    LV_DRAW_BUF_INIT_STATIC(viz_draw_buf);

    viz_canvas = lv_canvas_create(parent);
    lv_canvas_set_draw_buf(viz_canvas, &viz_draw_buf);
    lv_obj_set_pos(viz_canvas, SPECTRUM_VIZ_X, SPECTRUM_VIZ_Y);
    lv_obj_set_size(viz_canvas, VIZ_W, VIZ_H);
    lv_obj_set_style_radius(viz_canvas, 0, 0);
    lv_obj_set_style_border_width(viz_canvas, 0, 0);
    lv_obj_set_style_pad_all(viz_canvas, 0, 0);
    lv_obj_set_style_bg_opa(viz_canvas, LV_OPA_TRANSP, 0);
    app_obj_set_clickable(viz_canvas, false);
    app_obj_set_scrollable(viz_canvas, false);

    viz_cover_base = lv_image_create(parent);
    lv_image_set_src(viz_cover_base,
                     spectrum_cover(spectrum_state.track_index,
                                    spectrum_state.palette_index));
    lv_obj_set_size(viz_cover_base, 160, 160);
    lv_obj_set_pos(viz_cover_base, VIZ_CX - 80, VIZ_CY - 80);
    lv_image_set_pivot(viz_cover_base, 80, 80);
    app_obj_set_clickable(viz_cover_base, false);

    viz_cover_spin = lv_image_create(parent);
    lv_image_set_src(viz_cover_spin,
                     spectrum_cover_spin(spectrum_state.track_index,
                                         spectrum_state.palette_index));
    lv_obj_set_size(viz_cover_spin, 160, 160);
    lv_obj_set_pos(viz_cover_spin, VIZ_CX - 80, VIZ_CY - 80);
    lv_image_set_pivot(viz_cover_spin, 80, 80);
    lv_image_set_blend_mode(viz_cover_spin, LV_BLEND_MODE_ADDITIVE);
    app_obj_set_clickable(viz_cover_spin, false);

    viz_ring_inner = lv_obj_create(parent);
    lv_obj_set_style_bg_opa(viz_ring_inner, LV_OPA_TRANSP, 0);
    lv_obj_set_style_radius(viz_ring_inner, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_pad_all(viz_ring_inner, 0, 0);
    app_obj_set_clickable(viz_ring_inner, false);
    app_obj_set_scrollable(viz_ring_inner, false);

    viz_ring_outer = lv_obj_create(parent);
    lv_obj_set_style_bg_opa(viz_ring_outer, LV_OPA_TRANSP, 0);
    lv_obj_set_style_radius(viz_ring_outer, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_pad_all(viz_ring_outer, 0, 0);
    app_obj_set_clickable(viz_ring_outer, false);
    app_obj_set_scrollable(viz_ring_outer, false);

    viz_create_overlay(parent);
}

void spectrum_viz_update(double dt)
{
    if(!viz_ready) return;
    if(viz_last_track != spectrum_state.track_index) {
        viz_last_track = spectrum_state.track_index;
    }

    int mode = spectrum_state.mode;
    int size = cover_sizes[mode];
    const spectrum_palette_t * pal = spectrum_palette();

    viz_prepare_backdrop(pal);

    lv_layer_t layer;
    lv_canvas_init_layer(viz_canvas, &layer);
    draw_background(&layer, pal);

    switch(mode) {
        case SPECTRUM_MODE_ORBIT:
            draw_orbit(&layer, pal);
            break;
        case SPECTRUM_MODE_DUAL:
            draw_dual(&layer, pal);
            break;
        case SPECTRUM_MODE_RADIAL:
            draw_radial(&layer, pal);
            break;
        case SPECTRUM_MODE_SPIRAL:
            draw_spiral(&layer, pal);
            break;
        case SPECTRUM_MODE_SONAR:
            draw_sonar(&layer, pal);
            break;
        case SPECTRUM_MODE_STARS:
            draw_stars(&layer, pal, dt);
            break;
        default:
            break;
    }
    lv_canvas_finish_layer(viz_canvas, &layer);

    viz_add_halo(pal, size);

    int spin = (int)(spectrum_sim.time * cover_speed[mode] * 1800.0 / SP_PI);
    const lv_image_dsc_t * base_src;
    int base_size;
    if(size == 88) {
        base_src = spectrum_cover_base88(spectrum_state.track_index,
                                         spectrum_state.palette_index);
        base_size = 88;
    }
    else if(size == 78) {
        base_src = spectrum_cover_base78(spectrum_state.track_index,
                                         spectrum_state.palette_index);
        base_size = 78;
    }
    else {
        base_src = spectrum_cover(spectrum_state.track_index,
                                  spectrum_state.palette_index);
        base_size = 160;
    }
    lv_image_set_src(viz_cover_base, base_src);
    lv_obj_set_size(viz_cover_base, base_size, base_size);
    lv_obj_set_pos(viz_cover_base, VIZ_CX - base_size / 2,
                   VIZ_CY - base_size / 2);
    lv_image_set_pivot(viz_cover_base, base_size / 2, base_size / 2);
    lv_image_set_scale(viz_cover_base, (uint32_t)(256 * size / base_size));
    lv_image_set_rotation(viz_cover_base, 0);

    const lv_image_dsc_t * spin_src;
    int src_size;
    if(size == 88) {
        spin_src = spectrum_cover_spin88(spectrum_state.track_index,
                                         spectrum_state.palette_index);
        src_size = 88;
    }
    else if(size == 78) {
        spin_src = spectrum_cover_spin78(spectrum_state.track_index,
                                         spectrum_state.palette_index);
        src_size = 78;
    }
    else if(size <= 124) {
        spin_src = spectrum_cover_spin96(spectrum_state.track_index,
                                         spectrum_state.palette_index);
        src_size = 96;
    }
    else {
        spin_src = spectrum_cover_spin(spectrum_state.track_index,
                                       spectrum_state.palette_index);
        src_size = 160;
    }
    lv_image_set_src(viz_cover_spin, spin_src);
    lv_obj_set_size(viz_cover_spin, src_size, src_size);
    lv_obj_set_pos(viz_cover_spin, VIZ_CX - src_size / 2,
                   VIZ_CY - src_size / 2);
    lv_image_set_pivot(viz_cover_spin, src_size / 2, src_size / 2);
    lv_image_set_scale(viz_cover_spin, (uint32_t)(256 * size / src_size));
    lv_image_set_rotation(viz_cover_spin, spin);

    int r = size / 2;
    int inner_r = r - 1;
    lv_obj_set_size(viz_ring_inner, inner_r * 2, inner_r * 2);
    lv_obj_set_pos(viz_ring_inner, VIZ_CX - inner_r, VIZ_CY - inner_r);
    lv_obj_set_style_border_width(viz_ring_inner, 2, 0);
    lv_obj_set_style_border_color(viz_ring_inner, lv_color_hex(pal->a), 0);
    lv_obj_set_style_border_opa(viz_ring_inner, 64, 0);

    int outer_r = r + 2;
    lv_obj_set_size(viz_ring_outer, outer_r * 2, outer_r * 2);
    lv_obj_set_pos(viz_ring_outer, VIZ_CX - outer_r, VIZ_CY - outer_r);
    lv_obj_set_style_border_width(viz_ring_outer, 5, 0);
    lv_obj_set_style_border_color(viz_ring_outer, lv_color_hex(pal->c), 0);
    lv_obj_set_style_border_opa(viz_ring_outer, 46, 0);

    lv_obj_invalidate(viz_canvas);
    lv_obj_invalidate(viz_cover_base);
    lv_obj_invalidate(viz_cover_spin);
}

#endif
