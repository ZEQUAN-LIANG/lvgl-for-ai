#include "app.h"
#include "coffee_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include <stdio.h>
#include <string.h>

static lv_timer_t * brew_timer;
static lv_timer_t * close_timer;
static uint32_t brew_start;
static uint32_t brew_duration;
static int brew_drink;
static bool brew_finished;

static lv_obj_t * brew_arc;
static lv_obj_t * brew_liquid;
static lv_obj_t * brew_crema;
static lv_obj_t * brew_elapsed;
static lv_obj_t * brew_eta;
static lv_obj_t * brew_pressure;
static lv_obj_t * brew_temp;
static lv_obj_t * brew_title;
static lv_obj_t * brew_check;
static lv_obj_t * brew_cancel;
static lv_obj_t * brew_done;
static lv_obj_t * brew_wisps[3];
static lv_obj_t * phase_dots[6];
static lv_obj_t * phase_checks[6];
static lv_obj_t * phase_labels[6];
static lv_obj_t * phase_status[6];

static const char * phase_names[6];
static int phase_bounds[6];
static int phase_count;

static void close_timer_cb(lv_timer_t * timer);

static void format_mmss(char * buffer, size_t size, uint32_t ms)
{
    uint32_t seconds = ms / 1000u;
    snprintf(buffer, size, "%02u:%02u", (unsigned)(seconds / 60u),
             (unsigned)(seconds % 60u));
}

static uint32_t liquid_color(const coffee_drink_t * drink)
{
    if(drink->water_only) return 0xCFE3E1;
    if(drink->steam_only) return 0xF2E8D8;
    if(drink->cold) return 0x8A5A2A;
    if(drink->art == COFFEE_ART_MOCHA) return 0x6B3D1F;
    if(drink->milk_drink) return 0xB98755;
    if(drink->strength >= 5) return 0x3B1E0C;
    return 0x5A3418;
}

static uint32_t crema_color(const coffee_drink_t * drink)
{
    if(drink->water_only || drink->steam_only || drink->milk_drink) {
        return 0xF7EFE1;
    }
    return 0xD8B07A;
}

static bool check_resources(coffee_drink_t * drink)
{
    int cups = drink->double_cup ? 2 : 1;
    int water_needed = drink->steam_only ? 100 : drink->volume * cups + 30;
    if(coffee_state.water_ml < water_needed) {
        coffee_log("brew blocked reason=water need=%d have=%d", water_needed,
                   coffee_state.water_ml);
        coffee_toast(COFFEE_TXT_TOAST_LOW_WATER);
        return false;
    }
    if(!drink->water_only && !drink->steam_only) {
        int beans_needed = (6 + drink->strength * 2) * cups;
        if(coffee_state.beans_g < beans_needed) {
            coffee_log("brew blocked reason=beans need=%d have=%d",
                       beans_needed, coffee_state.beans_g);
            coffee_toast(COFFEE_TXT_TOAST_LOW_BEANS);
            return false;
        }
    }
    if(drink->milk_drink) {
        int milk_needed = drink->milk_ml * cups;
        if(coffee_state.milk_ml < milk_needed) {
            coffee_log("brew blocked reason=milk need=%d have=%d", milk_needed,
                       coffee_state.milk_ml);
            coffee_toast(COFFEE_TXT_TOAST_LOW_MILK);
            return false;
        }
    }
    return true;
}

static int active_phase(int pct)
{
    for(int i = 0; i < phase_count; i++) {
        if(pct < phase_bounds[i]) return i;
    }
    return phase_count - 1;
}

static void update_phases(int pct)
{
    int active = active_phase(pct);
    for(int i = 0; i < phase_count; i++) {
        bool done = pct >= phase_bounds[i];
        bool running = !done && i == active;
        const char * status = done      ? COFFEE_TXT_STATUS_DONE
                              : running ? COFFEE_TXT_STATUS_ACTIVE
                                        : COFFEE_TXT_STATUS_WAIT;
        lv_label_set_text(phase_status[i], status);
        lv_obj_set_style_text_color(phase_labels[i],
                                    lv_color_hex(done      ? COFFEE_MUTED
                                                 : running ? COFFEE_CREAM
                                                           : COFFEE_DIM),
                                    0);
        lv_obj_set_style_bg_color(phase_dots[i],
                                  lv_color_hex(done      ? COFFEE_GREEN
                                               : running ? COFFEE_GOLD
                                                         : COFFEE_CARD_UP),
                                  0);
        coffee_hide(phase_checks[i], !done);
        if(done) {
            lv_obj_set_style_image_recolor(phase_checks[i],
                                           lv_color_hex(0x16210F), 0);
        }
    }
}

static void brew_finish(void)
{
    brew_finished = true;
    if(brew_timer != NULL) {
        lv_timer_delete(brew_timer);
        brew_timer = NULL;
    }

    coffee_drink_t * drink = &coffee_drinks[brew_drink];
    int cups = drink->double_cup ? 2 : 1;
    int water_used = drink->steam_only ? 60 : drink->volume * cups + 20;
    coffee_state.water_ml -= water_used;
    if(coffee_state.water_ml < 0) coffee_state.water_ml = 0;

    if(!drink->water_only && !drink->steam_only) {
        coffee_state.beans_g -= (6 + drink->strength * 2) * cups;
        if(coffee_state.beans_g < 0) coffee_state.beans_g = 0;
        coffee_state.grounds_pct += 4 * cups;
        if(coffee_state.grounds_pct > 100) coffee_state.grounds_pct = 100;
    }
    if(drink->milk_drink) {
        coffee_state.milk_ml -= drink->milk_ml * cups;
        if(coffee_state.milk_ml < 0) coffee_state.milk_ml = 0;
    }

    coffee_state.brew_count++;
    coffee_state.cups_since_descale++;
    coffee_state.rinse_pct -= 2;
    coffee_state.milk_clean_pct -= drink->milk_drink ? 3 : 1;
    coffee_state.scale_pct -= 1;
    coffee_state.filter_pct -= 1;
    if(coffee_state.rinse_pct < 0) coffee_state.rinse_pct = 0;
    if(coffee_state.milk_clean_pct < 0) coffee_state.milk_clean_pct = 0;
    if(coffee_state.scale_pct < 0) coffee_state.scale_pct = 0;
    if(coffee_state.filter_pct < 0) coffee_state.filter_pct = 0;

    coffee_profile_t * profile = coffee_profile();
    profile->today++;
    profile->week[6]++;
    drink->brews++;

    coffee_log(
        "brew done drink=%d elapsed=%u water=%d beans=%d milk=%d grounds=%d",
        brew_drink, (unsigned)lv_tick_elaps(brew_start), coffee_state.water_ml,
        coffee_state.beans_g, coffee_state.milk_ml, coffee_state.grounds_pct);

    char message[64];
    snprintf(message, sizeof(message), "%s%s", drink->name,
             COFFEE_TXT_TOAST_BREW_DONE);
    coffee_toast(message);

    lv_arc_set_value(brew_arc, 100);
    lv_label_set_text(brew_title, COFFEE_TXT_BREW_DONE);
    lv_obj_set_style_text_color(brew_title, lv_color_hex(COFFEE_GOLD_BRIGHT),
                                0);
    char buffer[24];
    format_mmss(buffer, sizeof(buffer), lv_tick_elaps(brew_start));
    lv_label_set_text(brew_elapsed, buffer);
    lv_label_set_text(brew_eta, COFFEE_TXT_BREW_DONE_SUB);
    lv_label_set_text(brew_pressure, "0.0");
    coffee_format_temp(buffer, sizeof(buffer), drink->cold ? 4 : drink->temp_c);
    lv_label_set_text(brew_temp, buffer);
    coffee_hide(brew_check, false);
    coffee_hide(brew_cancel, true);
    coffee_hide(brew_done, false);
    for(int i = 0; i < phase_count; i++) {
        lv_label_set_text(phase_status[i], COFFEE_TXT_STATUS_DONE);
        coffee_hide(phase_checks[i], false);
        lv_obj_set_style_bg_color(phase_dots[i], lv_color_hex(COFFEE_GREEN), 0);
    }

    coffee_home_refresh();
    coffee_favorites_refresh();
    coffee_maintenance_refresh();

    close_timer = lv_timer_create(close_timer_cb, 3500, NULL);
    lv_timer_set_repeat_count(close_timer, 1);
}

static void close_timer_cb(lv_timer_t * timer)
{
    (void)timer;
    close_timer = NULL;
    coffee_modal_close();
}

static void brew_tick(void)
{
    coffee_drink_t * drink = &coffee_drinks[brew_drink];
    uint32_t elapsed = lv_tick_elaps(brew_start);
    int pct = (int)(elapsed * 100u / brew_duration);
    if(pct > 100) pct = 100;

    lv_arc_set_value(brew_arc, pct);
    update_phases(pct);

    char buffer[32];
    format_mmss(buffer, sizeof(buffer), elapsed);
    lv_label_set_text(brew_elapsed, buffer);

    uint32_t remaining = elapsed >= brew_duration ? 0 : brew_duration - elapsed;
    char eta[48];
    char remain_text[16];
    format_mmss(remain_text, sizeof(remain_text), remaining);
    snprintf(eta, sizeof(eta), "%s %s", COFFEE_TXT_ETA, remain_text);
    lv_label_set_text(brew_eta, eta);

    int pressure_tenths = 0;
    if(!drink->water_only && !drink->steam_only && pct >= 30 && pct < 92) {
        int wobble = (int)((elapsed / 250u + 7u) % 10u) - 5;
        pressure_tenths = 90 + wobble / 2;
    }
    snprintf(buffer, sizeof(buffer), "%d.%d %s", pressure_tenths / 10,
             pressure_tenths % 10, COFFEE_TXT_BAR);
    lv_label_set_text(brew_pressure, buffer);

    int target = drink->cold ? 4 : drink->temp_c;
    int temperature = target;
    if(!drink->cold && pct < 10) {
        temperature = 22 + (target - 22) * pct / 10;
    }
    coffee_format_temp(buffer, sizeof(buffer), temperature);
    lv_label_set_text(brew_temp, buffer);

    int start = drink->water_only ? 15 : drink->steam_only ? 45 : 30;
    int finish = 90;
    int fill = 0;
    if(pct > start) {
        fill = (pct - start) * 88 / (finish - start);
        if(fill > 88) fill = 88;
    }
    lv_obj_set_pos(brew_liquid, 0, 88 - fill);
    lv_obj_set_height(brew_liquid, fill);

    for(int i = 0; i < 3; i++) {
        if(brew_wisps[i] == NULL) continue;
        int wave = (int)((elapsed / 160u + (uint32_t)i * 26u) % 76u);
        int offset = wave < 38 ? wave / 5 : (76 - wave) / 5;
        lv_obj_set_y(brew_wisps[i], 52 - offset);
        lv_obj_set_style_bg_opa(brew_wisps[i], (lv_opa_t)(26 + offset * 2), 0);
    }

    if(pct >= 100 && !brew_finished) {
        brew_finish();
    }
}

static void brew_timer_cb(lv_timer_t * timer)
{
    (void)timer;
    brew_tick();
}

void coffee_brew_abort(void)
{
    if(brew_timer != NULL) {
        lv_timer_delete(brew_timer);
        brew_timer = NULL;
    }
    if(close_timer != NULL) {
        lv_timer_delete(close_timer);
        close_timer = NULL;
    }
}

static void cancel_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_log("brew cancel drink=%d", brew_drink);
    coffee_modal_close();
    coffee_toast(COFFEE_TXT_CANCELED);
}

static void done_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_modal_close();
}

static void phase_name_setup(const coffee_drink_t * drink)
{
    if(drink->water_only) {
        phase_count = 3;
        phase_names[0] = COFFEE_TXT_PHASE_PREHEAT;
        phase_names[1] = COFFEE_TXT_PHASE_WATER;
        phase_names[2] = COFFEE_TXT_PHASE_DONE;
        int bounds[3] = {15, 90, 100};
        for(int i = 0; i < 3; i++) phase_bounds[i] = bounds[i];
    }
    else if(drink->steam_only) {
        phase_count = 4;
        phase_names[0] = COFFEE_TXT_PHASE_PREHEAT;
        phase_names[1] = COFFEE_TXT_PHASE_HEAT_MILK;
        phase_names[2] = COFFEE_TXT_PHASE_FROTH;
        phase_names[3] = COFFEE_TXT_PHASE_DONE;
        int bounds[4] = {12, 45, 90, 100};
        for(int i = 0; i < 4; i++) phase_bounds[i] = bounds[i];
    }
    else if(drink->milk_drink) {
        phase_count = 6;
        phase_names[0] = COFFEE_TXT_PHASE_PREHEAT;
        phase_names[1] = COFFEE_TXT_PHASE_GRIND;
        phase_names[2] = COFFEE_TXT_PHASE_PREINFUSE;
        phase_names[3] = COFFEE_TXT_PHASE_EXTRACT;
        phase_names[4] = COFFEE_TXT_PHASE_MILK;
        phase_names[5] = COFFEE_TXT_PHASE_DONE;
        int bounds[6] = {8, 20, 30, 70, 92, 100};
        for(int i = 0; i < 6; i++) phase_bounds[i] = bounds[i];
    }
    else {
        phase_count = 5;
        phase_names[0] = COFFEE_TXT_PHASE_PREHEAT;
        phase_names[1] = COFFEE_TXT_PHASE_GRIND;
        phase_names[2] = COFFEE_TXT_PHASE_PREINFUSE;
        phase_names[3] = COFFEE_TXT_PHASE_EXTRACT;
        phase_names[4] = COFFEE_TXT_PHASE_DONE;
        int bounds[5] = {8, 20, 30, 92, 100};
        for(int i = 0; i < 5; i++) phase_bounds[i] = bounds[i];
    }
}

static void build_cup(lv_obj_t * panel, const coffee_drink_t * drink)
{
    const int cup_x = 44;
    const int cup_y = 80;

    lv_obj_t * inner =
        coffee_card(panel, cup_x + 48, cup_y + 40, 94, 88, 8, 0xCDBFAC, 0);
    lv_obj_set_style_clip_corner(inner, true, 0);
    brew_liquid = coffee_card(inner, 0, 88, 94, 0, 0, liquid_color(drink), 0);
    brew_crema =
        coffee_card(brew_liquid, 0, 0, 94, 5, 0, crema_color(drink), 0);

    lv_obj_t * cup = lv_image_create(panel);
    lv_image_set_src(cup, coffee_brew_cup_asset());
    lv_obj_set_pos(cup, cup_x, cup_y);
    app_obj_set_scrollable(cup, false);
    app_obj_set_clickable(cup, false);

    for(int i = 0; i < 3; i++) brew_wisps[i] = NULL;

    brew_check = coffee_icon_obj(panel, COFFEE_ICON_CHECK, 117, 143, 44,
                                 COFFEE_GOLD_BRIGHT);
    coffee_hide(brew_check, true);
}

void coffee_start_brew(int drink)
{
    if(drink < 0 || drink >= COFFEE_DRINK_COUNT) return;
    coffee_drink_t * item = &coffee_drinks[drink];
    if(!check_resources(item)) return;
    coffee_home_refresh();

    brew_drink = drink;
    brew_finished = false;
    brew_start = lv_tick_get();
    brew_duration = 9000u + (uint32_t)item->volume * 15u +
                    (uint32_t)item->strength * 700u +
                    (uint32_t)item->milk_ml * 20u;
    if(item->double_cup) brew_duration += 3000u;
    if(item->cold) brew_duration += 5000u;
    if(item->water_only) {
        brew_duration = 5000u + (uint32_t)item->volume * 10u;
    }
    if(item->steam_only) {
        brew_duration = 8000u + (uint32_t)item->milk_ml * 20u;
    }
    if(brew_duration > 32000u) brew_duration = 32000u;

    coffee_log("brew start drink=%d volume=%d strength=%d temp=%d milk=%d "
               "foam=%d double=%d duration=%u",
               drink, item->volume, item->strength, item->temp_c, item->milk_ml,
               item->foam, item->double_cup ? 1 : 0, (unsigned)brew_duration);

    lv_obj_t * panel = coffee_modal_open(660, 450);
    if(panel == NULL) return;

    brew_arc = lv_arc_create(panel);
    lv_obj_set_pos(brew_arc, 24, 58);
    lv_obj_set_size(brew_arc, 230, 230);
    lv_arc_set_bg_angles(brew_arc, 135, 405);
    lv_arc_set_range(brew_arc, 0, 100);
    lv_arc_set_value(brew_arc, 0);
    lv_obj_set_style_arc_width(brew_arc, 8, LV_PART_MAIN);
    lv_obj_set_style_arc_color(brew_arc, lv_color_hex(COFFEE_LINE),
                               LV_PART_MAIN);
    lv_obj_set_style_arc_width(brew_arc, 8, LV_PART_INDICATOR);
    lv_obj_set_style_arc_color(brew_arc, lv_color_hex(COFFEE_GOLD),
                               LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(brew_arc, LV_OPA_TRANSP, LV_PART_KNOB);
    lv_obj_set_style_pad_all(brew_arc, 0, 0);
    app_obj_set_clickable(brew_arc, false);

    build_cup(panel, item);

    brew_elapsed = coffee_label_at(panel, "00:00", COFFEE_FT_32B, COFFEE_CREAM,
                                   0, 296, 280, 42);
    lv_obj_set_style_text_align(brew_elapsed, LV_TEXT_ALIGN_CENTER, 0);
    brew_eta =
        coffee_label_at(panel, "", COFFEE_FT_12, COFFEE_MUTED, 0, 340, 280, 18);
    lv_obj_set_style_text_align(brew_eta, LV_TEXT_ALIGN_CENTER, 0);

    brew_title = coffee_label_at(panel, COFFEE_TXT_BREWING, COFFEE_FT_12,
                                 COFFEE_GOLD, 300, 18, 200, 16);
    coffee_label_at(panel, item->name, COFFEE_FT_24B, COFFEE_CREAM, 300, 38,
                    300, 32);
    char params[80];
    if(item->steam_only) {
        snprintf(params, sizeof(params), "%s %d %s", COFFEE_TXT_MILK_AMOUNT,
                 item->milk_ml, COFFEE_TXT_ML);
    }
    else if(item->strength > 0) {
        snprintf(params, sizeof(params), "%d %s %s %d/5", item->volume,
                 COFFEE_TXT_ML, COFFEE_TXT_DIVIDER, item->strength);
        if(item->milk_drink && item->milk_ml > 0) {
            size_t used = strlen(params);
            snprintf(params + used, sizeof(params) - used, " %s %s %d %s",
                     COFFEE_TXT_DIVIDER, COFFEE_TXT_MILK_AMOUNT, item->milk_ml,
                     COFFEE_TXT_ML);
        }
    }
    else {
        snprintf(params, sizeof(params), "%d %s", item->volume, COFFEE_TXT_ML);
    }
    coffee_label_at(panel, params, COFFEE_FT_12, COFFEE_MUTED, 300, 78, 330,
                    16);

    phase_name_setup(item);
    for(int i = 0; i < phase_count; i++) {
        int y = 110 + i * 34;
        lv_obj_t * dot =
            coffee_card(panel, 300, y, 22, 22, 11, COFFEE_CARD_UP, 0);
        phase_dots[i] = dot;
        phase_checks[i] =
            coffee_icon_obj(dot, COFFEE_ICON_CHECK, 0, 0, 14, 0x16210F);
        lv_obj_center(phase_checks[i]);
        coffee_hide(phase_checks[i], true);
        phase_labels[i] = coffee_label_at(panel, phase_names[i], COFFEE_FT_13,
                                          COFFEE_DIM, 332, y + 2, 150, 18);
        phase_status[i] =
            coffee_label_at(panel, COFFEE_TXT_STATUS_WAIT, COFFEE_FT_12,
                            COFFEE_DIM, 512, y + 3, 88, 16);
        lv_obj_set_style_text_align(phase_status[i], LV_TEXT_ALIGN_RIGHT, 0);
    }

    lv_obj_t * pressure_card =
        coffee_card(panel, 300, 324, 150, 58, 14, COFFEE_CARD_UP, 0);
    coffee_label_at(pressure_card, COFFEE_TXT_PRESSURE, COFFEE_FT_12,
                    COFFEE_MUTED, 14, 8, 100, 16);
    brew_pressure = coffee_label_at(pressure_card, "0.0", COFFEE_FT_18B,
                                    COFFEE_CREAM, 14, 28, 100, 24);

    lv_obj_t * temp_card =
        coffee_card(panel, 462, 324, 156, 58, 14, COFFEE_CARD_UP, 0);
    coffee_label_at(temp_card, COFFEE_TXT_WATER_TEMP, COFFEE_FT_12,
                    COFFEE_MUTED, 14, 8, 100, 16);
    brew_temp = coffee_label_at(temp_card, "", COFFEE_FT_18B, COFFEE_CREAM, 14,
                                28, 120, 24);

    brew_cancel =
        coffee_button(panel, 300, 394, 140, 44, false, COFFEE_TXT_CANCEL_BREW,
                      COFFEE_FT_14B, "brew_cancel");
    lv_obj_add_event_cb(brew_cancel, cancel_event_cb, LV_EVENT_CLICKED, NULL);
    brew_done = coffee_button(panel, 462, 394, 156, 44, true, COFFEE_TXT_DONE,
                              COFFEE_FT_14B, "brew_done");
    coffee_hide(brew_done, true);
    lv_obj_add_event_cb(brew_done, done_event_cb, LV_EVENT_CLICKED, NULL);

    brew_timer = lv_timer_create(brew_timer_cb, 80, NULL);
    brew_tick();
}

#endif
