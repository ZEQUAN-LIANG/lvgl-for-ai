/**
 * @file intro.c
 * Default landing screen for the distributable skill.
 *
 * Ported from docs/mockups/intro.html. Only LVGL 9.4+ primitives are used:
 * rectangles, gradients, borders, shadows, labels, a button, a bar, an arc
 * and timers/animations. No images or custom fonts are required.
 */

#include "intro.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "app.h"

#include <stdio.h>

#define INTRO_BG_TOP    0x0A1017
#define INTRO_BG_BOTTOM 0x070B10
#define INTRO_HOLE      0x080D13
#define INTRO_PANEL     0x0B131C
#define INTRO_PANEL_DEEP 0x091017
#define INTRO_ACTIVE_A  0x102433
#define INTRO_ACTIVE_B  0x0B1822
#define INTRO_DONE_A    0x0A1617
#define INTRO_DONE_B    0x081012
#define INTRO_LINE      0x182430
#define INTRO_LINE_2    0x223447
#define INTRO_LINE_3    0x2B3E52
#define INTRO_TEXT      0xF2F7FB
#define INTRO_MUTED     0x93A6B9
#define INTRO_DIM       0x6B8198
#define INTRO_FAINT     0x40566B
#define INTRO_ACCENT    0x38BDF8
#define INTRO_ACCENT_DEEP 0x1E5C7A
#define INTRO_GREEN     0x34D399
#define INTRO_INK       0x04131C
#define INTRO_DISC_BORDER 0x1B2C3C
#define INTRO_CONSOLE_BORDER 0x1B2A39

typedef enum {
    INTRO_CARD_IDLE,
    INTRO_CARD_NEXT,
    INTRO_CARD_ACTIVE,
    INTRO_CARD_DONE,
} intro_card_state_t;

typedef enum {
    INTRO_NODE_IDLE,
    INTRO_NODE_NEXT,
    INTRO_NODE_ACTIVE,
    INTRO_NODE_DONE,
} intro_node_state_t;

static const char * const intro_titles[4] = {
    "WRITE", "BUILD", "RECORD", "READ",
};
static const char * const intro_bodies[4] = {
    "Author the LVGL C interface.",
    "Build the real headless host.",
    "Replay input, record frames.",
    "Read timeline, diffs, logs.",
};
static const char * const intro_card_names[4] = {
    "intro_card_write",
    "intro_card_build",
    "intro_card_record",
    "intro_card_read",
};
static const char * const intro_statuses[4] = {
    "WRITING", "BUILDING", "RECORDING", "READING",
};
static const char * const intro_details[4] = {
    "AUTHOR THE LVGL C INTERFACE",
    "BUILD THE REAL HEADLESS HOST",
    "REPLAY INPUT, RECORD FRAMES",
    "READ TIMELINE, DIFFS, LOGS",
};

static lv_obj_t * intro_cards[4];
static lv_obj_t * intro_spines[4];
static lv_obj_t * intro_nums[4];
static lv_obj_t * intro_dividers[4];
static lv_obj_t * intro_titles_lbl[4];
static lv_obj_t * intro_bodies_lbl[4];
static lv_obj_t * intro_inds[4];
static lv_obj_t * intro_halos[4];
static lv_obj_t * intro_nodes[5];

static lv_obj_t * intro_step_readout;
static lv_obj_t * intro_arc;
static lv_obj_t * intro_disc;
static lv_obj_t * intro_disc_number;
static lv_obj_t * intro_disc_rule;
static lv_obj_t * intro_disc_caption;
static lv_obj_t * intro_disc_percent;
static lv_obj_t * intro_status_dot;
static lv_obj_t * intro_status;
static lv_obj_t * intro_detail;
static lv_obj_t * intro_console_percent;
static lv_obj_t * intro_bar;
static lv_obj_t * intro_button;
static lv_obj_t * intro_button_label;
static lv_timer_t * intro_timer;
static int intro_step = -1;
static int32_t intro_arc_value;

static void intro_pulse_cb(void * var, int32_t value)
{
    lv_obj_set_style_opa((lv_obj_t *)var, (lv_opa_t)value, 0);
}

static void intro_breathe(lv_obj_t * obj, uint32_t time)
{
    lv_anim_t anim;
    lv_anim_init(&anim);
    lv_anim_set_var(&anim, obj);
    lv_anim_set_values(&anim, 255, 89);
    lv_anim_set_time(&anim, time / 2);
    lv_anim_set_playback_time(&anim, time / 2);
    lv_anim_set_repeat_count(&anim, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_exec_cb(&anim, intro_pulse_cb);
    lv_anim_start(&anim);
}

static void intro_arc_anim_cb(void * var, int32_t value)
{
    (void)var;
    intro_arc_value = value;
    lv_arc_set_value(intro_arc, value);
    lv_bar_set_value(intro_bar, value, LV_ANIM_OFF);
    lv_label_set_text_fmt(intro_disc_percent, "%02d%%", value);
    lv_label_set_text_fmt(intro_console_percent, "%02d%%", value);
}

static void intro_animate_arc(int32_t target)
{
    lv_anim_t anim;
    lv_anim_del(&intro_arc_value, intro_arc_anim_cb);
    lv_anim_init(&anim);
    lv_anim_set_var(&anim, &intro_arc_value);
    lv_anim_set_values(&anim, intro_arc_value, target);
    lv_anim_set_time(&anim, 520);
    lv_anim_set_exec_cb(&anim, intro_arc_anim_cb);
    lv_anim_start(&anim);
}

static void intro_reset_arc(void)
{
    lv_anim_del(&intro_arc_value, intro_arc_anim_cb);
    intro_arc_value = 0;
    lv_arc_set_value(intro_arc, 0);
    lv_bar_set_value(intro_bar, 0, LV_ANIM_OFF);
    lv_label_set_text(intro_disc_percent, "00%");
    lv_label_set_text(intro_console_percent, "00%");
}

static void intro_status_breathe(void)
{
    lv_anim_del(intro_status_dot, intro_pulse_cb);
    intro_breathe(intro_status_dot, 1600);
}

static lv_obj_t * intro_rect(
    lv_obj_t * parent, int x, int y, int w, int h,
    uint32_t color, lv_opa_t opa, int radius)
{
    lv_obj_t * obj = lv_obj_create(parent);
    app_obj_set_scrollable(obj, false);
    app_obj_set_clickable(obj, false);
    lv_obj_set_pos(obj, x, y);
    lv_obj_set_size(obj, w, h);
    lv_obj_set_style_bg_color(obj, lv_color_hex(color), 0);
    lv_obj_set_style_bg_opa(obj, opa, 0);
    lv_obj_set_style_border_width(obj, 0, 0);
    lv_obj_set_style_radius(obj, radius, 0);
    return obj;
}

static lv_obj_t * intro_label(
    lv_obj_t * parent, const char * text, const lv_font_t * font,
    uint32_t color, int x, int y, int letter_space)
{
    lv_obj_t * label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    lv_obj_set_style_text_letter_space(label, letter_space, 0);
    lv_obj_set_pos(label, x, y);
    app_obj_set_clickable(label, false);
    return label;
}

static lv_obj_t * intro_dot(
    lv_obj_t * parent, int x, int y, int size,
    uint32_t border_color, bool border, uint32_t fill, lv_opa_t fill_opa)
{
    lv_obj_t * dot = lv_obj_create(parent);
    app_obj_set_scrollable(dot, false);
    app_obj_set_clickable(dot, false);
    lv_obj_set_pos(dot, x, y);
    lv_obj_set_size(dot, size, size);
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_border_width(dot, border ? 1 : 0, 0);
    lv_obj_set_style_border_color(dot, lv_color_hex(border_color), 0);
    lv_obj_set_style_bg_color(dot, lv_color_hex(fill), 0);
    lv_obj_set_style_bg_opa(dot, fill_opa, 0);
    return dot;
}

static void intro_card_state(int index, int state)
{
    lv_obj_t * card = intro_cards[index];
    uint32_t bg1;
    uint32_t bg2;
    uint32_t border;
    uint32_t spine;
    uint32_t num;
    uint32_t title;
    uint32_t body;
    uint32_t ind_border;
    uint32_t ind_bg;
    lv_opa_t ind_opa;
    lv_opa_t halo_opa;
    int border_w;
    int ind_border_w;
    int shadow_w;

    switch(state) {
        case INTRO_CARD_NEXT:
            bg1 = 0x0C1822;
            bg2 = 0x091119;
            border = 0x1D394C;
            spine = 0x245C78;
            num = 0x6FB9DC;
            title = 0xE7F2FA;
            body = 0x7F94A8;
            ind_border = 0x2E6B8B;
            ind_bg = INTRO_PANEL_DEEP;
            ind_opa = LV_OPA_TRANSP;
            halo_opa = LV_OPA_TRANSP;
            border_w = 1;
            ind_border_w = 1;
            shadow_w = 0;
            break;
        case INTRO_CARD_ACTIVE:
            bg1 = INTRO_ACTIVE_A;
            bg2 = INTRO_ACTIVE_B;
            border = INTRO_ACCENT;
            spine = INTRO_ACCENT;
            num = INTRO_ACCENT;
            title = INTRO_TEXT;
            body = 0xB5C7D6;
            ind_border = INTRO_ACCENT;
            ind_bg = INTRO_ACTIVE_B;
            ind_opa = LV_OPA_COVER;
            halo_opa = 140;
            border_w = 1;
            ind_border_w = 2;
            shadow_w = 28;
            break;
        case INTRO_CARD_DONE:
            bg1 = INTRO_DONE_A;
            bg2 = INTRO_DONE_B;
            border = 0x1D3A34;
            spine = INTRO_GREEN;
            num = INTRO_GREEN;
            title = 0xBDCDD8;
            body = 0x70879A;
            ind_border = INTRO_GREEN;
            ind_bg = INTRO_GREEN;
            ind_opa = LV_OPA_COVER;
            halo_opa = LV_OPA_TRANSP;
            border_w = 1;
            ind_border_w = 1;
            shadow_w = 0;
            break;
        case INTRO_CARD_IDLE:
        default:
            bg1 = 0x0C141D;
            bg2 = INTRO_PANEL_DEEP;
            border = INTRO_LINE;
            spine = INTRO_LINE;
            num = INTRO_FAINT;
            title = 0xD8E3ED;
            body = 0x7F94A8;
            ind_border = INTRO_LINE_3;
            ind_bg = INTRO_PANEL_DEEP;
            ind_opa = LV_OPA_TRANSP;
            halo_opa = LV_OPA_TRANSP;
            border_w = 1;
            ind_border_w = 1;
            shadow_w = 0;
            break;
    }

    lv_obj_set_style_bg_color(card, lv_color_hex(bg1), 0);
    lv_obj_set_style_bg_grad_color(card, lv_color_hex(bg2), 0);
    lv_obj_set_style_border_color(card, lv_color_hex(border), 0);
    lv_obj_set_style_border_width(card, border_w, 0);
    lv_obj_set_style_shadow_width(card, shadow_w, 0);
    lv_obj_set_style_shadow_opa(card, shadow_w > 0 ? 30 : LV_OPA_TRANSP, 0);
    lv_obj_set_style_shadow_color(card, lv_color_hex(INTRO_ACCENT), 0);
    lv_obj_set_style_shadow_offset_y(card, 10, 0);

    lv_obj_set_style_bg_color(intro_spines[index], lv_color_hex(spine), 0);
    lv_obj_set_style_bg_opa(
        intro_spines[index], state == INTRO_CARD_IDLE
                             ? LV_OPA_TRANSP : LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(
        intro_dividers[index],
        lv_color_hex(state == INTRO_CARD_ACTIVE ? 0x1B3A4E
                     : (state == INTRO_CARD_DONE ? 0x17332D : INTRO_LINE)), 0);
    lv_obj_set_style_text_color(intro_nums[index], lv_color_hex(num), 0);
    lv_obj_set_style_text_color(intro_titles_lbl[index], lv_color_hex(title), 0);
    lv_obj_set_style_text_color(intro_bodies_lbl[index], lv_color_hex(body), 0);
    lv_obj_set_style_border_color(
        intro_inds[index], lv_color_hex(ind_border), 0);
    lv_obj_set_style_border_width(
        intro_inds[index], ind_border_w, 0);
    lv_obj_set_style_bg_color(
        intro_inds[index], lv_color_hex(ind_bg), 0);
    lv_obj_set_style_bg_opa(intro_inds[index], ind_opa, 0);
    lv_obj_set_style_border_color(
        intro_halos[index],
        lv_color_hex(state == INTRO_CARD_DONE ? INTRO_GREEN : INTRO_ACCENT), 0);
    lv_obj_set_style_opa(intro_halos[index], halo_opa, 0);
}

static void intro_node_state(int index, int state)
{
    lv_obj_t * node = intro_nodes[index];
    uint32_t border;
    uint32_t fill;
    lv_opa_t fill_opa;

    switch(state) {
        case INTRO_NODE_NEXT:
            border = INTRO_ACCENT_DEEP;
            fill = INTRO_BG_BOTTOM;
            fill_opa = LV_OPA_TRANSP;
            break;
        case INTRO_NODE_ACTIVE:
            border = INTRO_ACCENT;
            fill = INTRO_ACCENT;
            fill_opa = LV_OPA_COVER;
            break;
        case INTRO_NODE_DONE:
            border = INTRO_GREEN;
            fill = INTRO_GREEN;
            fill_opa = LV_OPA_COVER;
            break;
        case INTRO_NODE_IDLE:
        default:
            border = INTRO_LINE_3;
            fill = INTRO_BG_BOTTOM;
            fill_opa = LV_OPA_COVER;
            break;
    }

    if(index == 0) {
        lv_obj_set_style_border_width(node, 0, 0);
        lv_obj_set_style_bg_color(
            node, lv_color_hex(state == INTRO_NODE_DONE
                               ? INTRO_GREEN : 0x2E4358), 0);
        lv_obj_set_style_bg_opa(node, LV_OPA_COVER, 0);
        return;
    }

    lv_obj_set_style_border_color(node, lv_color_hex(border), 0);
    lv_obj_set_style_bg_color(node, lv_color_hex(fill), 0);
    lv_obj_set_style_bg_opa(node, fill_opa, 0);
}

static void intro_disc_update(int step)
{
    if(step < 0) {
        lv_label_set_text(intro_disc_number, "01");
        lv_label_set_text(intro_disc_caption, intro_titles[0]);
        lv_obj_set_style_text_color(
            intro_disc_number, lv_color_hex(INTRO_TEXT), 0);
        lv_obj_set_style_bg_color(
            intro_disc_rule, lv_color_hex(INTRO_ACCENT), 0);
        lv_label_set_text(intro_step_readout, "00 / 04");
        return;
    }
    if(step < 4) {
        lv_label_set_text_fmt(intro_disc_number, "%02d", step + 1);
        lv_label_set_text(intro_disc_caption, intro_titles[step]);
        lv_obj_set_style_text_color(
            intro_disc_number, lv_color_hex(INTRO_TEXT), 0);
        lv_obj_set_style_bg_color(
            intro_disc_rule, lv_color_hex(INTRO_ACCENT), 0);
        lv_label_set_text_fmt(intro_step_readout, "%02d / 04", step + 1);
        return;
    }
    lv_label_set_text(intro_disc_number, "OK");
    lv_label_set_text(intro_disc_caption, "EVIDENCE");
    lv_obj_set_style_text_color(
        intro_disc_number, lv_color_hex(INTRO_GREEN), 0);
    lv_obj_set_style_bg_color(
        intro_disc_rule, lv_color_hex(INTRO_GREEN), 0);
    lv_label_set_text(intro_step_readout, "04 / 04");
}

static void intro_status_update(
    const char * status, const char * detail, uint32_t color,
    int percent, bool done)
{
    lv_label_set_text(intro_status, status);
    lv_label_set_text(intro_detail, detail);
    lv_obj_set_style_text_color(intro_status, lv_color_hex(color), 0);
    lv_obj_set_style_bg_color(intro_status_dot, lv_color_hex(color), 0);
    lv_label_set_text_fmt(intro_console_percent, "%02d%%", percent);
    lv_obj_set_style_text_color(
        intro_console_percent,
        lv_color_hex(done ? INTRO_GREEN
                     : (percent > 0 ? INTRO_ACCENT : INTRO_DIM)), 0);
}

static void intro_button_mode(int mode)
{
    if(mode == 1) {
        lv_obj_set_style_bg_color(
            intro_button, lv_color_hex(0x102B3D), 0);
        lv_obj_set_style_bg_opa(intro_button, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(intro_button, 0, 0);
        lv_obj_set_style_shadow_width(intro_button, 0, 0);
        lv_obj_set_style_text_color(
            intro_button_label, lv_color_hex(0x6F8EA6), 0);
        lv_label_set_text(intro_button_label, "RUNNING");
        app_obj_set_clickable(intro_button, false);
        return;
    }
    if(mode == 2) {
        lv_obj_set_style_bg_opa(intro_button, LV_OPA_TRANSP, 0);
        lv_obj_set_style_border_width(intro_button, 1, 0);
        lv_obj_set_style_border_color(
            intro_button, lv_color_hex(INTRO_GREEN), 0);
        lv_obj_set_style_shadow_width(intro_button, 0, 0);
        lv_obj_set_style_text_color(
            intro_button_label, lv_color_hex(INTRO_GREEN), 0);
        lv_label_set_text(intro_button_label, "REPLAY");
        app_obj_set_clickable(intro_button, true);
        return;
    }

    lv_obj_set_style_bg_color(intro_button, lv_color_hex(INTRO_ACCENT), 0);
    lv_obj_set_style_bg_opa(intro_button, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(intro_button, 0, 0);
    lv_obj_set_style_shadow_width(intro_button, 24, 0);
    lv_obj_set_style_shadow_opa(intro_button, 70, 0);
    lv_obj_set_style_shadow_color(
        intro_button, lv_color_hex(INTRO_ACCENT), 0);
    lv_obj_set_style_shadow_offset_y(intro_button, 8, 0);
    lv_obj_set_style_text_color(
        intro_button_label, lv_color_hex(INTRO_INK), 0);
    lv_label_set_text(intro_button_label, "RUN SCENARIO");
    app_obj_set_clickable(intro_button, true);
}

static void intro_apply(int step)
{
    int index;

    if(step < 0) {
        for(index = 0; index < 4; index++) {
            intro_card_state(
                index, index == 0 ? INTRO_CARD_NEXT : INTRO_CARD_IDLE);
        }
        for(index = 0; index < 5; index++) {
            intro_node_state(
                index, index == 1 ? INTRO_NODE_NEXT : INTRO_NODE_IDLE);
        }
        intro_animate_arc(0);
        intro_disc_update(-1);
        lv_label_set_text(intro_disc_percent, "00%");
        lv_label_set_text(intro_console_percent, "00%");
        intro_status_update(
            "READY", "CLICK TO PLAY THE LOOP", INTRO_ACCENT, 0, false);
        lv_obj_set_style_arc_color(
            intro_arc, lv_color_hex(INTRO_ACCENT), LV_PART_INDICATOR);
        lv_obj_set_style_bg_color(
            intro_bar, lv_color_hex(INTRO_ACCENT), LV_PART_INDICATOR);
        lv_obj_set_style_border_color(
            intro_disc, lv_color_hex(INTRO_DISC_BORDER), 0);
        intro_button_mode(0);
        intro_status_breathe();
        return;
    }

    if(step < 4) {
        for(index = 0; index < 4; index++) {
            intro_card_state(
                index,
                index < step ? INTRO_CARD_DONE
                : (index == step ? INTRO_CARD_ACTIVE
                   : (index == step + 1 ? INTRO_CARD_NEXT : INTRO_CARD_IDLE)));
        }
        for(index = 0; index < 5; index++) {
            if(index == 0) {
                intro_node_state(0, INTRO_NODE_DONE);
            }
            else {
                int node_step = index - 1;
                intro_node_state(
                    index,
                    node_step < step ? INTRO_NODE_DONE
                    : (node_step == step ? INTRO_NODE_ACTIVE
                       : (node_step == step + 1 ? INTRO_NODE_NEXT
                          : INTRO_NODE_IDLE)));
            }
        }
        intro_animate_arc((step + 1) * 25);
        intro_disc_update(step);
        intro_status_update(
            intro_statuses[step], intro_details[step], INTRO_ACCENT,
            (step + 1) * 25, false);
        lv_obj_set_style_arc_color(
            intro_arc, lv_color_hex(INTRO_ACCENT), LV_PART_INDICATOR);
        lv_obj_set_style_bg_color(
            intro_bar, lv_color_hex(INTRO_ACCENT), LV_PART_INDICATOR);
        lv_obj_set_style_border_color(
            intro_disc, lv_color_hex(INTRO_DISC_BORDER), 0);
        intro_button_mode(1);
        intro_status_breathe();
        printf("[intro] step=%d %s\n", step + 1, intro_titles[step]);
        return;
    }

    for(index = 0; index < 4; index++) {
        intro_card_state(index, INTRO_CARD_DONE);
    }
    for(index = 0; index < 5; index++) {
        intro_node_state(index, INTRO_NODE_DONE);
    }
    intro_animate_arc(100);
    intro_disc_update(4);
    intro_status_update(
        "EVIDENCE READY", "SESSION EVIDENCE IS READY",
        INTRO_GREEN, 100, true);
    lv_obj_set_style_arc_color(
        intro_arc, lv_color_hex(INTRO_GREEN), LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(
        intro_bar, lv_color_hex(INTRO_GREEN), LV_PART_INDICATOR);
    lv_obj_set_style_border_color(
        intro_disc, lv_color_hex(0x1E4A3D), 0);
    lv_anim_del(intro_status_dot, intro_pulse_cb);
    lv_obj_set_style_opa(intro_status_dot, 255, 0);
    intro_button_mode(2);
}

static void intro_timer_cb(lv_timer_t * timer)
{
    (void)timer;

    if(intro_step < 3) {
        intro_step++;
        intro_apply(intro_step);
    }
    else {
        intro_step = 4;
        intro_apply(4);
        if(intro_timer != NULL) {
            lv_timer_del(intro_timer);
            intro_timer = NULL;
        }
        printf("[intro] evidence ready\n");
    }
}

static void intro_click_cb(lv_event_t * event)
{
    (void)event;

    if(intro_timer != NULL) return;
    if(intro_step >= 0 && intro_step < 4) return;

    intro_reset_arc();
    intro_step = 0;
    intro_apply(0);
    intro_timer = lv_timer_create(intro_timer_cb, 900, NULL);
    printf("[intro] run\n");
}

static lv_obj_t * intro_card_create(lv_obj_t * parent, int index, int y)
{
    lv_obj_t * card = lv_obj_create(parent);
    app_obj_set_name(card, intro_card_names[index]);
    app_obj_set_scrollable(card, false);
    app_obj_set_clickable(card, false);
    lv_obj_set_pos(card, 48, y);
    lv_obj_set_size(card, 348, 62);
    lv_obj_set_style_radius(card, 10, 0);
    lv_obj_set_style_pad_all(card, 0, 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_grad_dir(card, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_border_width(card, 1, 0);

    intro_spines[index] = intro_rect(
        card, 0, 10, 2, 42, INTRO_LINE, LV_OPA_TRANSP, 1);
    intro_nums[index] = intro_label(
        card, "", &lv_font_montserrat_14, INTRO_FAINT, 14, 22, 1);
    lv_label_set_text_fmt(intro_nums[index], "%02d", index + 1);
    intro_dividers[index] = intro_rect(
        card, 44, 11, 1, 40, INTRO_LINE, LV_OPA_COVER, 0);
    intro_titles_lbl[index] = intro_label(
        card, intro_titles[index], &lv_font_montserrat_16,
        INTRO_TEXT, 58, 10, 1);
    intro_bodies_lbl[index] = intro_label(
        card, intro_bodies[index], &lv_font_montserrat_14,
        INTRO_MUTED, 58, 32, 0);
    lv_obj_set_width(intro_bodies_lbl[index], 246);
    lv_label_set_long_mode(intro_bodies_lbl[index], LV_LABEL_LONG_CLIP);

    intro_halos[index] = lv_obj_create(card);
    app_obj_set_scrollable(intro_halos[index], false);
    app_obj_set_clickable(intro_halos[index], false);
    lv_obj_set_pos(intro_halos[index], 315, 19);
    lv_obj_set_size(intro_halos[index], 22, 22);
    lv_obj_set_style_radius(intro_halos[index], LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(intro_halos[index], LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(intro_halos[index], 1, 0);
    lv_obj_set_style_border_color(
        intro_halos[index], lv_color_hex(INTRO_ACCENT), 0);
    lv_obj_set_style_opa(intro_halos[index], LV_OPA_TRANSP, 0);

    intro_inds[index] = lv_obj_create(card);
    app_obj_set_scrollable(intro_inds[index], false);
    app_obj_set_clickable(intro_inds[index], false);
    lv_obj_set_pos(intro_inds[index], 322, 26);
    lv_obj_set_size(intro_inds[index], 10, 10);
    lv_obj_set_style_radius(intro_inds[index], LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_border_width(intro_inds[index], 1, 0);
    lv_obj_set_style_border_color(
        intro_inds[index], lv_color_hex(INTRO_LINE_3), 0);
    lv_obj_set_style_bg_opa(intro_inds[index], LV_OPA_TRANSP, 0);

    return card;
}

static lv_obj_t * intro_bracket(lv_obj_t * parent, int x, int y, int sides)
{
    lv_obj_t * bracket = lv_obj_create(parent);
    app_obj_set_scrollable(bracket, false);
    app_obj_set_clickable(bracket, false);
    lv_obj_set_pos(bracket, x, y);
    lv_obj_set_size(bracket, 18, 18);
    lv_obj_set_style_bg_opa(bracket, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(bracket, 1, 0);
    lv_obj_set_style_border_color(bracket, lv_color_hex(0x203244), 0);
    lv_obj_set_style_border_side(bracket, (lv_border_side_t)sides, 0);
    return bracket;
}

void intro_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    int index;

    app_set_name("intro");
    lv_obj_set_style_bg_color(screen, lv_color_hex(INTRO_BG_TOP), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_hex(INTRO_BG_BOTTOM), 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    /* header */
    lv_obj_t * pulse = intro_dot(
        screen, 48, 37, 6, INTRO_GREEN, false, INTRO_GREEN, LV_OPA_COVER);
    app_obj_set_name(pulse, "intro_pulse");
    intro_breathe(pulse, 2600);

    lv_obj_t * brand = intro_label(
        screen, "", &lv_font_montserrat_16, INTRO_TEXT, 64, 28, 1);
    app_obj_set_name(brand, "intro_brand");
    lv_label_set_recolor(brand, true);
    lv_label_set_text(brand, "#38BDF8 LVGL# #F2F7FB VERIFY LOOP#");

    lv_obj_t * env = intro_label(
        screen, "HEADLESS / LVGL 9.6", &lv_font_montserrat_14,
        INTRO_DIM, 0, 30, 1);
    app_obj_set_name(env, "intro_env");
    lv_obj_align(env, LV_ALIGN_TOP_RIGHT, -48, 30);

    intro_rect(screen, 48, 64, 704, 1, INTRO_LINE, LV_OPA_COVER, 0);
    intro_rect(screen, 48, 63, 24, 2, INTRO_ACCENT, 230, 0);

    /* hero */
    intro_rect(screen, 48, 95, 5, 5, INTRO_ACCENT, LV_OPA_COVER, 0);
    lv_obj_t * eyebrow = intro_label(
        screen, "CLOSED-LOOP TOOLING", &lv_font_montserrat_14,
        INTRO_DIM, 62, 88, 2);
    app_obj_set_name(eyebrow, "intro_eyebrow");
    lv_obj_t * eyebrow_meta = intro_label(
        screen, "04 STEPS", &lv_font_montserrat_14,
        INTRO_FAINT, 0, 88, 2);
    app_obj_set_name(eyebrow_meta, "intro_eyebrow_meta");
    lv_obj_align(eyebrow_meta, LV_ALIGN_TOP_RIGHT, -404, 88);

    lv_obj_t * title = intro_label(
        screen, "", &lv_font_montserrat_20, INTRO_TEXT, 48, 110, 2);
    app_obj_set_name(title, "intro_title");
    lv_label_set_recolor(title, true);
    lv_label_set_text(
        title, "WRITE#38BDF8 .# RUN#38BDF8 .# SEE#38BDF8 .#");

    intro_label(
        screen, "A closed loop for LVGL user apps.",
        &lv_font_montserrat_14, INTRO_MUTED, 48, 139, 0);

    intro_rect(screen, 48, 170, 348, 1, INTRO_LINE, LV_OPA_COVER, 0);
    intro_rect(screen, 48, 169, 40, 2, INTRO_ACCENT, 220, 0);

    /* four-step stack */
    for(index = 0; index < 4; index++) {
        intro_cards[index] = intro_card_create(
            screen, index, 190 + index * 72);
    }

    /* loop gauge */
    lv_obj_t * caption = intro_label(
        screen, "VERIFICATION LOOP", &lv_font_montserrat_14,
        INTRO_DIM, 428, 88, 2);
    app_obj_set_name(caption, "intro_loop_caption");
    intro_step_readout = intro_label(
        screen, "00 / 04", &lv_font_montserrat_14, INTRO_DIM, 0, 88, 1);
    app_obj_set_name(intro_step_readout, "intro_step_readout");
    lv_obj_align(intro_step_readout, LV_ALIGN_TOP_RIGHT, -48, 88);

    intro_bracket(
        screen, 428, 118, LV_BORDER_SIDE_LEFT | LV_BORDER_SIDE_TOP);
    intro_bracket(
        screen, 734, 452, LV_BORDER_SIDE_RIGHT | LV_BORDER_SIDE_BOTTOM);

    lv_obj_t * halo = lv_obj_create(screen);
    app_obj_set_scrollable(halo, false);
    app_obj_set_clickable(halo, false);
    lv_obj_set_pos(halo, 422, 120);
    lv_obj_set_size(halo, 332, 332);
    lv_obj_set_style_radius(halo, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(halo, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(halo, 1, 0);
    lv_obj_set_style_border_color(halo, lv_color_hex(0x17293A), 0);

    intro_arc = lv_arc_create(screen);
    app_obj_set_name(intro_arc, "intro_arc");
    app_obj_set_scrollable(intro_arc, false);
    app_obj_set_clickable(intro_arc, false);
    lv_obj_set_pos(intro_arc, 444, 142);
    lv_obj_set_size(intro_arc, 288, 288);
    lv_arc_set_rotation(intro_arc, 135);
    lv_arc_set_bg_angles(intro_arc, 0, 270);
    lv_arc_set_range(intro_arc, 0, 100);
    lv_arc_set_value(intro_arc, 0);
    lv_obj_set_style_arc_width(intro_arc, 2, LV_PART_MAIN);
    lv_obj_set_style_arc_color(
        intro_arc, lv_color_hex(0x1B2C3B), LV_PART_MAIN);
    lv_obj_set_style_arc_width(intro_arc, 2, LV_PART_INDICATOR);
    lv_obj_set_style_arc_color(
        intro_arc, lv_color_hex(INTRO_ACCENT), LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(intro_arc, LV_OPA_TRANSP, LV_PART_KNOB);
    lv_obj_set_style_pad_all(intro_arc, 0, LV_PART_KNOB);

    lv_obj_t * hole = intro_rect(
        screen, 452, 150, 272, 272, INTRO_HOLE, LV_OPA_COVER,
        LV_RADIUS_CIRCLE);

    intro_disc = lv_obj_create(screen);
    app_obj_set_name(intro_disc, "intro_disc");
    app_obj_set_scrollable(intro_disc, false);
    app_obj_set_clickable(intro_disc, false);
    lv_obj_set_pos(intro_disc, 472, 170);
    lv_obj_set_size(intro_disc, 232, 232);
    lv_obj_set_style_radius(intro_disc, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(intro_disc, lv_color_hex(0x0D1A25), 0);
    lv_obj_set_style_bg_grad_color(intro_disc, lv_color_hex(0x081017), 0);
    lv_obj_set_style_bg_grad_dir(intro_disc, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_opa(intro_disc, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(intro_disc, 1, 0);
    lv_obj_set_style_border_color(
        intro_disc, lv_color_hex(INTRO_DISC_BORDER), 0);
    lv_obj_set_style_shadow_width(intro_disc, 40, 0);
    lv_obj_set_style_shadow_opa(intro_disc, 100, 0);
    lv_obj_set_style_shadow_color(intro_disc, lv_color_hex(0x000000), 0);
    lv_obj_set_style_shadow_offset_y(intro_disc, 18, 0);

    intro_disc_number = intro_label(
        intro_disc, "01", &lv_font_montserrat_20, INTRO_TEXT, 0, 75, 3);
    app_obj_set_name(intro_disc_number, "intro_disc_number");
    lv_obj_set_width(intro_disc_number, 232);
    lv_obj_set_style_text_align(
        intro_disc_number, LV_TEXT_ALIGN_CENTER, 0);

    intro_disc_rule = intro_rect(
        intro_disc, 104, 110, 24, 2, INTRO_ACCENT, LV_OPA_COVER, 0);

    intro_disc_caption = intro_label(
        intro_disc, intro_titles[0], &lv_font_montserrat_14,
        INTRO_MUTED, 0, 118, 2);
    app_obj_set_name(intro_disc_caption, "intro_disc_caption");
    lv_obj_set_width(intro_disc_caption, 232);
    lv_obj_set_style_text_align(
        intro_disc_caption, LV_TEXT_ALIGN_CENTER, 0);

    intro_disc_percent = intro_label(
        intro_disc, "00%", &lv_font_montserrat_14, INTRO_DIM, 0, 140, 1);
    app_obj_set_name(intro_disc_percent, "intro_disc_percent");
    lv_obj_set_width(intro_disc_percent, 232);
    lv_obj_set_style_text_align(
        intro_disc_percent, LV_TEXT_ALIGN_CENTER, 0);

    intro_nodes[0] = intro_dot(
        screen, 473, 397, 4, 0x2E4358, false, 0x2E4358, LV_OPA_COVER);
    app_obj_set_name(intro_nodes[0], "intro_node_start");
    intro_nodes[1] = intro_dot(
        screen, 436, 221, 8, INTRO_LINE_3, true, INTRO_BG_BOTTOM,
        LV_OPA_COVER);
    app_obj_set_name(intro_nodes[1], "intro_node_write");
    intro_nodes[2] = intro_dot(
        screen, 584, 122, 8, INTRO_LINE_3, true, INTRO_BG_BOTTOM,
        LV_OPA_COVER);
    app_obj_set_name(intro_nodes[2], "intro_node_build");
    intro_nodes[3] = intro_dot(
        screen, 732, 221, 8, INTRO_LINE_3, true, INTRO_BG_BOTTOM,
        LV_OPA_COVER);
    app_obj_set_name(intro_nodes[3], "intro_node_record");
    intro_nodes[4] = intro_dot(
        screen, 697, 395, 8, INTRO_LINE_3, true, INTRO_BG_BOTTOM,
        LV_OPA_COVER);
    app_obj_set_name(intro_nodes[4], "intro_node_read");

    /* bottom console */
    lv_obj_t * console = lv_obj_create(screen);
    app_obj_set_name(console, "intro_console");
    app_obj_set_scrollable(console, false);
    app_obj_set_clickable(console, false);
    lv_obj_set_pos(console, 48, 490);
    lv_obj_set_size(console, 704, 76);
    lv_obj_set_style_radius(console, 12, 0);
    lv_obj_set_style_pad_all(console, 0, 0);
    lv_obj_set_style_bg_color(console, lv_color_hex(0x0C1520), 0);
    lv_obj_set_style_bg_grad_color(console, lv_color_hex(0x091019), 0);
    lv_obj_set_style_bg_grad_dir(console, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_opa(console, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(console, 1, 0);
    lv_obj_set_style_border_color(
        console, lv_color_hex(INTRO_CONSOLE_BORDER), 0);
    lv_obj_set_style_shadow_width(console, 34, 0);
    lv_obj_set_style_shadow_opa(console, 110, 0);
    lv_obj_set_style_shadow_color(console, lv_color_hex(0x000000), 0);
    lv_obj_set_style_shadow_offset_y(console, 14, 0);

    intro_status_dot = intro_dot(
        console, 18, 12, 8, INTRO_ACCENT, false, INTRO_ACCENT,
        LV_OPA_COVER);
    app_obj_set_name(intro_status_dot, "intro_status_dot");

    intro_status = intro_label(
        console, "READY", &lv_font_montserrat_16, INTRO_ACCENT, 34, 6, 2);
    app_obj_set_name(intro_status, "intro_status");

    intro_console_percent = intro_label(
        console, "00%", &lv_font_montserrat_14, INTRO_DIM, 392, 6, 1);
    app_obj_set_name(intro_console_percent, "intro_console_percent");
    lv_obj_set_width(intro_console_percent, 72);
    lv_obj_set_style_text_align(
        intro_console_percent, LV_TEXT_ALIGN_RIGHT, 0);

    intro_detail = intro_label(
        console, "CLICK TO PLAY THE LOOP", &lv_font_montserrat_14,
        INTRO_DIM, 34, 29, 1);
    app_obj_set_name(intro_detail, "intro_detail");

    intro_bar = lv_bar_create(console);
    app_obj_set_name(intro_bar, "intro_progress");
    lv_obj_set_pos(intro_bar, 34, 55);
    lv_obj_set_size(intro_bar, 430, 4);
    lv_bar_set_range(intro_bar, 0, 100);
    lv_bar_set_value(intro_bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_radius(intro_bar, 2, LV_PART_MAIN);
    lv_obj_set_style_radius(intro_bar, 2, LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(intro_bar, lv_color_hex(0x1B2A38), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(intro_bar, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_bg_color(
        intro_bar, lv_color_hex(INTRO_ACCENT), LV_PART_INDICATOR);

    intro_rect(console, 484, 12, 1, 52, 0x182838, LV_OPA_COVER, 0);

    intro_button = lv_button_create(console);
    app_obj_set_name(intro_button, "intro_button");
    lv_obj_set_pos(intro_button, 500, 16);
    lv_obj_set_size(intro_button, 184, 44);
    lv_obj_set_style_radius(intro_button, 8, 0);
    lv_obj_set_style_bg_color(intro_button, lv_color_hex(INTRO_ACCENT), 0);
    lv_obj_set_style_bg_opa(intro_button, LV_OPA_COVER, 0);
    lv_obj_set_style_shadow_width(intro_button, 24, 0);
    lv_obj_set_style_shadow_opa(intro_button, 70, 0);
    lv_obj_set_style_shadow_color(
        intro_button, lv_color_hex(INTRO_ACCENT), 0);
    lv_obj_set_style_shadow_offset_y(intro_button, 8, 0);
    lv_obj_add_event_cb(intro_button, intro_click_cb, LV_EVENT_CLICKED, NULL);

    intro_button_label = lv_label_create(intro_button);
    app_obj_set_name(intro_button_label, "intro_button_label");
    lv_label_set_text(intro_button_label, "RUN SCENARIO");
    lv_obj_set_style_text_font(
        intro_button_label, &lv_font_montserrat_16, 0);
    lv_obj_set_style_text_color(
        intro_button_label, lv_color_hex(INTRO_INK), 0);
    lv_obj_set_style_text_letter_space(intro_button_label, 2, 0);
    app_obj_set_clickable(intro_button_label, false);
    lv_obj_center(intro_button_label);

    intro_arc_value = 0;
    intro_step = -1;
    intro_apply(-1);

    printf("[intro] created\n");
}

#endif /* LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4 */
