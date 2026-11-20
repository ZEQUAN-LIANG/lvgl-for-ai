
#ifndef XHS_UI_H
#define XHS_UI_H

#include "lvgl.h"
#include "xhs_texts.h"

#include <stdbool.h>
#include <stdint.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#define XHS_SCREEN_W   304
#define XHS_SCREEN_H   564
#define XHS_STATUS_H   24
#define XHS_NAV_H      46
#define XHS_TAB_HOST_H (XHS_SCREEN_H - XHS_STATUS_H - XHS_NAV_H)
#define XHS_OVERLAY_H  (XHS_SCREEN_H - XHS_STATUS_H)
#define XHS_COVER_W    138

#define XHS_RED      0xFF2442
#define XHS_DARK_RED 0xD91B37
#define XHS_TEXT     0x1F1F21
#define XHS_TITLE    0x262626
#define XHS_MUTED    0x8A8A8E
#define XHS_META     0x9A9A9E
#define XHS_AUTHOR   0x747478
#define XHS_LINE     0xF1F1F3
#define XHS_SOFT     0xF6F6F8
#define XHS_WHITE    0xFFFFFF
#define XHS_YELLOW   0xF5B942

typedef enum {
    XHS_FT_11,
    XHS_FT_12,
    XHS_FT_12B,
    XHS_FT_13,
    XHS_FT_14,
    XHS_FT_14B,
} xhs_font_id_t;

typedef enum {
    XHS_ICON_SEARCH,
    XHS_ICON_HEART_OUTLINE,
    XHS_ICON_HEART_FILLED,
    XHS_ICON_CHEVRON,
    XHS_ICON_PLUS,
    XHS_ICON_PLAY,
    XHS_ICON_BACK,
    XHS_ICON_MORE,
    XHS_ICON_COMMENT,
    XHS_ICON_STAR,
    XHS_ICON_STAR_FILLED,
    XHS_ICON_LOCATION,
    XHS_ICON_CLOSE,
    XHS_ICON_PLANE,
    XHS_ICON_SIGNAL,
    XHS_ICON_WIFI,
    XHS_ICON_BATTERY,
    XHS_ICON_CHECK,
} xhs_icon_id_t;

typedef struct {
    const char * title;
    const char * author;
    const char * avatar;
    const char * body;
    const char * tag;
    const char * location;
    const char * distance;
    int cover_index;
    uint32_t avatar_color;
    int likes;
    int collects;
    bool liked;
    bool collected;
    bool following;
    lv_obj_t * like_icon;
    lv_obj_t * like_label;
} xhs_note_t;

#define XHS_NOTE_COUNT 6
extern xhs_note_t xhs_notes[XHS_NOTE_COUNT];

const lv_font_t * xhs_font(xhs_font_id_t id);
const lv_image_dsc_t * xhs_icon(xhs_icon_id_t id);
const lv_image_dsc_t * xhs_cover(int index);
int xhs_cover_height(int index);

lv_obj_t * xhs_box(lv_obj_t * parent, int x, int y, int w, int h);
lv_obj_t * xhs_label(lv_obj_t * parent, const char * text, xhs_font_id_t font,
                     uint32_t color);
lv_obj_t * xhs_label_at(lv_obj_t * parent, const char * text,
                        xhs_font_id_t font, uint32_t color, int x, int y, int w,
                        int h);
lv_obj_t * xhs_image(lv_obj_t * parent, xhs_icon_id_t icon, int x, int y);
lv_obj_t * xhs_cover_thumb(lv_obj_t * parent, int cover_index, int x, int y,
                           int w, int h, int radius);
lv_obj_t * xhs_cover_scaled(lv_obj_t * parent, int cover_index, int scale_pct,
                            int center_x, int top_y);
lv_obj_t * xhs_avatar(lv_obj_t * parent, int x, int y, int size, uint32_t color,
                      const char * text, xhs_font_id_t font);
lv_obj_t * xhs_pill(lv_obj_t * parent, int x, int y, int w, int h, uint32_t bg,
                    const char * text, xhs_font_id_t font, uint32_t fg,
                    int radius);
lv_obj_t * xhs_page(lv_obj_t * parent);
lv_obj_t * xhs_root_page(lv_obj_t * parent);
lv_obj_t * xhs_scroll(lv_obj_t * parent, int x, int y, int w, int h);
void xhs_clickable(lv_obj_t * obj, const char * name);
void xhs_set_hidden(lv_obj_t * obj, bool hidden);
void xhs_back_event_cb(lv_event_t * event);

void xhs_show_root(int index);
void xhs_open_overlay(lv_obj_t * page);
void xhs_close_overlay(void);
lv_obj_t * xhs_overlay_host(void);

lv_obj_t * xhs_home_create(lv_obj_t * parent);
lv_obj_t * xhs_market_create(lv_obj_t * parent);
lv_obj_t * xhs_messages_create(lv_obj_t * parent);
lv_obj_t * xhs_profile_create(lv_obj_t * parent);
void xhs_note_open(int index);
void xhs_home_sync_likes(void);
void xhs_publish_open(void);

#endif

#endif
