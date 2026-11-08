/**
 * @file demo_assets.h
 * Demo assets referenced by the user/app C files as C arrays.
 *
 * No asset pipeline yet: the font and the image live in this header and are
 * compiled into the app TU that includes it.
 */

#ifndef DEMO_ASSETS_H
#define DEMO_ASSETS_H

#include "lvgl.h"
#include "lvgl_compat.h"

/* ---- image: 16x16 RGB565 checker ------------------------------------- */

#define DEMO_ASSET_LOGO_SIZE 16

static const uint16_t demo_asset_logo_pixels[DEMO_ASSET_LOGO_SIZE * DEMO_ASSET_LOGO_SIZE] = {
    0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0,
    0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0,
    0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0,
    0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0,
    0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800,
    0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800,
    0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800,
    0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800,
    0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0,
    0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0,
    0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0,
    0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0,
    0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800,
    0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800,
    0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800,
    0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800, 0x07E0, 0x07E0, 0x07E0, 0x07E0, 0xF800, 0xF800, 0xF800, 0xF800,
};

#if LVGL_VERSION_MAJOR >= 9
static const lv_image_dsc_t demo_asset_logo = {
    .header = {
        .magic = LV_IMAGE_HEADER_MAGIC,
        .cf = LV_COLOR_FORMAT_RGB565,
        .flags = 0,
        .w = DEMO_ASSET_LOGO_SIZE,
        .h = DEMO_ASSET_LOGO_SIZE,
        .stride = DEMO_ASSET_LOGO_SIZE * 2,
        .reserved_2 = 0,
    },
    .data_size = sizeof(demo_asset_logo_pixels),
    .data = (const uint8_t *)demo_asset_logo_pixels,
};

static inline void demo_asset_prepare(void)
{
}
#else
/* 8.x has no lv_image_dsc_t and its TRUE_COLOR images use the display color
 * depth. The engine runs 8.x at LV_COLOR_DEPTH 32, so convert the same RGB565
 * checker into a 32-bit lv_color_t array once at app startup. */
static lv_color_t demo_asset_logo_pixels_8x[DEMO_ASSET_LOGO_SIZE * DEMO_ASSET_LOGO_SIZE];

static inline void demo_asset_prepare(void)
{
    for(size_t i = 0; i < DEMO_ASSET_LOGO_SIZE * DEMO_ASSET_LOGO_SIZE; i++) {
        uint16_t px = demo_asset_logo_pixels[i];
        uint8_t r = (uint8_t)(((px >> 11) & 0x1Fu) * 255u / 31u);
        uint8_t g = (uint8_t)(((px >> 5) & 0x3Fu) * 255u / 63u);
        uint8_t b = (uint8_t)((px & 0x1Fu) * 255u / 31u);
        demo_asset_logo_pixels_8x[i] = lv_color_make(r, g, b);
    }
}

static const lv_img_dsc_t demo_asset_logo = {
    .header = {
        .cf = LV_IMG_CF_TRUE_COLOR,
        .w = DEMO_ASSET_LOGO_SIZE,
        .h = DEMO_ASSET_LOGO_SIZE,
    },
    .data_size = sizeof(demo_asset_logo_pixels_8x),
    .data = (const uint8_t *)demo_asset_logo_pixels_8x,
};
#endif

/* ---- font: 5x7 1bpp glyphs for the demo title --------------------------------- */

static const uint8_t demo_asset_font_bitmap[] = {
    /* A */ 0x70, 0x88, 0x88, 0xF8, 0x88, 0x88, 0x88,
    /* L */ 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0xF8,
    /* T */ 0xF8, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20,
};

static const lv_font_fmt_txt_glyph_dsc_t demo_asset_font_glyphs[] = {
    {.bitmap_index = 0, .adv_w = 0, .box_w = 0, .box_h = 0, .ofs_x = 0, .ofs_y = 0},
    {.bitmap_index = 0, .adv_w = 32, .box_w = 0, .box_h = 0, .ofs_x = 0, .ofs_y = 0},
    {.bitmap_index = 0, .adv_w = 80, .box_w = 5, .box_h = 7, .ofs_x = 0, .ofs_y = 1},
    {.bitmap_index = 7, .adv_w = 80, .box_w = 5, .box_h = 7, .ofs_x = 0, .ofs_y = 1},
    {.bitmap_index = 14, .adv_w = 80, .box_w = 5, .box_h = 7, .ofs_x = 0, .ofs_y = 1},
};

/* Relative code points (letter - 0x20), sorted: space, 'A', 'L', 'T'. */
static const uint16_t demo_asset_font_unicode[] = {0x00, 0x21, 0x2C, 0x34};

static const lv_font_fmt_txt_cmap_t demo_asset_font_cmaps[] = {
    {
        .range_start = 0x20,
        .range_length = 0x35,
        .glyph_id_start = 1,
        .unicode_list = demo_asset_font_unicode,
        .glyph_id_ofs_list = NULL,
        .list_length = 4,
        .type = LV_FONT_FMT_TXT_CMAP_SPARSE_TINY,
    },
};

static const lv_font_fmt_txt_dsc_t demo_asset_font_dsc = {
    .glyph_bitmap = demo_asset_font_bitmap,
    .glyph_dsc = demo_asset_font_glyphs,
    .cmaps = demo_asset_font_cmaps,
    .kern_dsc = NULL,
    .kern_scale = 0,
    .cmap_num = 1,
    .bpp = 1,
    .kern_classes = 0,
    .bitmap_format = LV_FONT_FMT_TXT_PLAIN,
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 5
    .stride = 1,
#endif
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
    .are_glyphs_dynamic_loaded = false,
#endif
};

static const lv_font_t demo_asset_font_8 = {
    .dsc = &demo_asset_font_dsc,
    .fallback = NULL,
    .user_data = NULL,
    .get_glyph_dsc = lv_font_get_glyph_dsc_fmt_txt,
    .get_glyph_bitmap = lv_font_get_bitmap_fmt_txt,
#if LVGL_VERSION_MAJOR >= 9
    .release_glyph = NULL,
#endif
    .line_height = 8,
    .base_line = 1,
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
    .cap_height = 7,
    .x_height = 5,
#endif
    .subpx = LV_FONT_SUBPX_NONE,
#if LVGL_VERSION_MAJOR >= 9
    .kerning = LV_FONT_KERNING_NONE,
#endif
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 5
    .static_bitmap = 0,
#endif
    .underline_position = -1,
    .underline_thickness = 0,
};

#endif /* DEMO_ASSETS_H */
