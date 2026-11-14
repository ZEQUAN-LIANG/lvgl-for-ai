#include "index_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include "app.h"
#include "index_layout.h"

#include <stdio.h>
#include <string.h>

#define IDX_W 800
#define IDX_H 600
#define IDX_APPBAR 60
#define IDX_TABBAR 48
#define IDX_STATUSBAR 26
#define IDX_WORKSPACE_Y (IDX_APPBAR + IDX_TABBAR)
#define IDX_WORKSPACE_H (IDX_H - IDX_WORKSPACE_Y - IDX_STATUSBAR)

#define COL_BG       0x05080c
#define COL_BG_TOP   0x08111a
#define COL_BG_BOT   0x060a0f
#define COL_LINE     0x182734
#define COL_LINE_2   0x223746
#define COL_LINE_3   0x2c4658
#define COL_TEXT     0xe8f1f8
#define COL_TEXT_SOFT 0xb4c5d2
#define COL_MUTED    0x8ea3b3
#define COL_DIM      0x6b8091
#define COL_CYAN     0x38bdf8
#define COL_CYAN_2   0x0ea5e9
#define COL_CYAN_SOFT 0x7dd3fc
#define COL_GREEN    0x34d399
#define COL_AMBER    0xfbbf24
#define COL_RED      0xfb7185
#define COL_INK      0x041019

static lv_font_t * idx_fonts[IDX_F_COUNT];
static const idx_screen_t * idx_screens[6] = {
    &idx_screen_overview,
    &idx_screen_loop,
    &idx_screen_evidence,
    &idx_screen_inspector,
    &idx_screen_versions,
    &idx_screen_start,
};
static lv_obj_t * idx_contents[6];
static lv_obj_t * idx_tabs[6];
static lv_obj_t * idx_tab_nums[6];
static lv_obj_t * idx_tab_names[6];
static lv_obj_t * idx_tab_lines[6];
static lv_obj_t * idx_workspace;
static lv_group_t * idx_group;
static uint8_t idx_current = 255;

typedef struct {
    const char * number;
    const char * name;
    int16_t x;
    int16_t w;
    int16_t num_x;
    int16_t num_w;
    int16_t name_x;
    int16_t name_w;
} idx_tab_spec_t;

static const idx_tab_spec_t idx_tab_specs[6] = {
    {"01", "OVERVIEW",  24, 91,  40, 11,  57, 42},
    {"02", "LOOP",     115, 70, 131, 11, 147, 21},
    {"03", "EVIDENCE", 184, 91, 200, 11, 217, 42},
    {"04", "INSPECTOR",275, 96, 291, 11, 308, 47},
    {"05", "VERSIONS", 371, 91, 387, 11, 404, 42},
    {"06", "START",    462, 75, 478, 11, 494, 26},
};

/* --------------------------------------------------------------------------
   Fonts
   -------------------------------------------------------------------------- */

static lv_font_t * idx_make_font(const char * path, uint32_t size,
                                 int32_t weight, bool bold_face)
{
    lv_font_info_t info;
    lv_freetype_init_font_info(&info);
    info.name = path;
    info.size = size;
    info.render_mode = LV_FREETYPE_FONT_RENDER_MODE_BITMAP;
    info.style = bold_face ? LV_FREETYPE_FONT_STYLE_BOLD
                           : LV_FREETYPE_FONT_STYLE_NORMAL;
    info.weight = weight;
    info.kerning = LV_FONT_KERNING_NONE;
    return lv_freetype_font_create_with_info(&info);
}

static void idx_fonts_init(void)
{
    static const struct {
        idx_font_id_t id;
        const char * path;
        uint32_t size;
        int32_t weight;
        bool bold;
    } spec[] = {
        {IDX_F_DISP_14, "C:\\Windows\\Fonts\\bahnschrift.ttf", 14, 700, false},
        {IDX_F_DISP_15, "C:\\Windows\\Fonts\\bahnschrift.ttf", 15, 700, false},
        {IDX_F_DISP_16, "C:\\Windows\\Fonts\\bahnschrift.ttf", 16, 700, false},
        {IDX_F_DISP_18, "C:\\Windows\\Fonts\\bahnschrift.ttf", 18, 700, false},
        {IDX_F_DISP_20, "C:\\Windows\\Fonts\\bahnschrift.ttf", 20, 700, false},
        {IDX_F_DISP_21, "C:\\Windows\\Fonts\\bahnschrift.ttf", 21, 700, false},
        {IDX_F_DISP_22, "C:\\Windows\\Fonts\\bahnschrift.ttf", 22, 700, false},
        {IDX_F_DISP_23, "C:\\Windows\\Fonts\\bahnschrift.ttf", 23, 700, false},
        {IDX_F_DISP_27, "C:\\Windows\\Fonts\\bahnschrift.ttf", 27, 700, false},
        {IDX_F_DISP_36, "C:\\Windows\\Fonts\\bahnschrift.ttf", 36, 700, false},
        {IDX_F_DISP_42, "C:\\Windows\\Fonts\\bahnschrift.ttf", 42, 700, false},
        {IDX_F_BODY_9,  "C:\\Windows\\Fonts\\Candara.ttf", 9, 0, false},
        {IDX_F_BODY_9B, "C:\\Windows\\Fonts\\Candarab.ttf", 9, 0, true},
        {IDX_F_BODY_10, "C:\\Windows\\Fonts\\Candara.ttf", 10, 0, false},
        {IDX_F_BODY_11, "C:\\Windows\\Fonts\\Candara.ttf", 11, 0, false},
        {IDX_F_BODY_11B,"C:\\Windows\\Fonts\\Candarab.ttf", 11, 0, true},
        {IDX_F_BODY_12, "C:\\Windows\\Fonts\\Candara.ttf", 12, 0, false},
        {IDX_F_BODY_13, "C:\\Windows\\Fonts\\Candara.ttf", 13, 0, false},
        {IDX_F_BODY_13B,"C:\\Windows\\Fonts\\Candarab.ttf", 13, 0, true},
        {IDX_F_BODY_14, "C:\\Windows\\Fonts\\Candara.ttf", 14, 0, false},
        {IDX_F_BODY_15, "C:\\Windows\\Fonts\\Candara.ttf", 15, 0, false},
        {IDX_F_MONO_6,  "C:\\Windows\\Fonts\\consola.ttf", 6, 0, false},
        {IDX_F_MONO_6B, "C:\\Windows\\Fonts\\consolab.ttf", 6, 0, true},
        {IDX_F_MONO_7,  "C:\\Windows\\Fonts\\consola.ttf", 7, 0, false},
        {IDX_F_MONO_8,  "C:\\Windows\\Fonts\\consola.ttf", 8, 0, false},
        {IDX_F_MONO_9,  "C:\\Windows\\Fonts\\consola.ttf", 9, 0, false},
        {IDX_F_MONO_9B, "C:\\Windows\\Fonts\\consolab.ttf", 9, 0, true},
        {IDX_F_MONO_10, "C:\\Windows\\Fonts\\consola.ttf", 10, 0, false},
        {IDX_F_MONO_11, "C:\\Windows\\Fonts\\consola.ttf", 11, 0, false},
        {IDX_F_SYMBOL_6, "C:\\Windows\\Fonts\\seguisym.ttf", 6, 0, false},
        {IDX_F_SYMBOL_7, "C:\\Windows\\Fonts\\seguisym.ttf", 7, 0, false},
        {IDX_F_SYMBOL_8, "C:\\Windows\\Fonts\\seguisym.ttf", 8, 0, false},
        {IDX_F_SYMBOL_9, "C:\\Windows\\Fonts\\seguisym.ttf", 9, 0, false},
        {IDX_F_SYMBOL_10, "C:\\Windows\\Fonts\\seguisym.ttf", 10, 0, false},
        {IDX_F_SYMBOL_11, "C:\\Windows\\Fonts\\seguisym.ttf", 11, 0, false},
        {IDX_F_SYMBOL_12, "C:\\Windows\\Fonts\\seguisym.ttf", 12, 0, false},
    };
    size_t i;
    for(i = 0; i < sizeof(spec) / sizeof(spec[0]); i++) {
        idx_fonts[spec[i].id] = idx_make_font(spec[i].path, spec[i].size,
                                              spec[i].weight, spec[i].bold);
        if(idx_fonts[spec[i].id] == NULL) {
            printf("[index] font failed: %s %u\n", spec[i].path,
                   (unsigned)spec[i].size);
        }
    }
}

lv_font_t * idx_font(idx_font_id_t id)
{
    if(id >= IDX_F_COUNT || idx_fonts[id] == NULL) {
        return (lv_font_t *)&lv_font_montserrat_14;
    }
    return idx_fonts[id];
}

/* --------------------------------------------------------------------------
   Small helpers
   -------------------------------------------------------------------------- */

static lv_obj_t * idx_new_obj(lv_obj_t * parent, int32_t x, int32_t y,
                              int32_t w, int32_t h)
{
    lv_obj_t * obj = lv_obj_create(parent);
    lv_obj_remove_style_all(obj);
    lv_obj_set_scrollable(obj, false);
    lv_obj_set_pos(obj, x, y);
    lv_obj_set_size(obj, w, h);
    return obj;
}

lv_obj_t * idx_box(lv_obj_t * parent, int32_t x, int32_t y, int32_t w, int32_t h,
                    uint32_t bg, uint8_t bg_opa, uint32_t border,
                    uint8_t border_opa, uint8_t border_w, uint16_t radius,
                    uint8_t opa)
{
    lv_obj_t * obj = idx_new_obj(parent, x, y, w, h);
    lv_obj_set_style_bg_color(obj, lv_color_hex(bg), 0);
    lv_obj_set_style_bg_opa(obj, (lv_opa_t)bg_opa, 0);
    if(border_w > 0) {
        lv_obj_set_style_border_width(obj, border_w, 0);
        lv_obj_set_style_border_color(obj, lv_color_hex(border), 0);
        lv_obj_set_style_border_opa(obj, (lv_opa_t)border_opa, 0);
    }
    lv_obj_set_style_radius(obj, radius, 0);
    if(opa < 255) lv_obj_set_style_opa(obj, (lv_opa_t)opa, 0);
    return obj;
}

static lv_obj_t * idx_grad_box(lv_obj_t * parent, int32_t x, int32_t y,
                               int32_t w, int32_t h, uint32_t top,
                               uint32_t bottom, uint32_t border,
                               uint8_t border_opa, uint8_t border_w,
                               uint16_t radius)
{
    lv_obj_t * obj = idx_new_obj(parent, x, y, w, h);
    lv_obj_set_style_bg_color(obj, lv_color_hex(top), 0);
    lv_obj_set_style_bg_grad_color(obj, lv_color_hex(bottom), 0);
    lv_obj_set_style_bg_grad_dir(obj, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_grad_stop(obj, 255, 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    if(border_w > 0) {
        lv_obj_set_style_border_width(obj, border_w, 0);
        lv_obj_set_style_border_color(obj, lv_color_hex(border), 0);
        lv_obj_set_style_border_opa(obj, (lv_opa_t)border_opa, 0);
    }
    lv_obj_set_style_radius(obj, radius, 0);
    return obj;
}

static lv_obj_t * idx_led(lv_obj_t * parent, int32_t x, int32_t y,
                          int32_t size, uint32_t color, int32_t glow)
{
    lv_obj_t * led = idx_box(parent, x, y, size, size, color, 255, 0, 0, 0,
                             LV_RADIUS_CIRCLE, 255);
    if(glow > 0) {
        lv_obj_set_style_shadow_color(led, lv_color_hex(color), 0);
        lv_obj_set_style_shadow_opa(led, 200, 0);
        lv_obj_set_style_shadow_width(led, glow, 0);
        lv_obj_set_style_shadow_spread(led, 0, 0);
        lv_obj_set_style_shadow_offset_x(led, 0, 0);
        lv_obj_set_style_shadow_offset_y(led, 0, 0);
    }
    return led;
}

static void idx_pulse_cb(void * var, int32_t value)
{
    lv_obj_set_style_opa((lv_obj_t *)var, (lv_opa_t)value, 0);
}

static void idx_pulse_start(lv_obj_t * obj, uint32_t half_ms)
{
    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, obj);
    lv_anim_set_values(&a, 255, 76);
    lv_anim_set_time(&a, half_ms);
    lv_anim_set_playback_time(&a, half_ms);
    lv_anim_set_repeat_count(&a, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_exec_cb(&a, idx_pulse_cb);
    lv_anim_set_path_cb(&a, lv_anim_path_ease_in_out);
    lv_anim_start(&a);
}

static lv_obj_t * idx_simple_text(lv_obj_t * parent, const char * text,
                                  idx_font_id_t font, uint32_t color,
                                  uint8_t opa, int32_t x, int32_t y,
                                  uint16_t target_w, int8_t letter_space)
{
    idx_seg_t seg;
    seg.text = text;
    seg.font = (uint8_t)font;
    return idx_text_line(parent, x, y, &seg, 1, color, opa, letter_space,
                         target_w, 0, 0);
}

/* --------------------------------------------------------------------------
   Text builder
   -------------------------------------------------------------------------- */

static int32_t idx_font_dy(uint8_t font)
{
    static const int16_t disp_sizes[] = {14, 15, 16, 18, 20, 21, 22, 23,
                                         27, 36, 42};
    if(font <= IDX_F_DISP_42) {
        int32_t size = disp_sizes[font - IDX_F_DISP_14];
        return (int32_t)(((size - 6) * 22 + 50) / 100);
    }
    return 0;
}

lv_obj_t * idx_text_line(lv_obj_t * parent, int32_t x, int32_t y,
                          const idx_seg_t * segs, uint8_t seg_count,
                          uint32_t color, uint8_t opa, int8_t letter_space,
                          uint16_t target_w, uint16_t clip_w, uint8_t flags)
{
    if(seg_count == 0 || segs == NULL) return NULL;
    y -= idx_font_dy(segs[0].font);
    lv_font_t * font = idx_font((idx_font_id_t)segs[0].font);

    if((flags & 1) != 0) {
        /* ellipsis: fixed width, natural size */
        lv_obj_t * label = lv_label_create(parent);
        lv_obj_set_scrollable(label, false);
        lv_label_set_text(label, segs[0].text);
        lv_obj_set_style_text_font(label, font, 0);
        lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
        lv_obj_set_style_text_opa(label, (lv_opa_t)opa, 0);
        lv_obj_set_style_text_letter_space(label, letter_space, 0);
        lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
        lv_obj_set_pos(label, x, y);
        lv_obj_set_size(label, target_w, LV_SIZE_CONTENT);
        return label;
    }

    if((flags & 2) != 0 && clip_w > 0) {
        /* horizontally clipped by an ancestor */
        lv_obj_t * label = lv_label_create(parent);
        lv_obj_set_scrollable(label, false);
        lv_label_set_text(label, segs[0].text);
        lv_obj_set_style_text_font(label, font, 0);
        lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
        lv_obj_set_style_text_opa(label, (lv_opa_t)opa, 0);
        lv_obj_set_style_text_letter_space(label, letter_space, 0);
        lv_label_set_long_mode(label, LV_LABEL_LONG_CLIP);
        lv_obj_set_pos(label, x, y);
        lv_obj_set_size(label, clip_w, LV_SIZE_CONTENT);
        return label;
    }

    /* Scale each run so its advance matches the browser line box. Edge
     * spaces are removed and paid back as a target-width gap, because LVGL
     * trims them from the label's line box. */
    uint8_t j;
    lv_point_t adv[8];
    const char * draw[8];
    char * owned[8];
    int32_t target = target_w;
    int32_t x_start = x;
    int32_t total = 0;
    if(seg_count > 8) seg_count = 8;
    for(j = 0; j < seg_count; j++) {
        const char * src = segs[j].text;
        size_t len = strlen(src);
        char * tmp = (char *)lv_malloc(len + 1);
        if(tmp == NULL) {
            while(j > 0) lv_free(owned[--j]);
            return NULL;
        }
        size_t n = 0;
        size_t k = 0;
        while(k < len) {
            if(k + 1 < len && (unsigned char)src[k] == 0xC2 &&
               (unsigned char)src[k + 1] == 0xA0) {
                tmp[n++] = ' ';
                k += 2;
            }
            else {
                tmp[n++] = src[k++];
            }
        }
        tmp[n] = 0;

        int32_t lead = 0;
        int32_t trail = 0;
        while(lead < (int32_t)n && tmp[lead] == ' ') lead++;
        while(trail < (int32_t)n && tmp[n - 1 - trail] == ' ') trail++;
        lv_font_t * f = idx_font((idx_font_id_t)segs[j].font);
        int32_t space_adv = (int32_t)lv_font_get_glyph_width(f, ' ', 0) +
                            letter_space;
        if(space_adv < 0) space_adv = 0;
        if(space_adv > 0) space_adv += 1;
        if(j == 0 && lead > 0) {
            x_start += lead * space_adv;
            target -= lead * space_adv;
            memmove(tmp, tmp + lead, n - (size_t)lead + 1);
            n -= (size_t)lead;
        }
        if(j == seg_count - 1 && trail > 0) {
            target -= trail * space_adv;
            n -= (size_t)trail;
            tmp[n] = 0;
        }
        owned[j] = tmp;
        draw[j] = tmp;
        lv_text_get_size(&adv[j], tmp, f, letter_space, 0, LV_COORD_MAX,
                         LV_TEXT_FLAG_NONE);
        total += adv[j].x;
    }
    if(target <= 0) target = 1;
    if(total <= 0) {
        for(j = 0; j < seg_count; j++) lv_free(owned[j]);
        return NULL;
    }
    int32_t scale = target > 0
                    ? (int32_t)(((int64_t)target * 256 + total / 2) / total)
                    : 256;
    uint8_t first_font = segs[0].font;
    if(first_font >= IDX_F_BODY_9 && first_font <= IDX_F_BODY_15) {
        scale = (scale * 258 + 128) / 256;
    }
    else if(first_font <= IDX_F_DISP_42) {
        scale = (scale * 259 + 128) / 256;
    }
    else if(first_font >= IDX_F_MONO_6 && first_font <= IDX_F_MONO_11) {
        scale = (scale * 260 + 128) / 256;
    }
    if(scale < 32) scale = 32;
    if(scale > 2048) scale = 2048;

    int32_t cursor = x_start;
    lv_obj_t * first = NULL;
    for(j = 0; j < seg_count; j++) {
        lv_obj_t * label = lv_label_create(parent);
        lv_obj_set_scrollable(label, false);
        lv_label_set_text(label, draw[j]);
        lv_obj_set_style_text_font(label,
                                   idx_font((idx_font_id_t)segs[j].font), 0);
        lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
        lv_obj_set_style_text_opa(label, (lv_opa_t)opa, 0);
        lv_obj_set_style_text_letter_space(label, letter_space, 0);
        lv_label_set_long_mode(label, LV_LABEL_LONG_CLIP);
        lv_obj_set_size(label, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
        lv_obj_set_pos(label, cursor, y);
        lv_obj_set_style_transform_scale_x(label, scale, 0);
        lv_obj_set_style_transform_pivot_x(label, 0, 0);
        lv_obj_set_style_transform_pivot_y(label, 0, 0);
        cursor += (adv[j].x * scale + 128) >> 8;
        if(first == NULL) first = label;
    }
    for(j = 0; j < seg_count; j++) lv_free(owned[j]);
    return first;
}

/* --------------------------------------------------------------------------
   Generated backgrounds / images
   -------------------------------------------------------------------------- */

static void idx_bg_build(lv_obj_t * parent, const idx_bg_t * b)
{
    if(b->type == 1) {
        lv_obj_t * img = lv_image_create(parent);
        lv_obj_set_scrollable(img, false);
        lv_image_set_src(img, b->src);
        lv_obj_set_pos(img, b->x, b->y);
        if(b->opa < 255) lv_obj_set_style_opa(img, (lv_opa_t)b->opa, 0);
        if(b->action != IDX_ACT_NONE) idx_action_attach(img, b->action);
        return;
    }

    lv_obj_t * obj = idx_new_obj(parent, b->x, b->y, b->w, b->h);
    lv_obj_set_style_bg_color(obj, lv_color_hex(b->bg), 0);
    lv_obj_set_style_bg_opa(obj, (lv_opa_t)b->bg_opa, 0);
    if(b->grad_dir != 0) {
        lv_obj_set_style_bg_grad_color(obj, lv_color_hex(b->grad), 0);
        lv_obj_set_style_bg_grad_dir(obj, LV_GRAD_DIR_VER, 0);
        lv_obj_set_style_bg_grad_stop(obj, 255, 0);
    }
    if(b->border_w > 0) {
        lv_obj_set_style_border_width(obj, b->border_w, 0);
        lv_obj_set_style_border_color(obj, lv_color_hex(b->border), 0);
        lv_obj_set_style_border_opa(obj, (lv_opa_t)b->border_opa, 0);
    }
    if(b->radius) lv_obj_set_style_radius(obj, b->radius, 0);
    if(b->shadow_w > 0) {
        lv_obj_set_style_shadow_color(obj, lv_color_hex(b->shadow), 0);
        lv_obj_set_style_shadow_opa(obj, (lv_opa_t)b->shadow_opa, 0);
        lv_obj_set_style_shadow_width(obj, b->shadow_w, 0);
        lv_obj_set_style_shadow_spread(obj, b->shadow_spread, 0);
        lv_obj_set_style_shadow_offset_x(obj, 0, 0);
        lv_obj_set_style_shadow_offset_y(obj, b->shadow_ofs_y, 0);
    }
    if(b->opa < 255) lv_obj_set_style_opa(obj, (lv_opa_t)b->opa, 0);
    if(b->action != IDX_ACT_NONE) idx_action_attach(obj, b->action);
    if(b->tag == IDX_TAG_EYEBROW) idx_pulse_start(obj, 1200);
    else if(b->tag == IDX_TAG_LED_RED) idx_pulse_start(obj, 900);
}

static void idx_build_screen_content(lv_obj_t * content, const idx_screen_t * s)
{
    uint16_t i;
    for(i = 0; i < s->bg_count; i++) idx_bg_build(content, &s->bgs[i]);
    for(i = 0; i < s->text_count; i++) {
        const idx_text_t * t = &s->texts[i];
        idx_text_line(content, t->x, t->y, t->segs, t->seg_count,
                      t->color, t->opa, t->letter_space, t->w, t->clip_w,
                      t->flags);
    }
}

/* --------------------------------------------------------------------------
   Loop screen (dynamic)
   -------------------------------------------------------------------------- */

typedef struct {
    const char * n;
    const char * tag;
    const char * phase;
    const char * title;
    const char * desc;
    const char * code[8];
    uint8_t code_count;
} idx_loop_step_t;

static const idx_loop_step_t idx_loop_steps[6] = {
    {
        "01", "HUMAN", "INTENT", "Intent",
        "Humans set the goal and acceptance criteria; no C, no widget list.",
        {
            "# HUMAN INPUT \xc2\xb7 ILLUSTRATIVE",
            "Goal      Coffee ordering screen; show extraction progress",
            "Bar       Card spacing consistent; clear input feedback",
            "Feedback  Circle it on screen; save as an annotation",
        }, 4
    },
    {
        "02", "AI", "SOURCE", "Write C",
        "AI edits user/app/**/*.c directly; there is no object tree, inspect or set.",
        {
            "// user/app/coffee/coffee.c",
            "lv_obj_t * card = lv_obj_create(list);",
            "lv_obj_set_style_pad_gap(card, 12, 0);",
            "lv_obj_add_event_cb(btn, brew_cb, LV_EVENT_CLICKED, ctx);",
        }, 4
    },
    {
        "03", "BUILD", "HOST", "Build",
        "The first build fetches sources and compiles the engine; the prebuilt host SDK needs GCC only.",
        {
            "$ python -I core/cli.py --lvgl 9.6 ...",
            "[build] lvgl_9_6 \xc2\xb7 lvgl_engine.exe",
            "[build] app variants: coffee",
            "[build] ok \xc2\xb7 engine ready",
        }, 4
    },
    {
        "04", "RUNTIME", "REPLAY", "Run",
        "Virtual input and virtual time drive real LVGL; the last stdout line is the session path.",
        {
            "$ python -I core/cli.py --lvgl 9.6 \\",
            "    --scenario user/scenarios/coffee.json --json",
            "",
            "{\"session_id\":\"20261114-095536-1d9d\",",
            " \"status\":\"ok\",\"app\":\"coffee\",",
            " \"display\":{\"width\":800,\"height\":600},",
            " \"frame_count\":305}",
        }, 7
    },
    {
        "05", "TOOL", "EVIDENCE", "Evidence",
        "Full PNGs, timeline, per-frame diffs and engine logs; only changed frames are written.",
        {
            "sessions/20261114-095536-1d9d/",
            "  manifest.json          status ok \xc2\xb7 app coffee \xc2\xb7 305 frames",
            "  timeline.ndjson        hit / hit_class / frame spans",
            "  frame_diffs.ndjson     changed bboxes",
            "  frames/000001.png \xe2\x80\xa6    changed frames only",
            "  engine.log             exact state printf'd by user C",
        }, 6
    },
    {
        "06", "HUMAN", "DECISION", "Decide",
        "AI self-checks against the human bar and fixes issues; the final call is human. No pass/fail output.",
        {
            "// no pass / fail output from the tool",
            "Read the evidence:",
            "  frame 000001 \xe2\x80\x94 spacing 16 / 12 px",
            "  annotation #1 \xe2\x80\x94 \xe2\x80\x9cunify to 12px\xe2\x80\x9d",
            "  whiteboard    \xe2\x80\x94 \xe2\x80\x9csketch the order flow\xe2\x80\x9d",
            "",
            "Verdict: rework or accept \xe2\x86\x92 next loop",
        }, 7
    },
};

static const int16_t idx_loop_row_y[6] = {161, 219, 292, 364, 437, 510};
static const int16_t idx_loop_row_h[6] = {58, 73, 73, 73, 73, 72};
static const char * idx_loop_desc_lines[6][2] = {
    {"Humans set the goal and the bar; no C.", NULL},
    {"AI edits user/app directly; C is the source ", "of truth."},
    {"First build compiles the engine; prebuilt ", "needs GCC only."},
    {"Virtual input and virtual time drive real ", "LVGL."},
    {"Frames, timeline, diffs and logs land in the ", "session."},
    {"AI self-checks; the human makes the final ", "call."},
};
static const int16_t idx_loop_desc_y[6][2] = {
    {195, 0}, {253, 268}, {326, 340}, {399, 413}, {471, 485}, {544, 558},
};
static const uint16_t idx_loop_desc_w[6][2] = {
    {155, 0}, {162, 34}, {158, 64}, {154, 23}, {168, 32}, {165, 16},
};
static const uint16_t idx_loop_title_w[6] = {34, 41, 29, 22, 50, 38};

static lv_obj_t * idx_loop_rows[6];
static lv_obj_t * idx_loop_bars[6];
static lv_obj_t * idx_loop_nums[6];
static lv_obj_t * idx_loop_leds[6];
static lv_obj_t * idx_loop_gauge;
static lv_obj_t * idx_loop_nodes[6];
static lv_obj_t * idx_loop_gauge_num;
static lv_obj_t * idx_loop_gauge_label;
static lv_obj_t * idx_loop_gauge_pct;
static lv_obj_t * idx_loop_tag1_label;
static lv_obj_t * idx_loop_tag2_label;
static lv_obj_t * idx_loop_title;
static lv_obj_t * idx_loop_desc;
static lv_obj_t * idx_loop_progress[6];
static lv_obj_t * idx_loop_code[8];
static lv_obj_t * idx_loop_play;
static lv_obj_t * idx_loop_play_icon;
static lv_obj_t * idx_loop_play_label;
static lv_timer_t * idx_loop_timer;
static uint8_t idx_loop_active;
static bool idx_loop_playing;
static bool idx_loop_initial = true;

static void idx_stop_loop_playback(void);
static void idx_anim_opa_cb(void * var, int32_t value);

static uint32_t idx_code_color(const char * line)
{
    if(line[0] == '#' || (line[0] == '/' && line[1] == '/')) {
        return 0x5c7284;
    }
    return 0xcfe0ec;
}

static void idx_loop_update_play_button(void)
{
    if(idx_loop_play == NULL) return;
    lv_obj_set_style_border_color(idx_loop_play,
                                  lv_color_hex(idx_loop_playing ? COL_GREEN : COL_LINE_3), 0);
    lv_obj_set_style_text_color(idx_loop_play_label,
                                lv_color_hex(idx_loop_playing ? COL_GREEN : COL_CYAN), 0);
    lv_obj_set_style_text_color(idx_loop_play_icon,
                                lv_color_hex(idx_loop_playing ? COL_GREEN : COL_CYAN), 0);
    if(idx_loop_play_icon) {
        lv_label_set_text(idx_loop_play_icon, idx_loop_playing ? "\xe2\x96\xa0" : "\xe2\x96\xb6");
    }
    if(idx_loop_play_label) {
        lv_label_set_text(idx_loop_play_label, idx_loop_playing ? "STOP" : "PLAY LOOP");
    }
}

static void idx_loop_render(uint8_t index, bool animate)
{
    if(index >= 6) index = 0;
    idx_loop_active = index;
    const idx_loop_step_t * step = &idx_loop_steps[index];
    uint8_t i;

    for(i = 0; i < 6; i++) {
        bool on = i == index;
        int32_t rg = on ? 19 : 0;
        lv_obj_set_style_bg_opa(idx_loop_rows[i], (lv_opa_t)rg, 0);
        lv_obj_set_style_bg_opa(idx_loop_bars[i], on ? 255 : 0, 0);
        lv_obj_set_style_text_color(idx_loop_nums[i],
                                    lv_color_hex(on ? COL_CYAN : COL_DIM), 0);
        lv_obj_set_style_bg_opa(idx_loop_leds[i], on ? 255 : 0, 0);
        lv_obj_set_style_border_color(idx_loop_leds[i],
                                      lv_color_hex(on ? COL_CYAN : COL_LINE_3), 0);
        lv_obj_set_style_bg_opa(idx_loop_progress[i], 255, 0);
        lv_obj_set_style_bg_color(idx_loop_progress[i],
                                  lv_color_hex(i <= index ? COL_CYAN : COL_LINE), 0);
        lv_obj_set_style_bg_opa(idx_loop_nodes[i], i <= index ? 255 : 0, 0);
        lv_obj_set_style_border_color(idx_loop_nodes[i],
                                      lv_color_hex(i <= index ? COL_CYAN : COL_LINE_3), 0);
    }

    if(idx_loop_gauge) {
        int32_t value = index + 1;
        if(animate) {
            lv_anim_t a;
            lv_anim_init(&a);
            lv_anim_set_var(&a, idx_loop_gauge);
            lv_anim_set_values(&a, lv_arc_get_value(idx_loop_gauge), value);
            lv_anim_set_time(&a, 300);
            lv_anim_set_exec_cb(&a, (lv_anim_exec_xcb_t)lv_arc_set_value);
            lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
            lv_anim_start(&a);
        }
        else {
            lv_arc_set_value(idx_loop_gauge, value);
        }
    }
    if(idx_loop_gauge_num) lv_label_set_text(idx_loop_gauge_num, step->n);
    if(idx_loop_gauge_label) lv_label_set_text(idx_loop_gauge_label, step->phase);
    if(idx_loop_gauge_pct) {
        int pct = (idx_loop_initial && index == 0)
                  ? 16 : ((index + 1) * 100 + 3) / 6;
        lv_label_set_text_fmt(idx_loop_gauge_pct, "%d%%", pct);
    }
    idx_loop_initial = false;

    if(idx_loop_tag1_label) {
        lv_label_set_text(idx_loop_tag1_label, step->tag);
        lv_obj_set_style_text_color(idx_loop_tag1_label,
                                    lv_color_hex(COL_CYAN), 0);
    }
    if(idx_loop_tag2_label) {
        lv_label_set_text(idx_loop_tag2_label, step->phase);
        lv_obj_set_style_text_color(idx_loop_tag2_label,
                                    lv_color_hex(COL_DIM), 0);
    }
    if(idx_loop_title) lv_label_set_text(idx_loop_title, step->title);
    if(idx_loop_desc) lv_label_set_text(idx_loop_desc, step->desc);

    for(i = 0; i < 8; i++) {
        if(idx_loop_code[i] == NULL) continue;
        if(i < step->code_count) {
            const char * line = step->code[i];
            lv_obj_set_hidden(idx_loop_code[i], line[0] == '\0');
            lv_label_set_text(idx_loop_code[i], line);
            lv_obj_set_style_text_color(idx_loop_code[i],
                                        lv_color_hex(idx_code_color(line)), 0);
        }
        else {
            lv_obj_set_hidden(idx_loop_code[i], true);
        }
    }
}

static void idx_loop_timer_cb(lv_timer_t * timer)
{
    LV_UNUSED(timer);
    if(!idx_loop_playing) return;
    idx_loop_render((uint8_t)((idx_loop_active + 1) % 6), true);
}

static void idx_loop_step_cb(lv_event_t * event)
{
    uintptr_t value = (uintptr_t)lv_event_get_user_data(event);
    if(value == 0 || value > 6) return;
    idx_stop_loop_playback();
    idx_loop_render((uint8_t)(value - 1), true);
}

static void idx_loop_play_cb(lv_event_t * event)
{
    LV_UNUSED(event);
    if(idx_loop_playing) {
        idx_stop_loop_playback();
        return;
    }
    idx_loop_playing = true;
    idx_loop_update_play_button();
}

static void idx_loop_chip(lv_obj_t * parent, lv_obj_t ** label_out,
                          const char * text, uint32_t color)
{
    lv_obj_t * chip = lv_obj_create(parent);
    lv_obj_remove_style_all(chip);
    lv_obj_set_scrollable(chip, false);
    lv_obj_set_style_bg_opa(chip, 0, 0);
    lv_obj_set_style_border_width(chip, 1, 0);
    lv_obj_set_style_border_color(chip, lv_color_hex(COL_LINE_2), 0);
    lv_obj_set_style_radius(chip, 3, 0);
    lv_obj_set_style_pad_hor(chip, 5, 0);
    lv_obj_set_style_pad_ver(chip, 2, 0);
    lv_obj_set_size(chip, LV_SIZE_CONTENT, 17);
    lv_obj_set_flex_flow(chip, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(chip, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);
    lv_obj_t * label = lv_label_create(chip);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, idx_font(IDX_F_MONO_7), 0);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    *label_out = label;
}

static void idx_loop_panel_shadow(lv_obj_t * obj)
{
    lv_obj_set_style_shadow_color(obj, lv_color_hex(0x000000), 0);
    lv_obj_set_style_shadow_opa(obj, 255, 0);
    lv_obj_set_style_shadow_width(obj, 32, 0);
    lv_obj_set_style_shadow_spread(obj, -24, 0);
    lv_obj_set_style_shadow_offset_x(obj, 0, 0);
    lv_obj_set_style_shadow_offset_y(obj, 14, 0);
}

static void idx_loop_build(lv_obj_t * content)
{
    uint8_t i;

    /* Stepper panel. */
    lv_obj_t * panel = idx_grad_box(content, 28, 129, 250, 453,
                                    0x0d1822, 0x0a121a, COL_LINE, 255, 1, 12);
    idx_loop_panel_shadow(panel);
    idx_box(content, 29, 160, 248, 1, COL_LINE, 255, 0, 0, 0, 0, 255);
    idx_simple_text(content, "SEQUENCE", IDX_F_MONO_7, COL_DIM, 255,
                    42, 140, 40, 1);
    idx_simple_text(content, "06 / STEPS", IDX_F_MONO_7, COL_DIM, 255,
                    215, 140, 49, 1);

    for(i = 0; i < 6; i++) {
        int32_t y = idx_loop_row_y[i];
        int32_t h = idx_loop_row_h[i];
        lv_obj_t * row = idx_new_obj(content, 29, y, 248, h);
        lv_obj_set_style_bg_color(row, lv_color_hex(COL_CYAN), 0);
        lv_obj_set_style_bg_opa(row, 0, 0);
        lv_obj_set_clickable(row, true);
        lv_obj_add_event_cb(row, idx_loop_step_cb, LV_EVENT_CLICKED,
                            (void *)(uintptr_t)(i + 1));
        idx_loop_rows[i] = row;

        lv_obj_t * bar = idx_box(content, 29, y, 2, h, COL_CYAN, 0,
                                 0, 0, 0, 0, 255);
        idx_loop_bars[i] = bar;
        if(i < 5) idx_box(content, 29, y + h - 1, 248, 1, COL_LINE, 255,
                          0, 0, 0, 0, 255);

        char num[3] = {idx_loop_steps[i].n[0], idx_loop_steps[i].n[1], 0};
        idx_loop_nums[i] = idx_simple_text(content, num, IDX_F_MONO_7,
                                           COL_DIM, 255, 41, y + 14, 8, 0);
        idx_simple_text(content, idx_loop_steps[i].title, IDX_F_BODY_13B,
                        COL_TEXT, 255, 76, y + 13, idx_loop_title_w[i], 0);

        int32_t dy = idx_loop_desc_y[i][0];
        idx_simple_text(content, idx_loop_desc_lines[i][0], IDX_F_BODY_10,
                        COL_MUTED, 255, 76, dy, idx_loop_desc_w[i][0], 0);
        if(idx_loop_desc_lines[i][1]) {
            idx_simple_text(content, idx_loop_desc_lines[i][1], IDX_F_BODY_10,
                            COL_MUTED, 255, 76, idx_loop_desc_y[i][1],
                            idx_loop_desc_w[i][1], 0);
        }

        lv_obj_t * led = idx_box(content, 260, y + 16, 5, 5, COL_CYAN, 0,
                                 COL_LINE_3, 255, 1, LV_RADIUS_CIRCLE, 255);
        idx_loop_leds[i] = led;
    }

    /* Gauge. */
    idx_loop_gauge = lv_arc_create(content);
    lv_obj_remove_style_all(idx_loop_gauge);
    lv_obj_set_scrollable(idx_loop_gauge, false);
    lv_obj_set_clickable(idx_loop_gauge, false);
    lv_obj_set_pos(idx_loop_gauge, 323, 195);
    lv_obj_set_size(idx_loop_gauge, 125, 125);
    lv_obj_set_style_bg_opa(idx_loop_gauge, 0, LV_PART_MAIN);
    lv_obj_set_style_border_width(idx_loop_gauge, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(idx_loop_gauge, 0, LV_PART_MAIN);
    lv_obj_set_style_arc_width(idx_loop_gauge, 6, LV_PART_MAIN);
    lv_obj_set_style_arc_color(idx_loop_gauge, lv_color_hex(0x142634),
                               LV_PART_MAIN);
    lv_obj_set_style_arc_opa(idx_loop_gauge, 255, LV_PART_MAIN);
    lv_obj_set_style_arc_rounded(idx_loop_gauge, true, LV_PART_MAIN);
    lv_obj_set_style_arc_width(idx_loop_gauge, 6, LV_PART_INDICATOR);
    lv_obj_set_style_arc_color(idx_loop_gauge, lv_color_hex(COL_CYAN),
                               LV_PART_INDICATOR);
    lv_obj_set_style_arc_opa(idx_loop_gauge, 255, LV_PART_INDICATOR);
    lv_obj_set_style_arc_rounded(idx_loop_gauge, true, LV_PART_INDICATOR);
    lv_arc_set_bg_angles(idx_loop_gauge, 135, 45);
    lv_arc_set_range(idx_loop_gauge, 0, 6);
    lv_arc_set_value(idx_loop_gauge, 1);

    static const int16_t node_x[6] = {324, 341, 383, 425, 443, 425};
    static const int16_t node_y[6] = {255, 213, 195, 213, 255, 297};
    for(i = 0; i < 6; i++) {
        idx_loop_nodes[i] = idx_box(content, node_x[i], node_y[i], 5, 5,
                                    COL_CYAN, 0, COL_LINE_3, 255, 1,
                                    LV_RADIUS_CIRCLE, 255);
    }

    idx_loop_gauge_num = lv_label_create(content);
    lv_label_set_text(idx_loop_gauge_num, "01");
    lv_obj_set_style_text_font(idx_loop_gauge_num, idx_font(IDX_F_DISP_36), 0);
    lv_obj_set_style_text_color(idx_loop_gauge_num, lv_color_hex(COL_TEXT), 0);
    lv_obj_set_style_text_align(idx_loop_gauge_num, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_pos(idx_loop_gauge_num, 309, 216);
    lv_obj_set_size(idx_loop_gauge_num, 152, LV_SIZE_CONTENT);

    idx_loop_gauge_label = lv_label_create(content);
    lv_label_set_text(idx_loop_gauge_label, "INTENT");
    lv_obj_set_style_text_font(idx_loop_gauge_label, idx_font(IDX_F_MONO_7), 0);
    lv_obj_set_style_text_color(idx_loop_gauge_label, lv_color_hex(COL_CYAN), 0);
    lv_obj_set_style_text_align(idx_loop_gauge_label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_pos(idx_loop_gauge_label, 309, 263);
    lv_obj_set_size(idx_loop_gauge_label, 152, LV_SIZE_CONTENT);

    idx_loop_gauge_pct = lv_label_create(content);
    lv_label_set_text(idx_loop_gauge_pct, "16%");
    lv_obj_set_style_text_font(idx_loop_gauge_pct, idx_font(IDX_F_MONO_7), 0);
    lv_obj_set_style_text_color(idx_loop_gauge_pct, lv_color_hex(COL_DIM), 0);
    lv_obj_set_style_text_align(idx_loop_gauge_pct, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_pos(idx_loop_gauge_pct, 309, 280);
    lv_obj_set_size(idx_loop_gauge_pct, 152, LV_SIZE_CONTENT);

    /* Console copy. */
    lv_obj_t * tags = idx_new_obj(content, 479, 207, 276, 18);
    lv_obj_set_flex_flow(tags, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_all(tags, 0, 0);
    lv_obj_set_style_pad_column(tags, 5, 0);
    idx_loop_chip(tags, &idx_loop_tag1_label, "HUMAN", COL_CYAN);
    idx_loop_chip(tags, &idx_loop_tag2_label, "INTENT", COL_DIM);

    idx_loop_title = lv_label_create(content);
    lv_label_set_text(idx_loop_title, "Intent");
    lv_obj_set_style_text_font(idx_loop_title, idx_font(IDX_F_DISP_22), 0);
    lv_obj_set_style_text_color(idx_loop_title, lv_color_hex(COL_TEXT), 0);
    lv_obj_set_pos(idx_loop_title, 479, 226);

    idx_loop_desc = lv_label_create(content);
    lv_label_set_text(idx_loop_desc,
                      "Humans set the goal and acceptance criteria; no C, no widget list.");
    lv_obj_set_style_text_font(idx_loop_desc, idx_font(IDX_F_BODY_11), 0);
    lv_obj_set_style_text_color(idx_loop_desc, lv_color_hex(COL_MUTED), 0);
    lv_obj_set_style_text_line_space(idx_loop_desc, 3, 0);
    lv_label_set_long_mode(idx_loop_desc, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(idx_loop_desc, 479, 260);
    lv_obj_set_size(idx_loop_desc, 254, LV_SIZE_CONTENT);

    for(i = 0; i < 6; i++) {
        idx_loop_progress[i] = idx_box(content, 479 + i * 46, 305, 43, 3,
                                       COL_LINE, 255, 0, 0, 0, 2, 255);
    }

    /* Code block. */
    idx_box(content, 325, 358, 414, 148, 0x050a0f, 255,
            COL_LINE, 255, 1, 7, 255);
    for(i = 0; i < 8; i++) {
        idx_loop_code[i] = lv_label_create(content);
        lv_obj_set_scrollable(idx_loop_code[i], false);
        lv_label_set_text(idx_loop_code[i], "");
        lv_obj_set_style_text_font(idx_loop_code[i], idx_font(IDX_F_MONO_10), 0);
        lv_obj_set_style_text_color(idx_loop_code[i], lv_color_hex(0xcfe0ec), 0);
        lv_label_set_long_mode(idx_loop_code[i], LV_LABEL_LONG_CLIP);
        lv_obj_set_pos(idx_loop_code[i], 339, 373 + i * 16);
        lv_obj_set_size(idx_loop_code[i], 400, LV_SIZE_CONTENT);
        lv_obj_set_hidden(idx_loop_code[i], true);
    }

    /* Console footer + play button. */
    idx_simple_text(content, "Click a step \xc2\xb7 illustrative flow",
                    IDX_F_MONO_7, COL_DIM, 255, 309, 523, 115, 0);
    idx_loop_play = idx_box(content, 680, 515, 75, 27, COL_CYAN, 13,
                            COL_LINE_3, 255, 1, 5, 255);
    app_obj_set_name(idx_loop_play, "loop_play");
    lv_obj_set_clickable(idx_loop_play, true);
    lv_obj_add_event_cb(idx_loop_play, idx_loop_play_cb, LV_EVENT_CLICKED, NULL);
    idx_loop_play_icon = idx_simple_text(content, "\xe2\x96\xb6", IDX_F_SYMBOL_8,
                                         COL_CYAN, 255, 690, 522, 8, 0);
    idx_loop_play_label = idx_simple_text(content, "PLAY LOOP", IDX_F_MONO_8,
                                          COL_CYAN, 255, 704, 522, 42, 0);
    lv_obj_t * play_hit = idx_new_obj(content, 680, 515, 75, 27);
    app_obj_set_name(play_hit, "loop_play_hit");
    lv_obj_set_clickable(play_hit, true);
    lv_obj_add_event_cb(play_hit, idx_loop_play_cb, LV_EVENT_CLICKED, NULL);

    idx_loop_timer = lv_timer_create(idx_loop_timer_cb, 2600, NULL);
    idx_loop_render(0, false);
    idx_loop_update_play_button();
}

/* --------------------------------------------------------------------------
   Versions screen (dynamic)
   -------------------------------------------------------------------------- */

typedef struct {
    const char * tag;
    const char * ver;
    const char * title;
    const char * text;
} idx_version_t;

static const idx_version_t idx_versions[6] = {
    {"DEFAULT HOST", "HOST 9.6", "Host default",
     "Daily preview and evidence use 9.6. The packaged intro app targets 9.4+ and runs on 9.6."},
    {"SUPPORTED", "HOST 9.5", "Same generation",
     "Same adapter path; select it with --lvgl 9.5 or the scenario's \"lvgl\" field."},
    {"DEVICE BASELINE", "BASE 9.4", "Device baseline",
     "Device apps target 9.4; SiFli export checks compatibility without rewriting shared source."},
    {"LEGACY HARNESS", "LEGACY 9.1", "Legacy harness",
     "9.1 and 8.x use the old harness; no object names, hit is empty, only hit_class."},
    {"LEGACY HARNESS", "LEGACY 8.4", "Legacy harness",
     "Cross-version comparison covers event semantics and the session file set, not pixels."},
    {"LEGACY HARNESS", "LEGACY 8.3", "Legacy harness",
     "Supports 8.x input semantics; below 9.2 there are no object names, use hit_class."},
};

static const char * idx_version_numbers[6] = {
    "9.6", "9.5", "9.4", "9.1", "8.4", "8.3"
};
static const char * idx_version_smalls[6] = {
    "DEFAULT", "SUPPORTED", "BASELINE", "LEGACY", "LEGACY", "LEGACY"
};
static lv_obj_t * idx_ver_cells[6];
static lv_obj_t * idx_ver_nums[6];
static lv_obj_t * idx_ver_smalls_labels[6];
static lv_obj_t * idx_ver_detail;
static lv_obj_t * idx_ver_tag;
static lv_obj_t * idx_ver_ver;
static lv_obj_t * idx_ver_title;
static lv_obj_t * idx_ver_text;
static uint8_t idx_ver_active;

static void idx_anim_y_cb(void * var, int32_t value)
{
    lv_obj_set_y((lv_obj_t *)var, value);
}

static void idx_versions_render(uint8_t index, bool animate)
{
    if(index >= 6) index = 0;
    idx_ver_active = index;
    uint8_t i;
    for(i = 0; i < 6; i++) {
        bool on = i == index;
        lv_obj_set_style_bg_opa(idx_ver_cells[i], on ? 255 : 0, 0);
        lv_obj_set_style_text_color(idx_ver_nums[i],
                                    lv_color_hex(on ? COL_INK : COL_TEXT), 0);
        lv_obj_set_style_text_color(idx_ver_smalls_labels[i],
                                    lv_color_hex(on ? COL_INK : COL_DIM), 0);
        lv_obj_set_style_text_opa(idx_ver_smalls_labels[i], on ? 179 : 255, 0);
    }
    const idx_version_t * v = &idx_versions[index];
    lv_label_set_text(idx_ver_tag, v->tag);
    lv_label_set_text(idx_ver_ver, v->ver);
    lv_label_set_text(idx_ver_title, v->title);
    lv_label_set_text(idx_ver_text, v->text);

    if(animate) {
        lv_obj_set_style_opa(idx_ver_detail, 0, 0);
        lv_obj_set_y(idx_ver_detail, 368);
        lv_anim_t ao;
        lv_anim_init(&ao);
        lv_anim_set_var(&ao, idx_ver_detail);
        lv_anim_set_values(&ao, 0, 255);
        lv_anim_set_time(&ao, 180);
        lv_anim_set_exec_cb(&ao, idx_anim_opa_cb);
        lv_anim_set_path_cb(&ao, lv_anim_path_ease_out);
        lv_anim_start(&ao);

        lv_anim_t ay;
        lv_anim_init(&ay);
        lv_anim_set_var(&ay, idx_ver_detail);
        lv_anim_set_values(&ay, 368, 364);
        lv_anim_set_time(&ay, 180);
        lv_anim_set_exec_cb(&ay, idx_anim_y_cb);
        lv_anim_set_path_cb(&ay, lv_anim_path_ease_out);
        lv_anim_start(&ay);
    }
    else {
        lv_obj_set_style_opa(idx_ver_detail, 255, 0);
        lv_obj_set_y(idx_ver_detail, 364);
    }
}

static void idx_version_click_cb(lv_event_t * event)
{
    uintptr_t value = (uintptr_t)lv_event_get_user_data(event);
    if(value < 6) idx_versions_render((uint8_t)value, true);
}

static void idx_versions_build(lv_obj_t * content)
{
    uint8_t i;
    lv_obj_t * rail = idx_new_obj(content, 44, 271, 712, 86);
    lv_obj_set_style_bg_opa(rail, 0, 0);
    lv_obj_set_style_border_width(rail, 1, 0);
    lv_obj_set_style_border_color(rail, lv_color_hex(COL_LINE_2), 0);
    lv_obj_set_style_radius(rail, 6, 0);
    lv_obj_set_style_clip_corner(rail, true, 0);

    for(i = 0; i < 6; i++) {
        int16_t col = (int16_t)(i % 3);
        int16_t row = (int16_t)(i / 3);
        int16_t x = (int16_t)(1 + col * 237);
        int16_t y = (int16_t)(1 + row * 42);
        int16_t h = row == 0 ? 42 : 41;
        lv_obj_t * cell = idx_new_obj(rail, x, y, 236, h);
        lv_obj_set_style_bg_color(cell, lv_color_hex(COL_CYAN), 0);
        lv_obj_set_style_bg_opa(cell, 0, 0);
        lv_obj_set_clickable(cell, true);
        lv_obj_add_event_cb(cell, idx_version_click_cb, LV_EVENT_CLICKED,
                            (void *)(uintptr_t)i);
        idx_ver_cells[i] = cell;

        idx_ver_nums[i] = idx_simple_text(cell, idx_version_numbers[i],
                                          IDX_F_DISP_16, COL_TEXT, 255,
                                          7, 5, 0, 0);
        idx_ver_smalls_labels[i] = idx_simple_text(cell,
                                                    idx_version_smalls[i],
                                                    IDX_F_MONO_6, COL_DIM,
                                                    255, 7, 25, 0, 0);
    }
    idx_box(rail, 237, 1, 1, 84, COL_LINE_2, 255, 0, 0, 0, 0, 255);
    idx_box(rail, 474, 1, 1, 84, COL_LINE_2, 255, 0, 0, 0, 0, 255);
    idx_box(rail, 1, 43, 710, 1, COL_LINE_2, 255, 0, 0, 0, 0, 255);

    idx_box(content, 44, 364, 712, 112, 0x081018, 140,
            COL_LINE, 255, 1, 6, 255);
    idx_box(content, 44, 365, 2, 110, COL_CYAN, 255, 0, 0, 0, 0, 255);
    idx_ver_detail = idx_new_obj(content, 44, 364, 712, 112);
    idx_ver_tag = idx_simple_text(idx_ver_detail, idx_versions[0].tag,
                                  IDX_F_MONO_7, COL_CYAN, 255, 15, 13, 0, 1);
    idx_ver_ver = lv_label_create(idx_ver_detail);
    lv_label_set_text(idx_ver_ver, idx_versions[0].ver);
    lv_obj_set_style_text_font(idx_ver_ver, idx_font(IDX_F_MONO_7), 0);
    lv_obj_set_style_text_color(idx_ver_ver, lv_color_hex(COL_DIM), 0);
    lv_obj_set_style_text_align(idx_ver_ver, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_set_pos(idx_ver_ver, 15, 13);
    lv_obj_set_size(idx_ver_ver, 683, LV_SIZE_CONTENT);

    idx_ver_title = idx_simple_text(idx_ver_detail, idx_versions[0].title,
                                    IDX_F_DISP_18, COL_TEXT, 255, 15, 31, 0, 0);
    idx_ver_text = lv_label_create(idx_ver_detail);
    lv_label_set_text(idx_ver_text, idx_versions[0].text);
    lv_obj_set_style_text_font(idx_ver_text, idx_font(IDX_F_BODY_10), 0);
    lv_obj_set_style_text_color(idx_ver_text, lv_color_hex(COL_MUTED), 0);
    lv_label_set_long_mode(idx_ver_text, LV_LABEL_LONG_WRAP);
    lv_obj_set_pos(idx_ver_text, 15, 55);
    lv_obj_set_size(idx_ver_text, 683, LV_SIZE_CONTENT);

    idx_versions_render(0, false);
}

/* --------------------------------------------------------------------------
   Animated media
   -------------------------------------------------------------------------- */

static const void * idx_intro_frame_ptrs[5];
static const void * idx_watch_frame_ptrs[8];

static void idx_inspector_build(lv_obj_t * content)
{
    uint8_t i;
    for(i = 0; i < 5; i++) idx_intro_frame_ptrs[i] = idx_intro_frames[i];
    lv_obj_t * anim = lv_animimg_create(content);
    lv_obj_set_scrollable(anim, false);
    lv_obj_set_pos(anim, 78, 192);
    lv_obj_set_size(anim, 644, 483);
    lv_animimg_set_src(anim, idx_intro_frame_ptrs, 5);
    lv_animimg_set_duration(anim, 4650);
    lv_animimg_set_repeat_count(anim, LV_ANIM_REPEAT_INFINITE);
    lv_animimg_start(anim);
}

static void idx_watch_build(lv_obj_t * content)
{
    uint8_t i;
    for(i = 0; i < 8; i++) idx_watch_frame_ptrs[i] = idx_watch_frames[i];
    idx_box(content, 258, 781, 32, 38, 0x000000, 0,
            COL_LINE_2, 255, 1, 2, 255);
    lv_obj_t * anim = lv_animimg_create(content);
    lv_obj_set_scrollable(anim, false);
    lv_obj_set_pos(anim, 259, 782);
    lv_obj_set_size(anim, 30, 36);
    lv_animimg_set_src(anim, idx_watch_frame_ptrs, 8);
    lv_animimg_set_duration(anim, 5750);
    lv_animimg_set_repeat_count(anim, LV_ANIM_REPEAT_INFINITE);
    lv_animimg_start(anim);
}

/* --------------------------------------------------------------------------
   Actions and screen switching
   -------------------------------------------------------------------------- */

static void idx_anim_opa_cb(void * var, int32_t value)
{
    lv_obj_set_style_opa((lv_obj_t *)var, (lv_opa_t)value, 0);
}

static void idx_action_cb(lv_event_t * event)
{
    uintptr_t action = (uintptr_t)lv_event_get_user_data(event);
    if(action >= IDX_ACT_SCREEN_OVERVIEW && action <= IDX_ACT_SCREEN_START) {
        uint8_t screen = (uint8_t)(action - IDX_ACT_SCREEN_OVERVIEW);
        printf("[index] nav=%u\n", (unsigned)screen);
        idx_show_screen(screen, true);
        idx_set_tab_focus(screen);
    }
    else if(action == IDX_ACT_LOG) {
        printf("[index] link (web-only in this port)\n");
    }
}

void idx_action_attach(lv_obj_t * obj, uint8_t action)
{
    if(action == IDX_ACT_NONE) return;
    lv_obj_set_clickable(obj, true);
    lv_obj_add_event_cb(obj, idx_action_cb, LV_EVENT_CLICKED,
                        (void *)(uintptr_t)action);
}

static void idx_tab_style(uint8_t screen, bool selected)
{
    lv_obj_t * tab = idx_tabs[screen];
    if(tab == NULL) return;
    lv_obj_set_style_bg_color(tab, lv_color_hex(COL_CYAN), 0);
    lv_obj_set_style_bg_opa(tab, selected ? 11 : 0, 0);
    lv_obj_set_style_text_color(idx_tab_names[screen],
                                lv_color_hex(selected ? COL_TEXT : COL_DIM), 0);
    lv_obj_set_style_text_opa(idx_tab_nums[screen], selected ? 255 : 153, 0);
    if(idx_tab_lines[screen]) {
        lv_obj_set_style_bg_opa(idx_tab_lines[screen],
                                selected ? 255 : 0, 0);
    }
}

void idx_set_tab_focus(uint8_t screen)
{
    if(screen < 6 && idx_group && idx_tabs[screen]) {
        lv_group_focus_obj(idx_tabs[screen]);
    }
}

static void idx_stop_loop_playback(void);

void idx_show_screen(uint8_t screen, bool animate)
{
    if(screen >= 6) screen = 0;
    if(idx_current == screen) {
        if(idx_workspace) lv_obj_scroll_to_y(idx_workspace, 0, LV_ANIM_OFF);
        return;
    }
    uint8_t previous = idx_current;
    idx_current = screen;

    if(previous < 6) {
        lv_obj_set_hidden(idx_contents[previous], true);
        lv_obj_set_size(idx_contents[previous], 0, 0);
        idx_tab_style(previous, false);
    }

    lv_obj_t * content = idx_contents[screen];
    lv_obj_set_size(content, IDX_W, idx_screens[screen]->content_h);
    lv_obj_set_hidden(content, false);
    lv_obj_set_pos(content, animate ? 8 : 0, 0);
    lv_obj_set_style_opa(content, animate ? 0 : 255, 0);
    if(idx_workspace) lv_obj_scroll_to_y(idx_workspace, 0, LV_ANIM_OFF);
    idx_tab_style(screen, true);

    if(previous == 1 && screen != 1) idx_stop_loop_playback();

    if(animate) {
        lv_anim_t ax;
        lv_anim_init(&ax);
        lv_anim_set_var(&ax, content);
        lv_anim_set_values(&ax, 8, 0);
        lv_anim_set_time(&ax, 220);
        lv_anim_set_exec_cb(&ax, (lv_anim_exec_xcb_t)lv_obj_set_x);
        lv_anim_set_path_cb(&ax, lv_anim_path_ease_out);
        lv_anim_start(&ax);

        lv_anim_t ao;
        lv_anim_init(&ao);
        lv_anim_set_var(&ao, content);
        lv_anim_set_values(&ao, 0, 255);
        lv_anim_set_time(&ao, 220);
        lv_anim_set_exec_cb(&ao, idx_anim_opa_cb);
        lv_anim_set_path_cb(&ao, lv_anim_path_ease_out);
        lv_anim_start(&ao);
    }
}

static void idx_tab_click_cb(lv_event_t * event)
{
    uintptr_t screen = (uintptr_t)lv_obj_get_user_data(lv_event_get_target(event));
    if(screen < 6) {
        idx_show_screen((uint8_t)screen, true);
        idx_set_tab_focus((uint8_t)screen);
    }
}

static void idx_tab_key_cb(lv_event_t * event)
{
    uintptr_t screen = (uintptr_t)lv_obj_get_user_data(lv_event_get_target(event));
    if(screen >= 6) return;
    uint32_t key = lv_event_get_key(event);
    if(key == LV_KEY_RIGHT || key == LV_KEY_DOWN) {
        idx_set_tab_focus((uint8_t)((screen + 1) % 6));
    }
    else if(key == LV_KEY_LEFT || key == LV_KEY_UP) {
        idx_set_tab_focus((uint8_t)((screen + 5) % 6));
    }
    else if(key == LV_KEY_HOME) {
        idx_set_tab_focus(0);
    }
    else if(key == LV_KEY_END) {
        idx_set_tab_focus(5);
    }
    else if(key == LV_KEY_ENTER) {
        idx_show_screen((uint8_t)screen, true);
    }
}

/* --------------------------------------------------------------------------
   Shell
   -------------------------------------------------------------------------- */

static void idx_shell_app_bar(lv_obj_t * screen)
{
    idx_box(screen, 0, 0, IDX_W, IDX_APPBAR, 0x070d13, 255, 0, 0, 0, 0, 255);
    idx_box(screen, 0, IDX_APPBAR - 1, IDX_W, 1, COL_LINE, 255, 0, 0, 0, 0, 255);

    /* brand mark (approximates the inline SVG) */
    idx_grad_box(screen, 24, 18, 23, 23, 0x0d2330, 0x08121a,
                 0x24475d, 255, 1, 5);
    idx_box(screen, 26, 20, 19, 19, 0x000000, 0, COL_CYAN, 255, 1, 4, 255);
    idx_box(screen, 35, 20, 1, 19, COL_CYAN, 90, 0, 0, 0, 0, 255);
    idx_box(screen, 26, 29, 19, 1, COL_CYAN, 90, 0, 0, 0, 0, 255);
    idx_box(screen, 32, 26, 7, 7, COL_CYAN, 255, 0, 0, 0, 1, 255);

    idx_simple_text(screen, "LVGL", IDX_F_DISP_15, COL_TEXT, 255,
                    56, 22, 36, 0);
    idx_simple_text(screen, "/", IDX_F_DISP_15, COL_CYAN, 255,
                    92, 22, 6, 0);
    idx_simple_text(screen, "AI", IDX_F_DISP_15, COL_TEXT, 255,
                    97, 22, 14, 0);
    idx_box(screen, 120, 24, 1, 10, COL_LINE_2, 255, 0, 0, 0, 0, 255);
    idx_simple_text(screen, "VERIFY LOOP", IDX_F_MONO_7, COL_DIM, 255,
                    131, 25, 55, 1);
    idx_action_attach(idx_new_obj(screen, 24, 18, 162, 23),
                      IDX_ACT_SCREEN_OVERVIEW);

    /* chips */
    idx_box(screen, 556, 20, 60, 19, 0x0a141e, 179,
            0x34d399, 87, 1, 4, 255);
    idx_led(screen, 563, 27, 5, COL_GREEN, 6);
    idx_simple_text(screen, "HEADLESS", IDX_F_MONO_7, COL_GREEN, 255,
                    573, 25, 36, 1);

    idx_box(screen, 622, 20, 50, 19, 0x0a141e, 179,
            COL_CYAN, 87, 1, 4, 255);
    idx_simple_text(screen, "LVGL 9.6", IDX_F_MONO_7, COL_CYAN, 255,
                    629, 25, 36, 1);

    idx_box(screen, 678, 20, 38, 19, 0x0a141e, 179,
            COL_RED, 97, 1, 4, 255);
    lv_obj_t * rec = idx_led(screen, 685, 27, 5, COL_RED, 6);
    idx_pulse_start(rec, 900);
    idx_simple_text(screen, "REC", IDX_F_MONO_7, COL_RED, 255,
                    695, 25, 13, 1);

    lv_obj_t * gitee_box = idx_box(screen, 721, 17, 55, 25, 0x000000, 0,
                                   COL_LINE_2, 255, 1, 4, 255);
    idx_action_attach(gitee_box, IDX_ACT_LOG);
    static const idx_seg_t gitee[] = {
        {"Gitee ", IDX_F_MONO_8},
        {"\xe2\x86\x97", IDX_F_SYMBOL_8},
    };
    idx_text_line(screen, 730, 24, gitee, 2, COL_TEXT_SOFT, 255, 0,
                  37, 0, 0);
}

static void idx_shell_tabbar(lv_obj_t * screen)
{
    idx_box(screen, 0, IDX_APPBAR, IDX_W, IDX_TABBAR, 0x060b11, 255,
            0, 0, 0, 0, 255);
    idx_box(screen, 0, IDX_APPBAR + IDX_TABBAR - 1, IDX_W, 1, COL_LINE,
            255, 0, 0, 0, 0, 255);

    uint8_t i;
    for(i = 0; i < 6; i++) {
        const idx_tab_spec_t * s = &idx_tab_specs[i];
        lv_obj_t * tab = idx_box(screen, s->x, IDX_APPBAR, s->w,
                                 IDX_TABBAR - 1, 0x000000, 0, 0, 0, 0, 0, 255);
        lv_obj_set_user_data(tab, (void *)(uintptr_t)i);
        lv_obj_set_clickable(tab, true);
        lv_obj_add_event_cb(tab, idx_tab_click_cb, LV_EVENT_CLICKED, NULL);
        lv_obj_add_event_cb(tab, idx_tab_key_cb, LV_EVENT_KEY, NULL);
        lv_obj_set_style_outline_width(tab, 2, LV_STATE_FOCUS_KEY);
        lv_obj_set_style_outline_color(tab, lv_color_hex(COL_CYAN),
                                       LV_STATE_FOCUS_KEY);
        lv_obj_set_style_outline_pad(tab, 2, LV_STATE_FOCUS_KEY);
        lv_obj_set_style_bg_color(tab, lv_color_hex(COL_CYAN), LV_STATE_PRESSED);
        lv_obj_set_style_bg_opa(tab, 14, LV_STATE_PRESSED);
        idx_tabs[i] = tab;

        idx_tab_nums[i] = idx_simple_text(screen, s->number, IDX_F_MONO_8,
                                          COL_CYAN, 153, s->num_x, 77,
                                          s->num_w, 0);
        idx_tab_names[i] = idx_simple_text(screen, s->name, IDX_F_MONO_8,
                                           COL_DIM, 255, s->name_x, 77,
                                           s->name_w, 0);
        idx_tab_lines[i] = idx_box(screen, s->x, IDX_APPBAR + IDX_TABBAR - 3,
                                   s->w, 2, COL_CYAN, 0, 0, 0, 0, 0, 255);
        if(idx_group) lv_group_add_obj(idx_group, tab);
    }
}

static void idx_shell_statusbar(lv_obj_t * screen)
{
    int32_t y = IDX_H - IDX_STATUSBAR;
    idx_box(screen, 0, y, IDX_W, IDX_STATUSBAR, 0x050a0f, 255,
            0, 0, 0, 0, 255);
    idx_box(screen, 0, y, IDX_W, 1, COL_LINE, 255, 0, 0, 0, 0, 255);
    idx_led(screen, 14, y + 11, 5, COL_GREEN, 6);
    idx_simple_text(screen, "READY", IDX_F_MONO_7, COL_DIM, 255,
                    25, y + 9, 21, 1);
    idx_simple_text(screen, "EVIDENCE ONLY", IDX_F_MONO_7, COL_DIM, 255,
                    61, y + 9, 54, 1);
    idx_simple_text(screen, "HUMAN DECIDES", IDX_F_MONO_7, COL_AMBER, 255,
                    130, y + 9, 54, 1);
    idx_simple_text(screen, "LVGL 9.6 \xc2\xb7 800 \xc3\x97 600 \xc2\xb7 VIRTUAL TIME",
                    IDX_F_MONO_7, COL_DIM, 255, 388, y + 9, 144, 1);
    idx_simple_text(screen, "SESSION 0001", IDX_F_MONO_7, COL_DIM, 255,
                    736, y + 9, 50, 1);
}

/* --------------------------------------------------------------------------
   Entry
   -------------------------------------------------------------------------- */

static void idx_stop_loop_playback(void)
{
    idx_loop_playing = false;
    idx_loop_update_play_button();
}

void idx_ui_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    app_set_name("index");

    lv_obj_set_style_bg_color(screen, lv_color_hex(COL_BG_TOP), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_hex(COL_BG_BOT), 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_grad_stop(screen, 255, 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    idx_fonts_init();

    idx_group = lv_group_create();
    lv_group_set_wrap(idx_group, true);

    idx_shell_app_bar(screen);
    idx_shell_tabbar(screen);
    idx_shell_statusbar(screen);

    idx_workspace = idx_new_obj(screen, 0, IDX_WORKSPACE_Y,
                                IDX_W, IDX_WORKSPACE_H);
    app_obj_set_name(idx_workspace, "workspace");
    lv_obj_set_scrollable(idx_workspace, true);
    lv_obj_set_scroll_dir(idx_workspace, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(idx_workspace, LV_SCROLLBAR_MODE_OFF);

    uint8_t i;
    for(i = 0; i < 6; i++) {
        lv_obj_t * content = idx_new_obj(idx_workspace, 0, 0,
                                         IDX_W, idx_screens[i]->content_h);
        static const char * content_names[6] = {
            "screen_overview", "screen_loop", "screen_evidence",
            "screen_inspector", "screen_versions", "screen_start"
        };
        app_obj_set_name(content, content_names[i]);
        lv_obj_set_hidden(content, true);
        lv_obj_set_size(content, 0, 0);
        idx_build_screen_content(content, idx_screens[i]);
        idx_contents[i] = content;
    }
    idx_loop_build(idx_contents[1]);
    idx_inspector_build(idx_contents[3]);
    idx_versions_build(idx_contents[4]);
    idx_watch_build(idx_contents[4]);

    /* Attach the keypad/encoder to our tab group. */
    lv_indev_t * indev = lv_indev_get_next(NULL);
    while(indev) {
        lv_indev_type_t type = lv_indev_get_type(indev);
        if(type == LV_INDEV_TYPE_KEYPAD || type == LV_INDEV_TYPE_ENCODER) {
            lv_indev_set_group(indev, idx_group);
        }
        indev = lv_indev_get_next(indev);
    }

    idx_current = 255;
    idx_show_screen(0, false);
    lv_group_focus_obj(idx_tabs[0]);

    printf("[index] ui created, %u fonts\n", (unsigned)IDX_F_COUNT);
}

#endif /* LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6 */
