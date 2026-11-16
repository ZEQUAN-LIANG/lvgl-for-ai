#ifndef ZC_GFX_H
#define ZC_GFX_H

#include "zc_priv.h"

void zc_gfx_bind(uint16_t * fb, uint16_t * backdrop, int w, int h, int dy,
                 int safe);

void zc_clear(uint16_t color);
void zc_pixel(int x, int y, uint16_t color);
void zc_blend_pixel(int x, int y, uint16_t color, uint8_t alpha);
void zc_rect(int x, int y, int w, int h, uint16_t color);
void zc_blend_rect(int x, int y, int w, int h, uint16_t color, uint8_t alpha);
void zc_rect_world(int x, int y, int w, int h, uint16_t color);
void zc_blend_rect_world(int x, int y, int w, int h, uint16_t color,
                         uint8_t alpha);
void zc_outline(int x, int y, int w, int h, int thickness, uint16_t color);
void zc_circle(int cx, int cy, int radius, uint16_t color);
void zc_blend_circle(int cx, int cy, int radius, uint16_t color, uint8_t alpha);
void zc_line(int x1, int y1, int x2, int y2, int size, uint16_t color);
void zc_line_world(int x1, int y1, int x2, int y2, int size, uint16_t color);
void zc_chamfer_panel(int x, int y, int w, int h, uint16_t fill,
                      uint16_t border, int cut, uint16_t inner);

void zc_copy_backdrop(void);
uint16_t zc_blend565(uint16_t dst, uint16_t src, uint8_t alpha);

int zc_text_width(const char * text, int scale, int spacing);
void zc_text(const char * text, int x, int y, int scale, uint16_t color,
             zc_align_t align, int spacing);
void zc_text_shadow(const char * text, int x, int y, int scale, uint16_t color,
                    uint16_t shadow, zc_align_t align, int spacing);

int zc_cn_width(const char * text, int size);
void zc_cn_text(const char * text, int x, int y, int size, uint16_t color,
                zc_align_t align, bool shadow);

void zc_heart(int x, int y, bool filled, int scale, bool flash);

#endif
