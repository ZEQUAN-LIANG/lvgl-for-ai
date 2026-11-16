
#include "coffee_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include <stdio.h>

static lv_obj_t * page;
static lv_obj_t * card_status[4];
static lv_obj_t * card_fill[4];
static lv_obj_t * grounds_value;
static lv_obj_t * grounds_fill;
static lv_obj_t * stats_brews;
static lv_obj_t * stats_since;

static lv_timer_t * run_timer;
static uint32_t run_start;
static uint32_t run_duration;
static int run_which;
static lv_obj_t * run_step;
static lv_obj_t * run_percent;
static lv_obj_t * run_fill;

static const char * const card_titles[4] = {
    COFFEE_TXT_RINSE,
    COFFEE_TXT_MILK_CLEAN,
    COFFEE_TXT_DESCALE,
    COFFEE_TXT_FILTER,
};
static const char * const card_descs[4] = {
    COFFEE_TXT_RINSE_DESC,
    COFFEE_TXT_MILK_CLEAN_DESC,
    COFFEE_TXT_DESCALE_DESC,
    COFFEE_TXT_FILTER_DESC,
};
static const char * const card_actions[4] = {
    COFFEE_TXT_RUN_RINSE,
    COFFEE_TXT_RUN_MILK,
    COFFEE_TXT_RUN_DESCALE,
    COFFEE_TXT_RUN_FILTER,
};
static const coffee_icon_id_t card_icons[4] = {
    COFFEE_ICON_CLEAN,
    COFFEE_ICON_STEAM,
    COFFEE_ICON_DESCALE,
    COFFEE_ICON_FILTER,
};
static const char * const done_texts[4] = {
    COFFEE_TXT_RINSE_DONE,
    COFFEE_TXT_MILK_DONE,
    COFFEE_TXT_DESCALE_DONE,
    COFFEE_TXT_FILTER_DONE,
};
static const char * const run_ids[4] = {
    "maintenance_run_0",
    "maintenance_run_1",
    "maintenance_run_2",
    "maintenance_run_3",
};
static const char * const refill_ids[3] = {
    "refill_water",
    "refill_beans",
    "refill_milk",
};

static int * life_value(int which)
{
    switch(which) {
        case 0:
            return &coffee_state.rinse_pct;
        case 1:
            return &coffee_state.milk_clean_pct;
        case 2:
            return &coffee_state.scale_pct;
        default:
            return &coffee_state.filter_pct;
    }
}

static void run_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_open_maintenance_run((int)(intptr_t)lv_event_get_user_data(event));
}

static void refill_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int which = (int)(intptr_t)lv_event_get_user_data(event);
    switch(which) {
        case 0:
            coffee_state.water_ml = coffee_state.water_cap_ml;
            coffee_log("refill water=%d", coffee_state.water_ml);
            coffee_toast(COFFEE_TXT_WATER_FILLED);
            break;
        case 1:
            coffee_state.beans_g = coffee_state.beans_cap_g;
            coffee_log("refill beans=%d", coffee_state.beans_g);
            coffee_toast(COFFEE_TXT_BEANS_FILLED);
            break;
        case 2:
            coffee_state.milk_ml = coffee_state.milk_cap_ml;
            coffee_log("refill milk=%d", coffee_state.milk_ml);
            coffee_toast(COFFEE_TXT_MILK_FILLED);
            break;
        default:
            coffee_state.grounds_pct = 0;
            coffee_log("empty grounds");
            coffee_toast(COFFEE_TXT_GROUNDS_EMPTIED);
            break;
    }
    coffee_maintenance_refresh();
    coffee_home_refresh();
}

static void run_timer_cb(lv_timer_t * timer)
{
    (void)timer;
    uint32_t elapsed = lv_tick_elaps(run_start);
    int pct = (int)(elapsed * 100u / run_duration);
    if(pct > 100) pct = 100;
    coffee_bar_set(run_fill, pct);

    char buffer[16];
    snprintf(buffer, sizeof(buffer), "%d%%", pct);
    lv_label_set_text(run_percent, buffer);

    const char * step;
    if(pct < 8) step = COFFEE_TXT_MAINT_PREPARE;
    else if(pct < 32)
        step = COFFEE_TXT_MAINT_FILL;
    else if(pct < 74)
        step = COFFEE_TXT_MAINT_CIRCULATE;
    else if(pct < 96)
        step = COFFEE_TXT_MAINT_RINSE;
    else
        step = COFFEE_TXT_MAINT_FINISH;
    lv_label_set_text(run_step, step);

    if(pct >= 100) {
        int * life = life_value(run_which);
        *life = 100;
        coffee_log("maintenance done which=%d life=%d", run_which, *life);
        lv_timer_t * finished = run_timer;
        run_timer = NULL;
        if(finished != NULL) lv_timer_delete(finished);
        coffee_modal_close();
        coffee_toast(done_texts[run_which]);
        coffee_maintenance_refresh();
        coffee_home_refresh();
    }
}

void coffee_maintenance_abort(void)
{
    if(run_timer != NULL) {
        lv_timer_delete(run_timer);
        run_timer = NULL;
    }
}

static void run_cancel_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_log("maintenance cancel which=%d", run_which);
    coffee_modal_close();
    coffee_toast(COFFEE_TXT_CANCELED);
}

void coffee_open_maintenance_run(int which)
{
    if(which < 0 || which > 3) return;
    run_which = which;
    run_duration = 5000u + (uint32_t)which * 1200u;
    run_start = lv_tick_get();
    coffee_log("maintenance start which=%d", which);

    lv_obj_t * panel = coffee_modal_open(480, 360);
    if(panel == NULL) return;

    coffee_icon_obj(panel, card_icons[which], 24, 20, 30, COFFEE_GOLD);
    coffee_label_at(panel, card_titles[which], COFFEE_FT_24B, COFFEE_CREAM, 68,
                    18, 300, 32);
    coffee_label_at(panel, card_descs[which], COFFEE_FT_13, COFFEE_MUTED, 24,
                    58, 420, 18);

    lv_obj_t * shade = coffee_box(panel, 24, 96, 432, 150);
    lv_obj_set_style_radius(shade, 18, 0);
    lv_obj_set_style_bg_color(shade, lv_color_hex(COFFEE_CARD_UP), 0);
    lv_obj_set_style_bg_opa(shade, LV_OPA_COVER, 0);

    run_step = coffee_label_at(panel, COFFEE_TXT_MAINT_PREPARE, COFFEE_FT_16,
                               COFFEE_CREAM, 48, 116, 384, 22);
    run_fill =
        coffee_bar(panel, 48, 150, 384, 8, COFFEE_LINE, COFFEE_GOLD, NULL);
    run_percent = coffee_label_at(panel, "0%", COFFEE_FT_32B,
                                  COFFEE_GOLD_BRIGHT, 48, 168, 384, 42);
    lv_obj_set_style_text_align(run_percent, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t * cancel =
        coffee_button(panel, 170, 282, 140, 44, false, COFFEE_TXT_CANCEL,
                      COFFEE_FT_14B, "maintenance_cancel");
    lv_obj_add_event_cb(cancel, run_cancel_event_cb, LV_EVENT_CLICKED, NULL);

    run_timer = lv_timer_create(run_timer_cb, 80, NULL);
}

void coffee_maintenance_refresh(void)
{
    if(page == NULL) return;
    for(int i = 0; i < 4; i++) {
        int * life = life_value(i);
        char buffer[24];
        snprintf(buffer, sizeof(buffer), "%d%%", *life);
        lv_label_set_text(card_status[i], buffer);
        coffee_bar_set(card_fill[i], *life);
        lv_obj_set_style_bg_color(
            card_fill[i], lv_color_hex(*life < 30 ? COFFEE_RED : COFFEE_GOLD),
            0);
    }

    char buffer[24];
    snprintf(buffer, sizeof(buffer), "%d%%", coffee_state.grounds_pct);
    lv_label_set_text(grounds_value, buffer);
    coffee_bar_set(grounds_fill, coffee_state.grounds_pct);
    lv_obj_set_style_bg_color(
        grounds_fill,
        lv_color_hex(coffee_state.grounds_pct > 85 ? COFFEE_RED : COFFEE_AMBER),
        0);

    snprintf(buffer, sizeof(buffer), "%s%d", COFFEE_TXT_BREW_COUNT_LABEL,
             coffee_state.brew_count);
    lv_label_set_text(stats_brews, buffer);
    snprintf(buffer, sizeof(buffer), "%s%d%s", COFFEE_TXT_BREWS_SINCE,
             coffee_state.cups_since_descale, COFFEE_TXT_BREWS_SINCE_SUFFIX);
    lv_label_set_text(stats_since, buffer);
}

static void build_card(lv_obj_t * parent, int which)
{
    int x = 20 + (which % 2) * 340;
    int y = 86 + (which / 2) * 152;
    lv_obj_t * card =
        coffee_card(parent, x, y, 324, 138, 18, COFFEE_CARD, COFFEE_LINE);
    coffee_icon_obj(card, card_icons[which], 16, 14, 26, COFFEE_GOLD);
    coffee_label_at(card, card_titles[which], COFFEE_FT_16, COFFEE_CREAM, 52,
                    12, 240, 22);
    coffee_label_at(card, card_descs[which], COFFEE_FT_12, COFFEE_MUTED, 16, 42,
                    292, 16);
    card_status[which] =
        coffee_label_at(card, "", COFFEE_FT_13, COFFEE_CREAM, 16, 66, 120, 18);
    card_fill[which] =
        coffee_bar(card, 16, 92, 180, 6, COFFEE_LINE, COFFEE_GOLD, NULL);
    lv_obj_t * action =
        coffee_button(card, 206, 80, 102, 38, false, card_actions[which],
                      COFFEE_FT_13, run_ids[which]);
    lv_obj_add_event_cb(action, run_event_cb, LV_EVENT_CLICKED,
                        coffee_int(which));
}

lv_obj_t * coffee_maintenance_create(lv_obj_t * parent)
{
    page = coffee_box(parent, 0, 0, COFFEE_PAGE_W, COFFEE_PAGE_H);
    coffee_label_at(page, COFFEE_TXT_MAINT_TITLE, COFFEE_FT_24B, COFFEE_CREAM,
                    20, 12, 320, 32);
    coffee_label_at(page, COFFEE_TXT_MAINT_SUB, COFFEE_FT_13, COFFEE_MUTED, 20,
                    48, 420, 18);

    for(int i = 0; i < 4; i++) build_card(page, i);

    lv_obj_t * bottom =
        coffee_card(page, 20, 396, 664, 126, 18, COFFEE_CARD, COFFEE_LINE);
    coffee_label_at(bottom, COFFEE_TXT_GROUNDS_BIN, COFFEE_FT_14B, COFFEE_CREAM,
                    16, 12, 120, 20);
    grounds_value = coffee_label_at(bottom, "", COFFEE_FT_13, COFFEE_AMBER, 136,
                                    13, 48, 18);
    grounds_fill =
        coffee_bar(bottom, 16, 40, 180, 6, COFFEE_LINE, COFFEE_AMBER, NULL);
    lv_obj_t * empty =
        coffee_button(bottom, 16, 62, 116, 40, false, COFFEE_TXT_EMPTY_GROUNDS,
                      COFFEE_FT_13, "empty_grounds");
    lv_obj_add_event_cb(empty, refill_event_cb, LV_EVENT_CLICKED,
                        coffee_int(3));

    lv_obj_t * divider = coffee_box(bottom, 214, 12, 1, 102);
    lv_obj_set_style_bg_color(divider, lv_color_hex(COFFEE_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);

    coffee_label_at(bottom, COFFEE_TXT_SUPPLIES, COFFEE_FT_14B, COFFEE_CREAM,
                    236, 12, 140, 20);
    static const char * const refill_texts[3] = {
        COFFEE_TXT_REFILL_WATER,
        COFFEE_TXT_REFILL_BEANS,
        COFFEE_TXT_REFILL_MILK,
    };
    for(int i = 0; i < 3; i++) {
        lv_obj_t * button =
            coffee_button(bottom, 236 + i * 96, 44, 88, 54, false,
                          refill_texts[i], COFFEE_FT_12, refill_ids[i]);
        lv_obj_add_event_cb(button, refill_event_cb, LV_EVENT_CLICKED,
                            coffee_int(i));
    }

    stats_brews = coffee_label_at(bottom, "", COFFEE_FT_12, COFFEE_MUTED, 520,
                                  16, 132, 18);
    stats_since = coffee_label_at(bottom, "", COFFEE_FT_12, COFFEE_MUTED, 520,
                                  48, 132, 18);
    coffee_label_at(bottom, COFFEE_TXT_RUNTIME, COFFEE_FT_12, COFFEE_MUTED, 520,
                    80, 132, 18);

    coffee_maintenance_refresh();
    return page;
}

#endif
