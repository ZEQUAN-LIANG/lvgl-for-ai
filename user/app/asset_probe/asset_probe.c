#include "asset_probe.h"

#include "app.h"
#include "probe_font_bpp1.h"
#include "probe_font_bpp2.h"
#include "probe_font_bpp4.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR < 3
/* LVGL 9.1/9.2 cannot render plain 8 bpp glyphs. */
#define PROBE_HAS_BPP8 0
#else
#include "probe_font_bpp8.h"
#define PROBE_HAS_BPP8 1
#endif

#if LVGL_VERSION_MAJOR >= 9
#include "probe_img_argb.h"
#include "probe_img_rgb565.h"
#include "probe_img_rgb888.h"
#include "probe_img_a8.h"
#define PROBE_IMG_ARGB (&probe_img_argb)
#define PROBE_IMG_RGB565 (&probe_img_rgb565)
#define PROBE_IMG_RGB888 (&probe_img_rgb888)
#define PROBE_IMG_A8 (&probe_img_a8)
#else
#include "probe_img_argb_v8.h"
#include "probe_img_rgb565_v8.h"
#include "probe_img_rgb888_v8.h"
#include "probe_img_a8_v8.h"
#define PROBE_IMG_ARGB (&probe_img_argb_v8)
#define PROBE_IMG_RGB565 (&probe_img_rgb565_v8)
#define PROBE_IMG_RGB888 (&probe_img_rgb888_v8)
#define PROBE_IMG_A8 (&probe_img_a8_v8)
#endif

#include <stdio.h>
#include <string.h>

#define PROBE_LOG_FONT(tag, font)                                              \
    printf("[asset_probe] font %s=%p lh=%d bl=%d\n", tag, (void *)&(font),     \
           (int)(font).line_height, (int)(font).base_line)

#define PROBE_LOG_IMAGE(tag, dsc)                                              \
    printf("[asset_probe] image %s=%p w=%d h=%d cf=%d size=%u\n", tag,         \
           (void *)(dsc), (int)(dsc)->header.w, (int)(dsc)->header.h,          \
           (int)(dsc)->header.cf, (unsigned)(dsc)->data_size)

static void asset_probe_click_cb(lv_event_t * event)
{
    lv_obj_t * status = lv_event_get_user_data(event);
    lv_label_set_text(status, "已点击 / clicked");
    printf("[asset_probe] clicked\n");
}

#if LV_USE_FREETYPE
static void asset_probe_freetype_delete_cb(lv_event_t * event)
{
    lv_font_t * font = lv_event_get_user_data(event);
#if LVGL_VERSION_MAJOR >= 9
    lv_freetype_font_delete(font);
#else
    lv_ft_font_destroy(font);
#endif
}

static lv_font_t * asset_probe_freetype_font(void)
{
    const char * path = "C:\\Windows\\Fonts\\Deng.ttf";
#if LVGL_VERSION_MAJOR >= 9
    /* 9.x initializes FreeType from lv_init(). */
    return lv_freetype_font_create(path, LV_FREETYPE_FONT_RENDER_MODE_BITMAP,
                                   20, LV_FREETYPE_FONT_STYLE_NORMAL);
#else
    static bool initialized = false;
    if(!initialized) {
        initialized = lv_freetype_init(0, 0, 0);
    }
    if(!initialized) {
        return NULL;
    }
    lv_ft_info_t info;
    memset(&info, 0, sizeof(info));
    info.name = path;
    info.weight = 20;
    info.style = FT_FONT_STYLE_NORMAL;
    if(!lv_ft_font_init(&info)) {
        return NULL;
    }
    return info.font;
#endif
}
#endif

static void asset_probe_card(lv_obj_t * parent, lv_coord_t x, const void * src,
                             const char * caption, bool recolor)
{
    lv_obj_t * card = lv_obj_create(parent);
    lv_obj_set_size(card, 88, 88);
    lv_obj_set_pos(card, x, 118);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x1E242C), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(card, 1, 0);
    lv_obj_set_style_border_color(card, lv_color_hex(0x39424D), 0);
    lv_obj_set_style_radius(card, 8, 0);
    lv_obj_set_style_pad_all(card, 12, 0);
    app_obj_set_scrollable(card, false);

    lv_obj_t * image = lv_image_create(card);
    lv_image_set_src(image, src);
    lv_obj_center(image);
    if(recolor) {
        app_image_set_recolor(image, lv_color_hex(0xFFB74D), LV_OPA_COVER);
    }

    lv_obj_t * label = lv_label_create(parent);
    lv_label_set_text(label, caption);
    lv_obj_set_style_text_color(label, lv_color_hex(0x9AA3AD), 0);
    lv_obj_align_to(label, card, LV_ALIGN_OUT_BOTTOM_MID, 0, 6);
}

void asset_probe_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    app_set_name("asset_probe");
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101318), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    lv_obj_t * title = lv_label_create(screen);
    lv_label_set_text(title, "资源格式 / BPP 探针");
    lv_obj_set_style_text_font(title, &probe_font_bpp4, 0);
    lv_obj_set_style_text_color(title, lv_color_hex(0xE6E8EB), 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 10);
    app_obj_set_name(title, "asset_probe_title");

    const lv_font_t * const bpp_fonts[] = {
        &probe_font_bpp1,
        &probe_font_bpp2,
        &probe_font_bpp4,
#if PROBE_HAS_BPP8
        &probe_font_bpp8,
#else
        &probe_font_bpp4,
#endif
    };
    const char * const bpp_texts[] = {
        "BPP1 Aa 你好",
        "BPP2 Aa 你好",
        "BPP4 Aa 你好",
#if PROBE_HAS_BPP8
        "BPP8 Aa 你好",
#else
        "BPP8 N/A (< 9.3)",
#endif
    };
    const char * const bpp_names[] = {
        "asset_probe_bpp1",
        "asset_probe_bpp2",
        "asset_probe_bpp4",
        "asset_probe_bpp8",
    };
    int index;
    for(index = 0; index < 4; index++) {
        lv_obj_t * label = lv_label_create(screen);
        lv_label_set_text(label, bpp_texts[index]);
        lv_obj_set_style_text_font(label, bpp_fonts[index], 0);
        lv_obj_set_style_text_color(label, lv_color_hex(0xDDE3EA), 0);
        lv_obj_set_pos(label, 24 + index * 196, 56);
        app_obj_set_name(label, bpp_names[index]);
    }

    asset_probe_card(screen, 24, PROBE_IMG_ARGB, "ARGB8888", false);
    asset_probe_card(screen, 220, PROBE_IMG_RGB565, "RGB565", false);
    asset_probe_card(screen, 416, PROBE_IMG_RGB888, "RGB888", false);
    asset_probe_card(screen, 612, PROBE_IMG_A8, "A8 (recolor)", true);

#if LV_USE_FREETYPE
    lv_obj_t * freetype_label = lv_label_create(screen);
    lv_font_t * freetype_font = asset_probe_freetype_font();
    if(freetype_font != NULL) {
        lv_label_set_text(freetype_label, "FreeType: 你好 TTF");
        lv_obj_set_style_text_font(freetype_label, freetype_font, 0);
        lv_obj_add_event_cb(screen, asset_probe_freetype_delete_cb,
                            LV_EVENT_DELETE, freetype_font);
        printf("[asset_probe] freetype font=%p line_height=%d\n",
               (void *)freetype_font, (int)freetype_font->line_height);
    }
    else {
        lv_label_set_text(freetype_label, "FreeType: FAIL");
        printf("[asset_probe] freetype failed\n");
    }
    lv_obj_set_style_text_color(freetype_label, lv_color_hex(0x7FD1FF), 0);
    lv_obj_align(freetype_label, LV_ALIGN_TOP_MID, 0, 250);
    app_obj_set_name(freetype_label, "asset_probe_freetype");
#endif

    lv_obj_t * button = lv_button_create(screen);
    lv_obj_set_size(button, 220, 48);
    lv_obj_align(button, LV_ALIGN_CENTER, 0, 30);
    app_obj_set_name(button, "asset_probe_button");

    lv_obj_t * button_label = lv_label_create(button);
    lv_label_set_text(button_label, "点击 CLICK");
    lv_obj_set_style_text_font(button_label, &probe_font_bpp4, 0);
    lv_obj_center(button_label);
    app_obj_set_name(button_label, "asset_probe_button_label");

    lv_obj_t * status = lv_label_create(screen);
    lv_label_set_text(status, "你好，世界");
    lv_obj_set_style_text_font(status, &probe_font_bpp4, 0);
    lv_obj_set_style_text_color(status, lv_color_hex(0x9AA3AD), 0);
    lv_obj_align(status, LV_ALIGN_CENTER, 0, 110);
    app_obj_set_name(status, "asset_probe_status");

    lv_obj_add_event_cb(button, asset_probe_click_cb, LV_EVENT_CLICKED, status);

    char version_text[48];
    snprintf(version_text, sizeof(version_text), "LVGL %d.%d  assets probe",
             LVGL_VERSION_MAJOR, LVGL_VERSION_MINOR);
    lv_obj_t * version = lv_label_create(screen);
    lv_label_set_text(version, version_text);
    lv_obj_set_style_text_color(version, lv_color_hex(0x6B7480), 0);
    lv_obj_align(version, LV_ALIGN_BOTTOM_MID, 0, -12);
    app_obj_set_name(version, "asset_probe_version");

    PROBE_LOG_FONT("bpp1", probe_font_bpp1);
    PROBE_LOG_FONT("bpp2", probe_font_bpp2);
    PROBE_LOG_FONT("bpp4", probe_font_bpp4);
#if PROBE_HAS_BPP8
    PROBE_LOG_FONT("bpp8", probe_font_bpp8);
#else
    printf("[asset_probe] font bpp8=unavailable (LVGL %d.%d)\n",
           LVGL_VERSION_MAJOR, LVGL_VERSION_MINOR);
#endif
    PROBE_LOG_IMAGE("argb", PROBE_IMG_ARGB);
    PROBE_LOG_IMAGE("rgb565", PROBE_IMG_RGB565);
    PROBE_LOG_IMAGE("rgb888", PROBE_IMG_RGB888);
    PROBE_LOG_IMAGE("a8", PROBE_IMG_A8);
    printf("[asset_probe] created\n");
}
