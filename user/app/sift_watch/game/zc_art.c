#include "zc_art.h"

#include "zc_gfx.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define ZC_PI_F 3.14159265358979f

typedef struct {
    uint32_t s;
} rng_t;

static float rnd(rng_t * r)
{
    uint32_t t = (r->s += 0x6D2B79F5U);
    t = (t ^ (t >> 15)) * (t | 1U);
    t ^= t + (t ^ (t >> 7)) * (t | 61U);
    return (float)(t ^ (t >> 14)) / 4294967296.0f;
}

#include "zc_sprites_data.h"

const zc_sprite_def_t * zc_art_sprite(int type)
{
    if(type < 0 || type > 3) type = 0;
    return zc_sprites[type];
}

void zc_art_sprite_draw(int type, int frame, int x, int y, int mode,
                        uint8_t alpha)
{
    const zc_sprite_def_t * def = zc_art_sprite(type);
    if(frame < 0 || frame >= def->frames) frame = 0;
    const char * const * rows = def->rows[frame];
    int s = def->scale;
    for(int row = 0; row < def->h; row++) {
        const char * line = rows[row];
        for(int col = 0; line[col] != '\0'; col++) {
            char ch = line[col];
            if(ch == '.') continue;
            uint16_t color;
            if(mode == 1) color = ZC_RGB565(244, 236, 207);
            else if(mode == 2)
                color = ZC_RGB565(7, 10, 7);
            else if(ch >= 'A' && ch <= 'Z')
                color = def->pal[ch - 'A'];
            else
                color = ZC_WHITE;
            if(alpha >= 255)
                zc_rect_world(x + col * s, y + row * s, s, s, color);
            else
                zc_blend_rect_world(x + col * s, y + row * s, s, s, color,
                                    alpha);
        }
    }
}

static void bd_dead_tree(rng_t * r, int baseX, int baseY)
{
    uint16_t col = ZC_RGB565(7, 16, 10);
    int trunkH = 29 + (int)(rnd(r) * 16.0f);
    zc_rect(baseX, baseY - trunkH, 3, trunkH, col);
    for(int i = 0; i < 4; i++) {
        int y = baseY - 8 - i * 6;
        zc_rect(baseX + (i % 2 ? -7 : 2), y, 9, 2, col);
        zc_rect(baseX + (i % 2 ? -10 : 9), y - 4, 2, 5, col);
        zc_rect(baseX + (i % 2 ? -12 : 11), y - 7, 2, 4, col);
    }
    zc_blend_rect(baseX + 1, baseY - trunkH, 1, 3, ZC_RGB565(41, 56, 34), 140);
    zc_blend_rect(baseX - 8, baseY - 30, 6, 1, ZC_RGB565(41, 56, 34), 140);
}

static void bd_puddle(int x, int y, int w, int h)
{
    zc_rect(x, y, w, h, ZC_RGB565(16, 26, 20));
    zc_rect(x + 3, y - 2, w - 7, h + 4, ZC_RGB565(16, 26, 20));
    zc_blend_rect(x + 5, y + 1, w - 14, 1, ZC_RGB565(66, 95, 75), 61);
    zc_blend_rect(x + 8, y + 2, 8, 1, ZC_RGB565(196, 209, 151), 20);
}

static void bd_tire(int x, int y)
{
    zc_rect(x, y, 15, 6, ZC_RGB565(9, 12, 8));
    zc_rect(x + 3, y - 3, 9, 12, ZC_RGB565(9, 12, 8));
    zc_rect(x + 4, y - 1, 7, 8, ZC_RGB565(36, 37, 29));
    zc_rect(x + 6, y + 1, 3, 4, ZC_RGB565(13, 16, 11));
}

static void bd_oil_barrel(int x, int y, bool tipped)
{
    if(tipped) {
        zc_rect(x, y, 25, 9, ZC_RGB565(26, 26, 18));
        zc_rect(x + 1, y + 1, 23, 7, ZC_RGB565(60, 61, 43));
        zc_rect(x + 5, y, 2, 9, ZC_RGB565(96, 77, 40));
        zc_rect(x + 18, y, 2, 9, ZC_RGB565(96, 77, 40));
        zc_rect(x + 7, y + 3, 12, 2, ZC_RGB565(17, 20, 13));
    }
    else {
        zc_rect(x, y, 9, 24, ZC_RGB565(23, 23, 15));
        zc_rect(x + 1, y + 1, 7, 22, ZC_RGB565(62, 59, 40));
        zc_rect(x + 1, y + 5, 7, 2, ZC_RGB565(91, 74, 43));
        zc_rect(x + 1, y + 16, 7, 2, ZC_RGB565(91, 74, 43));
        zc_rect(x + 3, y + 3, 3, 1, ZC_RGB565(37, 36, 24));
    }
}

static void bd_bones(int x, int y)
{
    zc_rect(x, y, 6, 1, ZC_RGB565(143, 134, 95));
    zc_rect(x + 4, y - 2, 2, 2, ZC_RGB565(143, 134, 95));
    zc_rect(x - 1, y - 1, 1, 3, ZC_RGB565(143, 134, 95));
    zc_rect(x + 8, y + 4, 4, 1, ZC_RGB565(143, 134, 95));
    zc_rect(x + 9, y - 4, 5, 4, ZC_RGB565(166, 155, 113));
    zc_rect(x + 10, y - 3, 1, 1, ZC_RGB565(166, 155, 113));
    zc_rect(x + 12, y - 3, 1, 1, ZC_RGB565(166, 155, 113));
}

static void bd_road_sign(int x, int y)
{
    zc_rect(x, y, 3, 34, ZC_RGB565(20, 21, 15));
    zc_rect(x - 8, y, 20, 12, ZC_RGB565(59, 58, 38));
    zc_rect(x - 6, y + 2, 16, 8, ZC_RGB565(109, 87, 48));
    zc_rect(x - 3, y + 4, 2, 4, ZC_RGB565(181, 157, 87));
    zc_rect(x + 1, y + 4, 4, 1, ZC_RGB565(181, 157, 87));
    zc_rect(x + 6, y + 4, 2, 4, ZC_RGB565(181, 157, 87));
}

static void draw_backdrop(void)
{
    rng_t rng = {2307U};
    int W = zc.w;
    int H = zc.h;
    static const int stops[][4] = {{0, 5, 8, 6},
                                   {26, 7, 16, 11},
                                   {58, 12, 23, 16},
                                   {84, 18, 33, 23},
                                   {110, 26, 42, 27}};
    for(int y = 0; y < 116; y += 2) {
        int a = 0;
        int b = 1;
        for(int i = 0; i < 4; i++) {
            if(y >= stops[i][0] && y <= stops[i + 1][0]) {
                a = i;
                b = i + 1;
                break;
            }
        }
        float t =
            (float)(y - stops[a][0]) /
            (float)(stops[b][0] > stops[a][0] ? stops[b][0] - stops[a][0] : 1);
        if(t < 0) t = 0;
        if(t > 1) t = 1;
        int rr = (int)(stops[a][1] + (stops[b][1] - stops[a][1]) * t);
        int gg = (int)(stops[a][2] + (stops[b][2] - stops[a][2]) * t);
        int bb = (int)(stops[a][3] + (stops[b][3] - stops[a][3]) * t);
        zc_rect(0, y, W, 2, ZC_RGB565(rr, gg, bb));
    }

    for(int i = 0; i < 95; i++) {
        int sx = (int)(rnd(&rng) * W);
        int sy = (int)(rnd(&rng) * 102.0f);
        float bright = rnd(&rng);
        if(bright > 0.86f) {
            zc_blend_rect(sx, sy, 2, 1, ZC_RGB565(219, 225, 173), 140);
            zc_blend_rect(sx - 1, sy + 1, 4, 1, ZC_RGB565(219, 225, 173), 140);
        }
        else {
            uint16_t col = bright > 0.5f ? ZC_RGB565(186, 198, 148)
                                         : ZC_RGB565(136, 156, 124);
            uint8_t alpha = bright > 0.5f ? 82 : 56;
            zc_blend_rect(sx, sy, 1, 1, col, alpha);
        }
    }

    int mx = 300;
    int my = 71;
    zc_blend_circle(mx, my, 59, ZC_RGB565(154, 169, 111), 6);
    zc_blend_circle(mx, my, 47, ZC_RGB565(170, 182, 119), 10);
    zc_blend_circle(mx, my, 37, ZC_RGB565(193, 202, 135), 19);
    zc_blend_circle(mx, my, 31, ZC_RGB565(214, 213, 163), 41);
    zc_circle(mx, my, 29, ZC_RGB565(201, 206, 148));
    for(int yy = -29; yy <= 29; yy++) {
        int rem = 29 * 29 - yy * yy;
        if(rem < 0) rem = 0;
        int dx = 0;
        while((dx + 1) * (dx + 1) <= rem) dx++;
        int edge = (-yy + 29) * 11 / 100;
        if(edge < 0) edge = 0;
        int w = dx * 2 + 1;
        if(w > edge) w = edge;
        zc_rect(mx - dx, my + yy, w, 1, ZC_RGB565(182, 189, 128));
        if((yy < 0 ? -yy : yy) > 18) {
            zc_blend_rect(mx + dx - 5, my + yy, 5, 1, ZC_RGB565(105, 112, 72),
                          89);
        }
    }
    static const int craters[][4] = {{-11, -10, 7, 4}, {-3, -18, 4, 2},
                                     {9, -4, 6, 3},    {12, 11, 4, 2},
                                     {-12, 9, 5, 2},   {2, 5, 3, 2}};
    for(size_t i = 0; i < sizeof(craters) / sizeof(craters[0]); i++) {
        int cx = craters[i][0];
        int cy = craters[i][1];
        int cw = craters[i][2];
        int ch = craters[i][3];
        zc_blend_rect(mx + cx, my + cy, cw, ch, ZC_RGB565(102, 111, 70), 87);
        zc_blend_rect(mx + cx + 1, my + cy + 1, cw - 2 > 1 ? cw - 2 : 1, 1,
                      ZC_RGB565(161, 168, 113), 56);
    }
    zc_blend_rect(mx - 59, my + 12, 78, 3, ZC_RGB565(5, 10, 7), 140);
    zc_blend_rect(mx - 41, my + 15, 110, 2, ZC_RGB565(5, 10, 7), 140);
    zc_blend_rect(mx + 23, my - 2, 36, 2, ZC_RGB565(5, 10, 7), 140);

    static const int skyline[][4] = {
        {0, 92, 38, 28},   {21, 83, 17, 37},   {43, 99, 35, 21},
        {68, 88, 10, 32},  {89, 103, 19, 17},  {110, 86, 8, 34},
        {122, 78, 14, 42}, {139, 97, 29, 23},  {174, 104, 21, 16},
        {201, 90, 13, 30}, {218, 99, 31, 21},  {250, 84, 5, 36},
        {261, 96, 25, 24}, {287, 103, 17, 17}, {307, 80, 38, 40},
        {346, 98, 23, 22}, {370, 90, 20, 30}};
    for(size_t i = 0; i < sizeof(skyline) / sizeof(skyline[0]); i++) {
        zc_rect(skyline[i][0], skyline[i][1], skyline[i][2], skyline[i][3],
                ZC_RGB565(9, 16, 11));
    }
    for(int x = 4; x < W; x += 19) {
        int h = 3 + (int)(rnd(&rng) * 8.0f);
        zc_rect(x, 112 - h, 6 + (int)(rnd(&rng) * 7.0f), h,
                ZC_RGB565(9, 16, 11));
    }

    zc_rect(320, 66, 24, 18, ZC_RGB565(10, 17, 12));
    zc_rect(324, 84, 3, 34, ZC_RGB565(10, 17, 12));
    zc_rect(337, 84, 3, 34, ZC_RGB565(10, 17, 12));
    zc_rect(316, 63, 32, 4, ZC_RGB565(10, 17, 12));
    zc_rect(318, 57, 28, 7, ZC_RGB565(10, 17, 12));
    zc_rect(320, 58, 24, 2, ZC_RGB565(22, 33, 23));
    zc_rect(318, 61, 28, 1, ZC_RGB565(22, 33, 23));
    zc_rect(222, 64, 2, 54, ZC_RGB565(10, 17, 12));
    zc_rect(216, 73, 14, 2, ZC_RGB565(10, 17, 12));
    zc_blend_rect(221, 62, 4, 2, ZC_RGB565(133, 153, 96), 82);

    bd_dead_tree(&rng, 51, 116);
    bd_dead_tree(&rng, 359, 116);

    zc_rect(87, 82, 3, 35, ZC_RGB565(8, 14, 10));
    zc_rect(79, 87, 19, 2, ZC_RGB565(8, 14, 10));
    zc_rect(82, 94, 13, 2, ZC_RGB565(8, 14, 10));
    zc_rect(263, 89, 3, 28, ZC_RGB565(8, 14, 10));
    zc_rect(256, 94, 17, 2, ZC_RGB565(8, 14, 10));
    for(int x = 92; x < 256; x += 2) {
        int ty =
            90 + (int)lroundf(sinf((float)(x - 92) / 164.0f * ZC_PI_F) * 7.0f);
        zc_blend_rect(x, ty, 2, 1, ZC_RGB565(7, 12, 8), 204);
    }
    for(int x = 264; x < W; x += 2) {
        int ty =
            96 + (int)lroundf(sinf((float)(x - 264) / 126.0f * ZC_PI_F) * 5.0f);
        zc_blend_rect(x, ty, 2, 1, ZC_RGB565(7, 12, 8), 204);
    }

    for(int y = 104; y < 138; y += 2) {
        float alpha = (float)(y - 104) / 34.0f;
        uint8_t a = (uint8_t)((0.03f + alpha * 0.055f) * 255.0f);
        for(int x = y % 4; x < W; x += 4) {
            if(rnd(&rng) > 0.3f)
                zc_blend_rect(x, y, 4, 2, ZC_RGB565(121, 143, 103), a);
        }
    }

    zc_rect(0, 116, W, H - 116, ZC_RGB565(20, 20, 14));
    for(int y = 116; y < H; y += 2) {
        float t = (float)(y - 116) / (float)(H - 116);
        int shade = (int)(15.0f + 13.0f * t);
        zc_rect(0, y, W, 2,
                ZC_RGB565(shade, shade + 1, shade - 4 > 7 ? shade - 4 : 7));
    }
    for(int i = 0; i < 700; i++) {
        int x = (int)(rnd(&rng) * W);
        int y = 116 + (int)(rnd(&rng) * (float)(H - 116));
        bool light = rnd(&rng) > 0.55f;
        int w = rnd(&rng) > 0.82f ? 3 : 1;
        zc_blend_rect(x, y, w, 1,
                      light ? ZC_RGB565(87, 79, 49) : ZC_RGB565(4, 8, 5),
                      light ? 33 : 56);
    }

    for(int y = 116; y < H; y += 2) {
        float t = (float)(y - 116) / (float)(H - 116);
        int half = (int)(10.0f + t * t * 161.0f);
        zc_rect(195 - half, y, half * 2, 2, ZC_RGB565(28, 27, 20));
        zc_blend_rect(195 - half, y, 2, 2, ZC_RGB565(86, 78, 48), 61);
        zc_blend_rect(195 + half - 2, y, 2, 2, ZC_RGB565(86, 78, 48), 61);
    }
    for(int i = 0; i < 90; i++) {
        int y = 116 + (int)(rnd(&rng) * (float)(H - 116));
        float t = (float)(y - 116) / (float)(H - 116);
        int half = (int)(10.0f + t * t * 150.0f);
        int x = (int)(195.0f + (rnd(&rng) * 2.0f - 1.0f) * (float)half * 0.82f);
        bool light = rnd(&rng) > 0.5f;
        int w = 1 + (int)(rnd(&rng) * 5.0f);
        zc_blend_rect(x, y, w, 1,
                      light ? ZC_RGB565(106, 94, 57) : ZC_RGB565(6, 8, 5),
                      light ? 56 : 82);
    }
    int dashY = 140;
    int dashIndex = 0;
    while(dashY < H) {
        float t = (float)(dashY - 116) / (float)(H - 116);
        int w = (int)(1.0f + t * 4.0f);
        int h = (int)(2.0f + t * 5.0f);
        if(w < 2) w = 2;
        if(h < 2) h = 2;
        if((dashIndex & 1) == 0) {
            zc_blend_rect(195 - w / 2, dashY, w, h, ZC_RGB565(118, 104, 57),
                          89);
        }
        dashY += 22 + (int)(t * 22.0f);
        dashIndex++;
    }
    for(int i = 0; i < 12; i++) {
        int x = (int)(60.0f + rnd(&rng) * 270.0f);
        int y = (int)(150.0f + rnd(&rng) * 220.0f);
        int x1 = (int)(x + rnd(&rng) * 14.0f - 7.0f);
        int y1 = (int)(y + 6.0f + rnd(&rng) * 14.0f);
        int x2 = (int)(x + rnd(&rng) * 18.0f - 9.0f);
        int y2 = (int)(y + 18.0f + rnd(&rng) * 18.0f);
        zc_line(x, y, x1, y1, 1, ZC_RGB565(4, 7, 4));
        zc_line(x1, y1, x2, y2, 1, ZC_RGB565(4, 7, 4));
    }

    bd_puddle(71, 294, 31, 8);
    bd_puddle(300, 228, 48, 11);
    bd_puddle(324, 378, 40, 8);
    bd_tire(49, 318);
    bd_tire(344, 345);
    bd_oil_barrel(34, 236, true);
    bd_oil_barrel(338, 164, false);
    bd_bones(287, 302);
    bd_bones(119, 377);
    bd_road_sign(86, 212);
    for(int i = 0; i < 28; i++) {
        int x = rnd(&rng) < 0.5f ? (int)(20.0f + rnd(&rng) * 90.0f)
                                 : (int)(280.0f + rnd(&rng) * 90.0f);
        int y = (int)(140.0f + rnd(&rng) * 260.0f);
        bool light = rnd(&rng) > 0.5f;
        zc_rect(x, y, 1, 2 + (int)(rnd(&rng) * 3.0f),
                light ? ZC_RGB565(38, 48, 28) : ZC_RGB565(29, 36, 23));
    }

    for(int y = 0; y < H; y++) {
        for(int x = 0; x < W; x++) {
            float dx = (float)(x - 195);
            float dy = (float)(y - 232);
            float d = sqrtf(dx * dx + dy * dy);
            float t = (d - 115.0f) / 165.0f;
            if(t <= 0) continue;
            if(t > 1) t = 1;
            float a = t < 0.72f ? 0.10f * (t / 0.72f)
                                : 0.10f + 0.52f * ((t - 0.72f) / 0.28f);
            if(a <= 0) continue;
            zc_blend_pixel(x, y, ZC_BLACK, (uint8_t)(a * 255.0f));
        }
    }
    for(int i = 0; i < 120; i++) {
        int x = (int)(rnd(&rng) * W);
        int y = (int)(rnd(&rng) * H);
        bool light = rnd(&rng) > 0.5f;
        zc_blend_rect(x, y, 1, 1, light ? ZC_RGB565(227, 219, 174) : ZC_BLACK,
                      light ? 9 : 26);
    }
}

void zc_art_backdrop_build(void)
{
    if(zc.backdrop == NULL) return;
    uint16_t * saved = zc.fb;
    int ox = zc.ox;
    int oy = zc.oy;
    zc.fb = zc.backdrop;
    zc.ox = 0;
    zc.oy = 0;
    draw_backdrop();
    zc.fb = saved;
    zc.ox = ox;
    zc.oy = oy;
}

void zc_art_backdrop_draw(void)
{
    if(zc.backdrop != NULL) {
        zc_copy_backdrop();
        return;
    }
    zc_clear(ZC_INK);
    draw_backdrop();
}

typedef struct {
    int16_t x;
    int16_t y;
    uint8_t w;
    uint8_t h;
    uint8_t a;
} fog_dot_t;

#define ZC_FOG_MAX 900
static fog_dot_t fog_a[ZC_FOG_MAX];
static fog_dot_t fog_b[ZC_FOG_MAX];
static int fog_a_count;
static int fog_b_count;

static void make_fog(uint32_t seed, int width, int height, float alpha_base,
                     fog_dot_t * out, int * count)
{
    rng_t rng = {seed};
    int n = 0;
    struct cluster {
        float x, y, rx, ry;
    } clusters[18];
    for(int i = 0; i < 18; i++) {
        clusters[i].x = rnd(&rng) * (float)width;
        clusters[i].y = (float)height * (0.2f + rnd(&rng) * 0.65f);
        clusters[i].rx = 24.0f + rnd(&rng) * 64.0f;
        clusters[i].ry = 4.0f + rnd(&rng) * 10.0f;
    }
    for(int i = 0; i < 18; i++) {
        int cnt = 20 + (int)(rnd(&rng) * 30.0f);
        for(int j = 0; j < cnt && n < ZC_FOG_MAX; j++) {
            float a = rnd(&rng) * 6.2831853f;
            float rr = sqrtf(rnd(&rng));
            int px =
                (int)lroundf(clusters[i].x + cosf(a) * clusters[i].rx * rr);
            int py =
                (int)lroundf(clusters[i].y + sinf(a) * clusters[i].ry * rr);
            int w = 2 + (int)(rnd(&rng) * 8.0f);
            int h = 1 + (int)(rnd(&rng) * 2.0f);
            if(px < -16 || px > width + 8 || py < -4 || py > height + 4)
                continue;
            out[n].x = (int16_t)px;
            out[n].y = (int16_t)py;
            out[n].w = (uint8_t)w;
            out[n].h = (uint8_t)h;
            out[n].a =
                (uint8_t)(alpha_base * (0.4f + rnd(&rng) * 0.6f) * 255.0f);
            n++;
            if(rnd(&rng) > 0.6f && n < ZC_FOG_MAX) {
                out[n].x = (int16_t)(px + 2);
                out[n].y = (int16_t)(py + h);
                out[n].w = (uint8_t)(w > 2 ? w - 2 : 1);
                out[n].h = 1;
                out[n].a = out[n - 1].a;
                n++;
            }
        }
    }
    *count = n;
}

void zc_art_fog_init(void)
{
    make_fog(91U, 520, 90, 0.075f, fog_a, &fog_a_count);
    make_fog(177U, 460, 120, 0.045f, fog_b, &fog_b_count);
}

static void draw_fog_layer(const fog_dot_t * dots, int count, int x, int y,
                           uint8_t layer_alpha)
{
    for(int i = 0; i < count; i++) {
        uint16_t a = (uint16_t)((dots[i].a * layer_alpha) / 255U);
        if(a == 0) continue;
        zc_blend_rect(x + dots[i].x, y + dots[i].y, dots[i].w, dots[i].h,
                      ZC_RGB565(155, 172, 125), (uint8_t)a);
    }
}

void zc_art_fog_draw(float t)
{
    int x1 = (int)(sinf(t * 0.035f) * 22.0f - 34.0f) + zc.ox;
    int x2 = (int)(sinf(t * 0.022f + 2.0f) * 26.0f - 30.0f) + zc.ox;
    draw_fog_layer(fog_a, fog_a_count, x1, 88 + zc.oy, 122);
    draw_fog_layer(fog_b, fog_b_count, x2, 144 + zc.oy, 66);
}

typedef struct {
    float x;
    float y;
    float vx;
    float vy;
    float phase;
    uint8_t size;
    uint8_t alpha;
    bool warm;
} mote_t;

static mote_t motes[22];
static rng_t mote_rng = {0x51F7A11DU};

void zc_art_motes_init(void)
{
    mote_rng.s = 0x51F7A11DU;
    for(int i = 0; i < 22; i++) {
        motes[i].x = 12.0f + rnd(&mote_rng) * (float)(zc.w - 24);
        motes[i].y = 130.0f + rnd(&mote_rng) * (float)(zc.h - 130);
        motes[i].vy = -7.0f + rnd(&mote_rng) * 5.0f;
        motes[i].vx = -2.0f + rnd(&mote_rng) * 4.0f;
        motes[i].size = rnd(&mote_rng) > 0.78f ? 2 : 1;
        motes[i].alpha = (uint8_t)((0.12f + rnd(&mote_rng) * 0.30f) * 255.0f);
        motes[i].phase = rnd(&mote_rng) * 6.2831853f;
        motes[i].warm = rnd(&mote_rng) > 0.5f;
    }
}

void zc_art_motes_update(float dt, float t)
{
    for(int i = 0; i < 22; i++) {
        mote_t * m = &motes[i];
        m->y += m->vy * dt;
        m->x += (m->vx + sinf(t * 0.7f + m->phase) * 1.6f) * dt;
        if(m->y < 110.0f || m->x < -8.0f || m->x > (float)zc.w + 8.0f) {
            m->x = 20.0f + rnd(&mote_rng) * (float)(zc.w - 40);
            m->y = (float)(zc.h - 65) + rnd(&mote_rng) * 53.0f;
            m->vy = -9.0f + rnd(&mote_rng) * 6.0f;
            m->vx = -2.0f + rnd(&mote_rng) * 4.0f;
        }
    }
}

void zc_art_motes_draw(float t)
{
    for(int i = 0; i < 22; i++) {
        mote_t * m = &motes[i];
        float flicker = 0.55f + 0.45f * sinf(t * 3.0f + m->phase);
        uint8_t a = (uint8_t)((float)m->alpha * flicker);
        uint16_t col = m->warm ? ZC_ORANGE : ZC_ACID;
        zc_blend_rect_world((int)m->x, (int)m->y, m->size, m->size, col, a);
    }
}

static void art_r(int x, int y, int w, int h, uint16_t c)
{
    zc_rect_world(x, y, w, h, c);
}

static void art_blend(int x, int y, int w, int h, uint16_t c, uint8_t a)
{
    zc_blend_rect_world(x, y, w, h, c, a);
}

static void art_circle(int cx, int cy, int r, uint16_t c, uint8_t a)
{
    zc_blend_circle(cx + zc.ox, cy + zc.oy, r, c, a);
}

static void draw_barrel(float angle, float recoil)
{
    float len = 39.0f - recoil * 6.0f;
    int px = 195;
    int py = 404 + zc.dy;
    float sx = (float)px + cosf(angle) * (7.0f + recoil * 4.0f);
    float sy = (float)py + sinf(angle) * (7.0f + recoil * 4.0f);
    float ex = (float)px + cosf(angle) * len;
    float ey = (float)py + sinf(angle) * len;
    zc_line_world((int)lroundf(sx), (int)lroundf(sy), (int)lroundf(ex),
                  (int)lroundf(ey), 11, ZC_RGB565(8, 11, 7));
    zc_line_world((int)lroundf(sx), (int)lroundf(sy), (int)lroundf(ex),
                  (int)lroundf(ey), 8, ZC_RGB565(63, 72, 45));
    zc_line_world((int)lroundf(sx) + 1, (int)lroundf(sy) + 1,
                  (int)lroundf(ex) + 1, (int)lroundf(ey) + 1, 3,
                  ZC_RGB565(137, 145, 98));
    float bandT = 0.66f;
    float bandX = sx + (ex - sx) * bandT;
    float bandY = sy + (ey - sy) * bandT;
    float bxv = cosf(angle + ZC_PI_F * 0.5f);
    float byv = sinf(angle + ZC_PI_F * 0.5f);
    zc_line_world((int)lroundf(bandX - bxv * 5.0f),
                  (int)lroundf(bandY - byv * 5.0f),
                  (int)lroundf(bandX + bxv * 5.0f),
                  (int)lroundf(bandY + byv * 5.0f), 2, ZC_RGB565(35, 42, 25));
    art_r((int)lroundf(bandX) - 1, (int)lroundf(bandY) - 1, 2, 2,
          ZC_RGB565(156, 160, 109));
    int bx = (int)lroundf(ex);
    int by = (int)lroundf(ey);
    art_r(bx - 5, by - 5, 10, 10, ZC_RGB565(8, 11, 7));
    art_r(bx - 4, by - 4, 8, 8, ZC_RGB565(78, 88, 58));
    art_r(bx - 4, by - 2, 2, 2, ZC_RGB565(23, 28, 16));
    art_r(bx + 2, by - 3, 2, 2, ZC_RGB565(23, 28, 16));
    art_r(bx - 1, by - 1, 3, 3, ZC_RGB565(10, 13, 8));
    art_r(bx, by, 1, 1, ZC_RGB565(194, 194, 139));
}

static void draw_barrel_twin(float angle, float recoil)
{
    float len = 39.0f - recoil * 6.0f;
    int px = 195;
    int py = 404 + zc.dy;
    float sx = (float)px + cosf(angle) * (7.0f + recoil * 4.0f);
    float sy = (float)py + sinf(angle) * (7.0f + recoil * 4.0f);
    float ex = (float)px + cosf(angle) * len;
    float ey = (float)py + sinf(angle) * len;
    float ox = cosf(angle + ZC_PI_F * 0.5f) * 6.0f;
    float oy = sinf(angle + ZC_PI_F * 0.5f) * 6.0f;
    zc_line_world((int)lroundf(sx + ox), (int)lroundf(sy + oy),
                  (int)lroundf(ex + ox), (int)lroundf(ey + oy), 8,
                  ZC_RGB565(8, 11, 7));
    zc_line_world((int)lroundf(sx + ox), (int)lroundf(sy + oy),
                  (int)lroundf(ex + ox), (int)lroundf(ey + oy), 5,
                  ZC_RGB565(70, 80, 52));
    zc_line_world((int)lroundf(sx + ox) + 1, (int)lroundf(sy + oy) + 1,
                  (int)lroundf(ex + ox) + 1, (int)lroundf(ey + oy) + 1, 2,
                  ZC_RGB565(129, 138, 92));
    int mx = (int)lroundf(ex + ox);
    int my = (int)lroundf(ey + oy);
    art_r(mx - 4, my - 4, 8, 8, ZC_RGB565(8, 11, 7));
    art_r(mx - 3, my - 3, 6, 6, ZC_RGB565(78, 88, 58));
    art_r(mx - 1, my - 1, 2, 2, ZC_RGB565(10, 13, 8));
}

static void draw_sandbags(float t)
{
    static const int rows[3] = {418, 431, 444};
    static const uint16_t cols[3][3] = {
        {ZC_RGB565(26, 26, 16), ZC_RGB565(95, 87, 55), ZC_RGB565(123, 112, 71)},
        {ZC_RGB565(23, 24, 15), ZC_RGB565(85, 78, 50), ZC_RGB565(110, 100, 64)},
        {ZC_RGB565(19, 21, 13), ZC_RGB565(72, 66, 43), ZC_RGB565(97, 88, 55)}};
    for(int row = 0; row < 3; row++) {
        int y = rows[row] + zc.dy;
        int offset = row % 2 ? 14 : 0;
        int bagW = 29;
        for(int x = -offset; x < zc.w + bagW; x += bagW) {
            int bw = bagW - 2;
            if(bw > zc.w - x) bw = zc.w - x;
            if(bw <= 0) continue;
            art_r(x, y, bw, 13, cols[row][0]);
            art_r(x + 2, y + 2, bw - 4, 9, cols[row][1]);
            art_r(x + 4, y + 2, bw - 10, 2, cols[row][2]);
            art_r(x + 6, y + 9, bw - 14, 1, cols[row][0]);
            art_blend(x + 3, y + 3, 3, 1, ZC_RGB565(207, 199, 148), 41);
            if(row == 2 && x > 110 && x < 194) {
                art_r(x + 9, y + 4, 2, 8, ZC_RGB565(46, 42, 27));
            }
        }
    }
    art_r(0, 416 + zc.dy, zc.w, 2, ZC_RGB565(11, 14, 8));
    for(int x = 8; x < zc.w; x += 17) {
        uint16_t c = (x % 34) ? ZC_RGB565(107, 99, 68) : ZC_RGB565(62, 62, 42);
        art_r(x, 414 + zc.dy + (x % 3), 2, 2, c);
    }
    float blink = sinf(t * 3.1f) > 0.3f ? 1.0f : 0.2f;
    art_blend(149, 421 + zc.dy, 3, 3, ZC_RED,
              (uint8_t)((0.2f + blink * 0.7f) * 255.0f));
    if(blink > 0.5f) art_circle(150, 422, 10, ZC_RED, 20);
}

static void draw_wire(float t)
{
    for(int i = 0; i < 5; i++) {
        int x = 8 + i * 84;
        art_r(x, 414 + zc.dy, 2, 17, ZC_RGB565(10, 13, 8));
        art_r(x - 2, 413 + zc.dy + (x % 3), 6, 2, ZC_RGB565(10, 13, 8));
    }
    for(int layer = 0; layer < 3; layer++) {
        for(int x = 0; x < zc.w; x += 3) {
            int y = 417 + zc.dy + layer * 4 +
                    (int)lroundf(sinf((float)x * 0.07f + (float)layer * 1.8f +
                                      t * 0.8f) *
                                 2.0f);
            art_r(x, y, 2, 1, ZC_RGB565(48, 54, 31));
            if(x % 18 < 3) art_r(x + 1, y - 2, 1, 4, ZC_RGB565(48, 54, 31));
        }
    }
}

void zc_art_base_draw(float t, float aim, float recoil, int base_hp, bool twin)
{
    int dy = zc.dy;
    art_r(49, 344 + dy, 3, 78, ZC_RGB565(23, 27, 18));
    art_r(50, 344 + dy, 1, 78, ZC_RGB565(72, 80, 55));
    for(int i = 0; i < 26; i++) {
        int yy = 348 + dy + i / 5;
        int cut = (i % 5 == 4 && sinf(t * 1.6f + (float)i) > 0.1f) ? 1 : 0;
        art_r(52 + i,
              yy + (int)lroundf(sinf(t * 3.0f + (float)i * 0.3f) * 1.5f), 1,
              12 - cut, ZC_RGB565(140, 49, 39));
    }
    art_r(54, 352 + dy, 2, 2, ZC_RGB565(92, 32, 27));
    art_r(64, 354 + dy, 3, 1, ZC_RGB565(92, 32, 27));
    art_r(69, 357 + dy, 2, 2, ZC_RGB565(92, 32, 27));
    art_r(61, 351 + dy, 2, 2, ZC_RGB565(206, 185, 125));
    art_r(66, 351 + dy, 2, 2, ZC_RGB565(206, 185, 125));
    art_r(63, 355 + dy, 4, 1, ZC_RGB565(206, 185, 125));
    art_r(45, 340 + dy, 11, 4, ZC_RGB565(42, 47, 30));
    art_r(48, 338 + dy, 5, 2, ZC_RGB565(100, 108, 72));

    art_r(332, 365 + dy, 3, 56, ZC_RGB565(27, 30, 20));
    art_r(332, 365 + dy, 1, 56, ZC_RGB565(85, 92, 61));
    art_r(318, 364 + dy, 18, 3, ZC_RGB565(43, 47, 30));
    art_r(314, 366 + dy, 9, 13, ZC_RGB565(19, 22, 14));
    art_r(316, 368 + dy, 5, 8, ZC_RGB565(179, 113, 50));
    art_r(317, 369 + dy, 3, 5, ZC_RGB565(244, 207, 120));
    art_r(316, 365 + dy, 5, 2, ZC_RGB565(62, 59, 38));
    art_r(318, 379 + dy, 2, 3, ZC_RGB565(62, 59, 38));
    float flick = 0.5f + 0.5f * sinf(t * 8.4f) * sinf(t * 2.1f + 1.0f);
    art_circle(318, 373, 30, ZC_RGB565(246, 179, 83),
               (uint8_t)((0.045f + flick * 0.035f) * 255.0f));
    art_circle(318, 373, 18, ZC_RGB565(246, 179, 83),
               (uint8_t)((0.04f + flick * 0.025f) * 255.0f));

    art_circle(195, 414, 45, ZC_BLACK, 97);
    art_r(151, 409 + dy, 88, 10, ZC_RGB565(9, 12, 7));
    art_r(159, 410 + dy, 72, 7, ZC_RGB565(37, 44, 26));
    art_r(165, 412 + dy, 60, 3, ZC_RGB565(61, 73, 42));
    for(int i = 0; i < 4; i++)
        art_r(169 + i * 17, 413 + dy, 2, 2, ZC_RGB565(124, 129, 90));

    art_r(158, 390 + dy, 18, 24, ZC_RGB565(10, 13, 8));
    art_r(161, 392 + dy, 13, 20, ZC_RGB565(61, 72, 41));
    art_r(163, 394 + dy, 9, 4, ZC_RGB565(102, 115, 70));
    art_r(161, 407 + dy, 13, 3, ZC_RGB565(28, 34, 20));
    art_r(214, 390 + dy, 18, 24, ZC_RGB565(10, 13, 8));
    art_r(216, 392 + dy, 13, 20, ZC_RGB565(61, 72, 41));
    art_r(218, 394 + dy, 9, 4, ZC_RGB565(102, 115, 70));
    art_r(216, 407 + dy, 13, 3, ZC_RGB565(28, 34, 20));
    art_r(169, 391 + dy, 52, 24, ZC_RGB565(10, 13, 8));
    art_r(172, 393 + dy, 46, 20, ZC_RGB565(39, 48, 28));
    art_r(176, 396 + dy, 38, 13, ZC_RGB565(58, 70, 40));
    art_r(180, 397 + dy, 30, 3, ZC_RGB565(102, 116, 70));
    art_r(176, 407 + dy, 38, 2, ZC_RGB565(26, 32, 19));

    draw_barrel(aim, recoil);
    if(twin) draw_barrel_twin(aim, recoil);

    art_r(178, 397 + dy, 34, 20, ZC_RGB565(10, 13, 8));
    art_r(181, 399 + dy, 28, 17, ZC_RGB565(74, 86, 50));
    art_r(184, 401 + dy, 22, 4, ZC_RGB565(116, 131, 77));
    art_r(184, 411 + dy, 22, 3, ZC_RGB565(27, 33, 19));
    art_r(190, 404 + dy, 10, 7, ZC_RGB565(36, 44, 26));
    art_r(184, 387 + dy, 22, 9, ZC_RGB565(10, 13, 8));
    art_r(187, 389 + dy, 16, 5, ZC_RGB565(70, 81, 48));
    art_r(190, 390 + dy, 10, 2, ZC_RGB565(113, 126, 76));
    art_r(202, 387 + dy, 2, 8, ZC_RGB565(27, 33, 19));
    float optic = 0.5f + 0.5f * sinf(t * 3.7f);
    art_blend(205, 390 + dy, 2, 2, ZC_ACID,
              (uint8_t)((0.4f + optic * 0.5f) * 255.0f));
    art_r(228, 414 + dy, 4, 2, ZC_RGB565(183, 133, 63));
    art_r(234, 413 + dy, 2, 2, ZC_RGB565(183, 133, 63));
    art_r(159, 415 + dy, 3, 2, ZC_RGB565(183, 133, 63));
    art_r(229, 416 + dy, 2, 1, ZC_RGB565(110, 84, 42));
    float blink = sinf(t * 2.4f) > 0.5f ? 1.0f : 0.2f;
    art_blend(220, 405 + dy, 3, 3, ZC_RED,
              (uint8_t)((0.35f + blink * 0.55f) * 255.0f));
    if(blink > 0.5f) art_circle(221, 406, 13, ZC_RED, 26);

    draw_sandbags(t);
    draw_wire(t);
    int smoke_count = base_hp <= 2 ? 8 : 4;
    for(int i = 0; i < smoke_count; i++) {
        int sx =
            202 + (i % 4) * 9 + (int)lroundf(sinf(t * 0.7f + (float)i) * 4.0f);
        int sy = 394 + dy - (i / 4) * 9 - (int)fmodf(t * 4.0f, 12.0f);
        uint8_t a = (uint8_t)(((base_hp <= 2 ? 0.22f : 0.16f) -
                               (float)(i % 4) * 0.025f) *
                              255.0f);
        art_blend(sx, sy, 7, 3, ZC_RGB565(18, 22, 15), a);
    }
    if(base_hp <= 2) {
        float pulse = 0.35f + 0.25f * sinf(t * 8.0f);
        for(int i = 0; i < 4; i++) {
            int fx =
                175 + i * 12 + (int)lroundf(sinf(t * 7.0f + (float)i) * 2.0f);
            int fh = 3 + (int)lroundf(sinf(t * 9.0f + (float)i) * 2.0f);
            art_blend(fx, 414 + dy - fh, 2, fh, ZC_ORANGE,
                      (uint8_t)(pulse * 255.0f));
        }
    }
}
