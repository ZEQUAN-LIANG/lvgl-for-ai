#ifndef INTRO_UI_H
#define INTRO_UI_H

#include "lvgl.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

typedef enum {
    INTRO_F_DISP_14 = 0,
    INTRO_F_DISP_15,
    INTRO_F_DISP_16,
    INTRO_F_DISP_18,
    INTRO_F_DISP_20,
    INTRO_F_DISP_21,
    INTRO_F_DISP_22,
    INTRO_F_DISP_23,
    INTRO_F_DISP_27,
    INTRO_F_DISP_36,
    INTRO_F_DISP_42,
    INTRO_F_BODY_9,
    INTRO_F_BODY_9B,
    INTRO_F_BODY_10,
    INTRO_F_BODY_11,
    INTRO_F_BODY_11B,
    INTRO_F_BODY_12,
    INTRO_F_BODY_13,
    INTRO_F_BODY_13B,
    INTRO_F_BODY_14,
    INTRO_F_BODY_15,
    INTRO_F_MONO_6,
    INTRO_F_MONO_6B,
    INTRO_F_MONO_7,
    INTRO_F_MONO_8,
    INTRO_F_MONO_9,
    INTRO_F_MONO_9B,
    INTRO_F_MONO_10,
    INTRO_F_MONO_11,
    INTRO_F_SYMBOL_6,
    INTRO_F_SYMBOL_7,
    INTRO_F_SYMBOL_8,
    INTRO_F_SYMBOL_9,
    INTRO_F_SYMBOL_10,
    INTRO_F_SYMBOL_11,
    INTRO_F_SYMBOL_12,
    INTRO_F_COUNT
} intro_font_id_t;

typedef enum {
    INTRO_ACT_NONE = 0,
    INTRO_ACT_SCREEN_OVERVIEW,
    INTRO_ACT_SCREEN_LOOP,
    INTRO_ACT_SCREEN_EVIDENCE,
    INTRO_ACT_SCREEN_INSPECTOR,
    INTRO_ACT_SCREEN_VERSIONS,
    INTRO_ACT_SCREEN_START,
    INTRO_ACT_LOG
} intro_action_t;

typedef enum {
    INTRO_TAG_NONE = 0,
    INTRO_TAG_EYEBROW,
    INTRO_TAG_LED_RED,
    INTRO_TAG_LED_GREEN,
    INTRO_TAG_LED_CYAN
} intro_tag_t;

typedef struct {
    const char * text;
    uint8_t font;
} intro_seg_t;

typedef struct {
    uint8_t type;
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
} intro_bg_t;

typedef struct {
    int16_t x;
    int16_t y;
    uint16_t w;
    uint16_t clip_w;
    const intro_seg_t * segs;
    uint8_t seg_count;
    uint32_t color;
    uint8_t opa;
    int8_t letter_space;
    uint8_t flags;
} intro_text_t;

typedef struct {
    const intro_bg_t * bgs;
    uint16_t bg_count;
    const intro_text_t * texts;
    uint16_t text_count;
    uint16_t content_h;
} intro_screen_t;

void intro_ui_create(void);

lv_font_t * intro_font(intro_font_id_t id);
lv_obj_t * intro_text_line(lv_obj_t * parent, int32_t x, int32_t y,
                          const intro_seg_t * segs, uint8_t seg_count,
                          uint32_t color, uint8_t opa, int8_t letter_space,
                          uint16_t target_w, uint16_t clip_w, uint8_t flags);
lv_obj_t * intro_box(lv_obj_t * parent, int32_t x, int32_t y, int32_t w, int32_t h,
                    uint32_t bg, uint8_t bg_opa, uint32_t border,
                    uint8_t border_opa, uint8_t border_w, uint16_t radius,
                    uint8_t opa);
void intro_show_screen(uint8_t screen, bool animate);
void intro_set_tab_focus(uint8_t screen);
void intro_action_attach(lv_obj_t * obj, uint8_t action);

#endif

#endif
