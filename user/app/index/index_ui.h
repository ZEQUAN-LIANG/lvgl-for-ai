#ifndef INDEX_UI_H
#define INDEX_UI_H

#include "lvgl.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

typedef enum {
    IDX_F_DISP_14 = 0,
    IDX_F_DISP_15,
    IDX_F_DISP_16,
    IDX_F_DISP_18,
    IDX_F_DISP_20,
    IDX_F_DISP_21,
    IDX_F_DISP_22,
    IDX_F_DISP_23,
    IDX_F_DISP_27,
    IDX_F_DISP_36,
    IDX_F_DISP_42,
    IDX_F_BODY_9,
    IDX_F_BODY_9B,
    IDX_F_BODY_10,
    IDX_F_BODY_11,
    IDX_F_BODY_11B,
    IDX_F_BODY_12,
    IDX_F_BODY_13,
    IDX_F_BODY_13B,
    IDX_F_BODY_14,
    IDX_F_BODY_15,
    IDX_F_MONO_6,
    IDX_F_MONO_6B,
    IDX_F_MONO_7,
    IDX_F_MONO_8,
    IDX_F_MONO_9,
    IDX_F_MONO_9B,
    IDX_F_MONO_10,
    IDX_F_MONO_11,
    IDX_F_SYMBOL_6,
    IDX_F_SYMBOL_7,
    IDX_F_SYMBOL_8,
    IDX_F_SYMBOL_9,
    IDX_F_SYMBOL_10,
    IDX_F_SYMBOL_11,
    IDX_F_SYMBOL_12,
    IDX_F_COUNT
} idx_font_id_t;

typedef enum {
    IDX_ACT_NONE = 0,
    IDX_ACT_SCREEN_OVERVIEW,
    IDX_ACT_SCREEN_LOOP,
    IDX_ACT_SCREEN_EVIDENCE,
    IDX_ACT_SCREEN_INSPECTOR,
    IDX_ACT_SCREEN_VERSIONS,
    IDX_ACT_SCREEN_START,
    IDX_ACT_LOG
} idx_action_t;

typedef enum {
    IDX_TAG_NONE = 0,
    IDX_TAG_EYEBROW,
    IDX_TAG_LED_RED,
    IDX_TAG_LED_GREEN,
    IDX_TAG_LED_CYAN
} idx_tag_t;

typedef struct {
    const char * text;
    uint8_t font;
} idx_seg_t;

typedef struct {
    uint8_t type;          /* 0 = box, 1 = image */
    uint8_t action;
    uint8_t tag;
    uint8_t opa;
    int16_t x;
    int16_t y;
    uint16_t w;
    uint16_t h;
    uint32_t bg;
    uint32_t grad;
    uint32_t border;
    uint32_t shadow;
    uint8_t bg_opa;
    uint8_t grad_dir;
    uint8_t border_opa;
    uint8_t border_w;
    uint16_t radius;
    uint8_t shadow_opa;
    uint8_t shadow_w;
    int16_t shadow_ofs_y;
    int16_t shadow_spread;
    const void * src;
} idx_bg_t;

typedef struct {
    int16_t x;
    int16_t y;
    uint16_t w;        /* target line width */
    uint16_t clip_w;   /* visible width when clipped; 0 = no clip */
    const idx_seg_t * segs;
    uint8_t seg_count;
    uint32_t color;
    uint8_t opa;
    int8_t letter_space;
    uint8_t flags;     /* bit 0: ellipsis, bit 1: clipped */
} idx_text_t;

typedef struct {
    const idx_bg_t * bgs;
    uint16_t bg_count;
    const idx_text_t * texts;
    uint16_t text_count;
    uint16_t content_h;
} idx_screen_t;

void idx_ui_create(void);

/* Shared helpers used by the hand-written dynamic screens. */
lv_font_t * idx_font(idx_font_id_t id);
lv_obj_t * idx_text_line(lv_obj_t * parent, int32_t x, int32_t y,
                          const idx_seg_t * segs, uint8_t seg_count,
                          uint32_t color, uint8_t opa, int8_t letter_space,
                          uint16_t target_w, uint16_t clip_w, uint8_t flags);
lv_obj_t * idx_box(lv_obj_t * parent, int32_t x, int32_t y, int32_t w, int32_t h,
                    uint32_t bg, uint8_t bg_opa, uint32_t border,
                    uint8_t border_opa, uint8_t border_w, uint16_t radius,
                    uint8_t opa);
void idx_show_screen(uint8_t screen, bool animate);
void idx_set_tab_focus(uint8_t screen);
void idx_action_attach(lv_obj_t * obj, uint8_t action);

#endif /* LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6 */

#endif /* INDEX_UI_H */
