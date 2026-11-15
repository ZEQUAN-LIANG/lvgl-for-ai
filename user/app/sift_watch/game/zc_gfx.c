#include "zc_gfx.h"

#include "zc_cjk_font.h"
#include "zc_font5x7.h"

#include <math.h>
#include <string.h>

zc_ctx_t zc;

void zc_gfx_bind(uint16_t * fb, uint16_t * backdrop, int w, int h, int dy, int safe)
{
    zc.fb = fb;
    zc.backdrop = backdrop;
    zc.w = w;
    zc.h = h;
    zc.dy = dy;
    zc.safe = safe;
    zc.ox = 0;
    zc.oy = 0;
}

uint16_t zc_blend565(uint16_t dst, uint16_t src, uint8_t alpha)
{
    if(alpha == 0) return dst;
    if(alpha == 255) return src;
    uint32_t a = alpha;
    uint32_t ia = 255U - a;
    uint32_t dr = (dst >> 11) & 0x1FU;
    uint32_t dg = (dst >> 5) & 0x3FU;
    uint32_t db = dst & 0x1FU;
    uint32_t sr = (src >> 11) & 0x1FU;
    uint32_t sg = (src >> 5) & 0x3FU;
    uint32_t sb = src & 0x1FU;
    uint32_t r = (dr * ia + sr * a + 127U) / 255U;
    uint32_t g = (dg * ia + sg * a + 127U) / 255U;
    uint32_t b = (db * ia + sb * a + 127U) / 255U;
    return (uint16_t)((r << 11) | (g << 5) | b);
}

void zc_pixel(int x, int y, uint16_t color)
{
    if((unsigned)x >= (unsigned)zc.w || (unsigned)y >= (unsigned)zc.h) return;
    zc.fb[y * zc.w + x] = color;
}

void zc_blend_pixel(int x, int y, uint16_t color, uint8_t alpha)
{
    if((unsigned)x >= (unsigned)zc.w || (unsigned)y >= (unsigned)zc.h) return;
    uint16_t * p = &zc.fb[y * zc.w + x];
    *p = zc_blend565(*p, color, alpha);
}

void zc_rect(int x, int y, int w, int h, uint16_t color)
{
    int x0 = x < 0 ? 0 : x;
    int y0 = y < 0 ? 0 : y;
    int x1 = x + w > zc.w ? zc.w : x + w;
    int y1 = y + h > zc.h ? zc.h : y + h;
    if(x1 <= x0 || y1 <= y0) return;
    for(int yy = y0; yy < y1; yy++) {
        uint16_t * row = zc.fb + yy * zc.w;
        for(int xx = x0; xx < x1; xx++) row[xx] = color;
    }
}

void zc_blend_rect(int x, int y, int w, int h, uint16_t color, uint8_t alpha)
{
    if(alpha == 0) return;
    int x0 = x < 0 ? 0 : x;
    int y0 = y < 0 ? 0 : y;
    int x1 = x + w > zc.w ? zc.w : x + w;
    int y1 = y + h > zc.h ? zc.h : y + h;
    if(x1 <= x0 || y1 <= y0) return;
    if(alpha == 255) {
        zc_rect(x0, y0, x1 - x0, y1 - y0, color);
        return;
    }
    for(int yy = y0; yy < y1; yy++) {
        uint16_t * row = zc.fb + yy * zc.w;
        for(int xx = x0; xx < x1; xx++) row[xx] = zc_blend565(row[xx], color, alpha);
    }
}

void zc_rect_world(int x, int y, int w, int h, uint16_t color)
{
    zc_rect(x + zc.ox, y + zc.oy, w, h, color);
}

void zc_blend_rect_world(int x, int y, int w, int h, uint16_t color, uint8_t alpha)
{
    zc_blend_rect(x + zc.ox, y + zc.oy, w, h, color, alpha);
}

void zc_clear(uint16_t color)
{
    zc_rect(0, 0, zc.w, zc.h, color);
}

void zc_outline(int x, int y, int w, int h, int thickness, uint16_t color)
{
    zc_rect(x, y, w, thickness, color);
    zc_rect(x, y + h - thickness, w, thickness, color);
    zc_rect(x, y, thickness, h, color);
    zc_rect(x + w - thickness, y, thickness, h, color);
}

void zc_circle(int cx, int cy, int radius, uint16_t color)
{
    if(radius <= 0) return;
    int r2 = radius * radius;
    for(int dy = -radius; dy <= radius; dy++) {
        int rem = r2 - dy * dy;
        if(rem < 0) rem = 0;
        int dx = 0;
        while((dx + 1) * (dx + 1) <= rem) dx++;
        zc_rect(cx - dx, cy + dy, dx * 2 + 1, 1, color);
    }
}

void zc_blend_circle(int cx, int cy, int radius, uint16_t color, uint8_t alpha)
{
    if(radius <= 0 || alpha == 0) return;
    int r2 = radius * radius;
    for(int dy = -radius; dy <= radius; dy++) {
        int rem = r2 - dy * dy;
        if(rem < 0) rem = 0;
        int dx = 0;
        while((dx + 1) * (dx + 1) <= rem) dx++;
        zc_blend_rect(cx - dx, cy + dy, dx * 2 + 1, 1, color, alpha);
    }
}

void zc_line(int x1, int y1, int x2, int y2, int size, uint16_t color)
{
    if(size < 1) size = 1;
    int dx = x2 - x1;
    int dy = y2 - y1;
    int ax = dx < 0 ? -dx : dx;
    int ay = dy < 0 ? -dy : dy;
    int steps = (int)ceilf((float)(ax > ay ? ax : ay) / fmaxf(1.0f, (float)size * 0.55f));
    if(steps < 1) steps = 1;
    for(int i = 0; i <= steps; i++) {
        float t = (float)i / (float)steps;
        int px = (int)lroundf((float)x1 + (float)dx * t - (float)size * 0.5f);
        int py = (int)lroundf((float)y1 + (float)dy * t - (float)size * 0.5f);
        zc_rect(px, py, size, size, color);
    }
}

void zc_line_world(int x1, int y1, int x2, int y2, int size, uint16_t color)
{
    zc_line(x1 + zc.ox, y1 + zc.oy, x2 + zc.ox, y2 + zc.oy, size, color);
}

void zc_chamfer_panel(int x, int y, int w, int h, uint16_t fill, uint16_t border,
                      int cut, uint16_t inner)
{
    zc_rect(x + cut, y, w - cut * 2, h, fill);
    zc_rect(x, y + cut, w, h - cut * 2, fill);
    if(inner != fill) {
        zc_rect(x + cut, y + 4, w - cut * 2, h - 8, inner);
        zc_rect(x + 4, y + cut, w - 8, h - cut * 2, inner);
    }
    zc_rect(x + cut, y, w - cut * 2, 2, border);
    zc_rect(x + cut, y + h - 2, w - cut * 2, 2, border);
    zc_rect(x, y + cut, 2, h - cut * 2, border);
    zc_rect(x + w - 2, y + cut, 2, h - cut * 2, border);
    zc_rect(x + cut - 2, y + 2, 2, 2, border);
    zc_rect(x + w - cut, y + 2, 2, 2, border);
    zc_rect(x + cut - 2, y + h - 4, 2, 2, border);
    zc_rect(x + w - cut, y + h - 4, 2, 2, border);
}

void zc_copy_backdrop(void)
{
    if(zc.backdrop == NULL) return;
    if(zc.ox == 0 && zc.oy == 0) {
        memcpy(zc.fb, zc.backdrop, (size_t)zc.w * (size_t)zc.h * sizeof(uint16_t));
        return;
    }
    zc_clear(ZC_INK);
    for(int y = 0; y < zc.h; y++) {
        int sy = y - zc.oy;
        if(sy < 0 || sy >= zc.h) continue;
        int dx0 = zc.ox < 0 ? -zc.ox : 0;
        int dx1 = zc.w - zc.ox;
        if(dx1 > zc.w) dx1 = zc.w;
        if(dx1 <= dx0) continue;
        memcpy(zc.fb + (size_t)y * zc.w + dx0,
               zc.backdrop + (size_t)sy * zc.w + (dx0 - zc.ox),
               (size_t)(dx1 - dx0) * sizeof(uint16_t));
    }
}


static const zc_glyph5_t * find5(char ch)
{
    if(ch >= 'a' && ch <= 'z') ch = (char)(ch - 'a' + 'A');
    for(size_t i = 0; i < sizeof(zc_font5) / sizeof(zc_font5[0]); i++) {
        if(zc_font5[i].ch == ch) return &zc_font5[i];
    }
    return NULL;
}

int zc_text_width(const char * text, int scale, int spacing)
{
    int n = (int)strlen(text);
    if(n <= 0) return 0;
    return n * 5 * scale + (n - 1) * spacing;
}

void zc_text(const char * text, int x, int y, int scale, uint16_t color,
             zc_align_t align, int spacing)
{
    if(scale < 1) scale = 1;
    if(spacing < 0) spacing = scale;
    int total = zc_text_width(text, scale, spacing);
    int cx = align == ZC_ALIGN_CENTER ? x - total / 2 : align == ZC_ALIGN_RIGHT ? x - total : x;
    for(const char * p = text; *p != '\0'; p++) {
        char ch = *p;
        if(ch >= 'a' && ch <= 'z') ch = (char)(ch - 'a' + 'A');
        const zc_glyph5_t * g = find5(ch);
        if(g == NULL) g = find5('?');
        if(g != NULL) {
            for(int row = 0; row < 7; row++) {
                uint8_t bits = g->rows[row];
                for(int col = 0; col < 5; col++) {
                    if(bits & (uint8_t)(0x10U >> col)) {
                        zc_rect(cx + col * scale, y + row * scale, scale, scale, color);
                    }
                }
            }
        }
        cx += 5 * scale + spacing;
    }
}

void zc_text_shadow(const char * text, int x, int y, int scale, uint16_t color,
                    uint16_t shadow, zc_align_t align, int spacing)
{
    zc_text(text, x + scale, y + scale, scale, shadow, align, spacing);
    zc_text(text, x, y, scale, color, align, spacing);
}

static uint32_t utf8_next(const char ** pp)
{
    const unsigned char * p = (const unsigned char *)*pp;
    uint32_t cp;
    if(p[0] < 0x80U) {
        cp = p[0];
        *pp += 1;
    }
    else if((p[0] & 0xE0U) == 0xC0U && p[1] != 0) {
        cp = ((uint32_t)(p[0] & 0x1FU) << 6) | (p[1] & 0x3FU);
        *pp += 2;
    }
    else if((p[0] & 0xF0U) == 0xE0U && p[1] != 0 && p[2] != 0) {
        cp = ((uint32_t)(p[0] & 0x0FU) << 12) | ((uint32_t)(p[1] & 0x3FU) << 6) | (p[2] & 0x3FU);
        *pp += 3;
    }
    else if((p[0] & 0xF8U) == 0xF0U && p[1] != 0 && p[2] != 0 && p[3] != 0) {
        cp = ((uint32_t)(p[0] & 0x07U) << 18) | ((uint32_t)(p[1] & 0x3FU) << 12) |
             ((uint32_t)(p[2] & 0x3FU) << 6) | (p[3] & 0x3FU);
        *pp += 4;
    }
    else {
        cp = '?';
        *pp += 1;
    }
    return cp;
}

int zc_cn_width(const char * text, int size)
{
    int total = 0;
    const char * p = text;
    while(*p != '\0') {
        uint32_t cp = utf8_next(&p);
        const zc_glyph_t * g = zc_cjk_lookup(cp, size);
        total += g != NULL ? g->adv : size;
    }
    return total;
}

static void draw_cjk_bitmap(const zc_glyph_t * g, int x, int y, uint16_t color)
{
    if(g == NULL || g->w == 0 || g->h == 0) return;
    const uint8_t * bits = zc_cjk_bits() + g->data_off;
    int stride = (g->w + 7) / 8;
    for(int row = 0; row < g->h; row++) {
        for(int col = 0; col < g->w; col++) {
            if(bits[row * stride + (col >> 3)] & (uint8_t)(0x80U >> (col & 7))) {
                zc_pixel(x + col, y + row, color);
            }
        }
    }
}

void zc_cn_text(const char * text, int x, int y, int size, uint16_t color,
                zc_align_t align, bool shadow)
{
    int total = zc_cn_width(text, size);
    int cx = align == ZC_ALIGN_CENTER ? x - total / 2 : align == ZC_ALIGN_RIGHT ? x - total : x;
    if(shadow) {
        int sx = cx;
        const char * p = text;
        while(*p != '\0') {
            uint32_t cp = utf8_next(&p);
            const zc_glyph_t * g = zc_cjk_lookup(cp, size);
            if(g != NULL) {
                draw_cjk_bitmap(g, sx + g->xoff + 1, y + g->yoff + 2, ZC_RGB565(3, 6, 3));
                sx += g->adv;
            }
            else {
                sx += size;
            }
        }
    }
    const char * p = text;
    while(*p != '\0') {
        uint32_t cp = utf8_next(&p);
        const zc_glyph_t * g = zc_cjk_lookup(cp, size);
        if(g != NULL) {
            draw_cjk_bitmap(g, cx + g->xoff, y + g->yoff, color);
            cx += g->adv;
        }
        else {
            zc_outline(cx, y + 2, size, size, 1, color);
            cx += size;
        }
    }
}

void zc_heart(int x, int y, bool filled, int scale, bool flash)
{
    static const char * rows[5] = {".X.X.", "XXXXX", "XXXXX", ".XXX.", "..X.."};
    uint16_t body = flash ? ZC_WHITE : filled ? ZC_RED : ZC_RGB565(53, 39, 29);
    uint16_t shade = flash ? ZC_BONE : filled ? ZC_RED_D : ZC_RGB565(32, 24, 18);
    for(int r = 0; r < 5; r++) {
        for(int c = 0; c < 5; c++) {
            if(rows[r][c] != 'X') continue;
            uint16_t col = (r == 4 || (r == 3 && (c == 0 || c == 4))) ? shade : body;
            zc_rect(x + c * scale, y + r * scale, scale, scale, col);
        }
    }
    if(filled && !flash) {
        zc_rect(x + 2 * scale, y + 1 * scale, scale, scale, ZC_RGB565(245, 154, 99));
    }
}
