
#include "coffee_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include <stdio.h>

static lv_obj_t * page;
static lv_obj_t * value_grind;
static lv_obj_t * value_temp;
static lv_obj_t * value_hardness;
static lv_obj_t * value_auto;
static lv_obj_t * value_brightness;
static lv_obj_t * value_unit;
static lv_obj_t * toggle_preheat;
static lv_obj_t * toggle_sound;
static lv_obj_t * toggle_eco;
static lv_obj_t * summary_label;

static const char * const hardness_texts[4] = {
    COFFEE_TXT_HARDNESS_1, COFFEE_TXT_HARDNESS_2,
    COFFEE_TXT_HARDNESS_3, COFFEE_TXT_HARDNESS_4,
};
static const char * const auto_texts[4] = {
    COFFEE_TXT_AUTO_OFF_NEVER, COFFEE_TXT_MIN_15,
    COFFEE_TXT_MIN_30, COFFEE_TXT_MIN_60,
};
static const int auto_values[4] = { 0, 15, 30, 60 };

static void apply_preheat(bool on)
{
    coffee_state.preheat = on;
    for(int i = 0; i < COFFEE_DRINK_COUNT; i++) {
        coffee_drinks[i].preheat = on;
    }
}

static void grind_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int step = (int)(intptr_t)lv_event_get_user_data(event);
    coffee_state.grind += step;
    if(coffee_state.grind < 1) coffee_state.grind = 1;
    if(coffee_state.grind > 10) coffee_state.grind = 10;
    coffee_log("setting grind=%d", coffee_state.grind);
    coffee_settings_refresh();
}

static void temp_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int step = (int)(intptr_t)lv_event_get_user_data(event);
    coffee_state.temp_c += step;
    if(coffee_state.temp_c < 88) coffee_state.temp_c = 88;
    if(coffee_state.temp_c > 96) coffee_state.temp_c = 96;
    for(int i = 0; i < COFFEE_DRINK_COUNT; i++) {
        if(!coffee_drinks[i].cold) coffee_drinks[i].temp_c = coffee_state.temp_c;
    }
    coffee_log("setting temp=%d", coffee_state.temp_c);
    coffee_shell_refresh();
    coffee_home_refresh();
    coffee_settings_refresh();
}

static void hardness_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int step = (int)(intptr_t)lv_event_get_user_data(event);
    coffee_state.hardness += step;
    if(coffee_state.hardness < 1) coffee_state.hardness = 4;
    if(coffee_state.hardness > 4) coffee_state.hardness = 1;
    coffee_log("setting hardness=%d", coffee_state.hardness);
    coffee_settings_refresh();
}

static void auto_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int step = (int)(intptr_t)lv_event_get_user_data(event);
    int index = 0;
    for(int i = 0; i < 4; i++) {
        if(auto_values[i] == coffee_state.auto_off_min) index = i;
    }
    index = (index + step + 4) % 4;
    coffee_state.auto_off_min = auto_values[index];
    coffee_log("setting auto_off=%d", coffee_state.auto_off_min);
    coffee_settings_refresh();
}

static void brightness_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int step = (int)(intptr_t)lv_event_get_user_data(event);
    coffee_state.brightness += step * 10;
    if(coffee_state.brightness < 40) coffee_state.brightness = 40;
    if(coffee_state.brightness > 100) coffee_state.brightness = 100;
    coffee_log("setting brightness=%d", coffee_state.brightness);
    coffee_apply_brightness();
    coffee_settings_refresh();
}

static void preheat_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    apply_preheat(!coffee_state.preheat);
    coffee_log("setting preheat=%d", coffee_state.preheat ? 1 : 0);
    coffee_toggle_set(lv_event_get_target_obj(event), coffee_state.preheat);
    coffee_settings_refresh();
}

static void sound_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_state.sound = !coffee_state.sound;
    coffee_log("setting sound=%d", coffee_state.sound ? 1 : 0);
    coffee_toggle_set(lv_event_get_target_obj(event), coffee_state.sound);
    coffee_settings_refresh();
}

static void eco_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_state.eco = !coffee_state.eco;
    coffee_log("setting eco=%d", coffee_state.eco ? 1 : 0);
    coffee_toggle_set(lv_event_get_target_obj(event), coffee_state.eco);
    coffee_settings_refresh();
}

static void unit_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_state.use_fahrenheit = !coffee_state.use_fahrenheit;
    coffee_log("setting unit=%s",
               coffee_state.use_fahrenheit ? "fahrenheit" : "celsius");
    coffee_refresh_all();
}

static void reset_confirm_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_state.grind = 6;
    coffee_state.temp_c = 93;
    coffee_state.hardness = 2;
    coffee_state.auto_off_min = 30;
    coffee_state.brightness = 100;
    coffee_state.sound = true;
    coffee_state.eco = false;
    coffee_state.use_fahrenheit = false;
    apply_preheat(false);
    for(int i = 0; i < COFFEE_DRINK_COUNT; i++) {
        if(!coffee_drinks[i].cold) coffee_drinks[i].temp_c = 93;
        coffee_drinks[i].double_cup = false;
    }
    coffee_log("setting reset");
    coffee_modal_close();
    coffee_apply_brightness();
    coffee_refresh_all();
    coffee_toast(COFFEE_TXT_RESET_DONE);
}

static void reset_cancel_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_modal_close();
}

static void reset_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    lv_obj_t * panel = coffee_modal_open(420, 226);
    if(panel == NULL) return;
    coffee_label_at(panel, COFFEE_TXT_RESET_CONFIRM, COFFEE_FT_18B,
                    COFFEE_CREAM, 24, 28, 372, 28);
    lv_obj_t * sub = coffee_label_at(panel, COFFEE_TXT_RESET_CONFIRM_SUB,
                                     COFFEE_FT_13, COFFEE_MUTED,
                                     24, 68, 372, 40);
    lv_label_set_long_mode(sub, LV_LABEL_LONG_WRAP);
    lv_obj_t * cancel = coffee_button(panel, 64, 150, 124, 44, false,
                                      COFFEE_TXT_CANCEL, COFFEE_FT_14B,
                                      "reset_cancel");
    lv_obj_add_event_cb(cancel, reset_cancel_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t * confirm = coffee_button(panel, 232, 150, 124, 44, true,
                                       COFFEE_TXT_RESTORE, COFFEE_FT_14B,
                                       "reset_confirm");
    lv_obj_add_event_cb(confirm, reset_confirm_cb, LV_EVENT_CLICKED, NULL);
}

static void stepper(lv_obj_t * parent, int y,
                    const char * minus_name, const char * plus_name,
                    lv_event_cb_t callback, lv_obj_t ** value)
{
    lv_obj_t * minus = coffee_icon_button(parent, 166, y + 2, 32,
                                           COFFEE_ICON_MINUS,
                                           COFFEE_GOLD_BRIGHT, COFFEE_CARD_UP,
                                           minus_name);
    lv_obj_add_event_cb(minus, callback, LV_EVENT_CLICKED, coffee_int(-1));
    *value = coffee_label_at(parent, "", COFFEE_FT_18B, COFFEE_CREAM,
                             202, y + 2, 68, 28);
    lv_obj_set_style_text_align(*value, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_t * plus = coffee_icon_button(parent, 274, y + 2, 32,
                                          COFFEE_ICON_PLUS,
                                          COFFEE_GOLD_BRIGHT, COFFEE_CARD_UP,
                                          plus_name);
    lv_obj_add_event_cb(plus, callback, LV_EVENT_CLICKED, coffee_int(1));
}

static void build_left_card(lv_obj_t * parent)
{
    lv_obj_t * card = coffee_card(parent, 20, 86, 324, 400, 20,
                                  COFFEE_CARD, COFFEE_LINE);
    coffee_label_at(card, COFFEE_TXT_SET_BREW, COFFEE_FT_16, COFFEE_CREAM,
                    18, 14, 200, 20);
    lv_obj_t * line = coffee_box(card, 18, 44, 288, 1);
    lv_obj_set_style_bg_color(line, lv_color_hex(COFFEE_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);

    coffee_label_at(card, COFFEE_TXT_GRIND, COFFEE_FT_14, COFFEE_CREAM,
                    18, 63, 140, 20);
    stepper(card, 56, "setting_grind_minus", "setting_grind_plus",
            grind_event_cb, &value_grind);

    coffee_label_at(card, COFFEE_TXT_COFFEE_TEMP, COFFEE_FT_14,
                    COFFEE_CREAM, 18, 127, 140, 20);
    stepper(card, 120, "setting_temp_minus", "setting_temp_plus",
            temp_event_cb, &value_temp);

    coffee_label_at(card, COFFEE_TXT_HARDNESS, COFFEE_FT_14, COFFEE_CREAM,
                    18, 191, 140, 20);
    stepper(card, 184, "setting_hardness_minus",
            "setting_hardness_plus", hardness_event_cb, &value_hardness);

    coffee_label_at(card, COFFEE_TXT_PREHEAT_CUP, COFFEE_FT_14,
                    COFFEE_CREAM, 18, 255, 160, 20);
    toggle_preheat = coffee_toggle(card, 254, 250, 52, 28,
                                   coffee_state.preheat, "setting_preheat");
    lv_obj_add_event_cb(toggle_preheat, preheat_event_cb, LV_EVENT_CLICKED,
                        NULL);

    lv_obj_t * divider = coffee_box(card, 18, 300, 288, 1);
    lv_obj_set_style_bg_color(divider, lv_color_hex(COFFEE_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);
    summary_label = coffee_label_at(card, "", COFFEE_FT_13, COFFEE_MUTED,
                                    18, 318, 288, 20);
}

static void build_right_card(lv_obj_t * parent)
{
    lv_obj_t * card = coffee_card(parent, 360, 86, 324, 400, 20,
                                  COFFEE_CARD, COFFEE_LINE);
    coffee_label_at(card, COFFEE_TXT_SET_SYSTEM, COFFEE_FT_16,
                    COFFEE_CREAM, 18, 14, 200, 20);
    lv_obj_t * line = coffee_box(card, 18, 44, 288, 1);
    lv_obj_set_style_bg_color(line, lv_color_hex(COFFEE_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);

    coffee_label_at(card, COFFEE_TXT_AUTO_OFF, COFFEE_FT_14, COFFEE_CREAM,
                    18, 63, 140, 20);
    stepper(card, 56, "setting_auto_minus", "setting_auto_plus",
            auto_event_cb, &value_auto);

    coffee_label_at(card, COFFEE_TXT_BRIGHTNESS, COFFEE_FT_14,
                    COFFEE_CREAM, 18, 127, 140, 20);
    stepper(card, 120, "setting_brightness_minus",
            "setting_brightness_plus", brightness_event_cb, &value_brightness);

    coffee_label_at(card, COFFEE_TXT_SOUND, COFFEE_FT_14, COFFEE_CREAM,
                    18, 191, 140, 20);
    toggle_sound = coffee_toggle(card, 254, 186, 52, 28, coffee_state.sound,
                                 "setting_sound");
    lv_obj_add_event_cb(toggle_sound, sound_event_cb, LV_EVENT_CLICKED, NULL);

    coffee_label_at(card, COFFEE_TXT_ECO, COFFEE_FT_14, COFFEE_CREAM,
                    18, 255, 140, 20);
    toggle_eco = coffee_toggle(card, 254, 250, 52, 28, coffee_state.eco,
                               "setting_eco");
    lv_obj_add_event_cb(toggle_eco, eco_event_cb, LV_EVENT_CLICKED, NULL);

    coffee_label_at(card, COFFEE_TXT_UNIT, COFFEE_FT_14, COFFEE_CREAM,
                    18, 319, 140, 20);
    lv_obj_t * unit = coffee_button(card, 242, 314, 64, 32, false,
                                    COFFEE_TXT_DEGREE_C, COFFEE_FT_14B,
                                    "setting_unit");
    value_unit = lv_obj_get_child(unit, 0);
    lv_obj_add_event_cb(unit, unit_event_cb, LV_EVENT_CLICKED, NULL);
}

void coffee_settings_refresh(void)
{
    if(page == NULL) return;
    char buffer[32];

    snprintf(buffer, sizeof(buffer), "%d / 10", coffee_state.grind);
    lv_label_set_text(value_grind, buffer);
    coffee_format_temp(buffer, sizeof(buffer), coffee_state.temp_c);
    lv_label_set_text(value_temp, buffer);
    lv_label_set_text(value_hardness,
                      hardness_texts[coffee_state.hardness - 1]);

    int auto_index = 0;
    for(int i = 0; i < 4; i++) {
        if(auto_values[i] == coffee_state.auto_off_min) auto_index = i;
    }
    lv_label_set_text(value_auto, auto_texts[auto_index]);

    snprintf(buffer, sizeof(buffer), "%d%%", coffee_state.brightness);
    lv_label_set_text(value_brightness, buffer);
    lv_label_set_text(value_unit, coffee_state.use_fahrenheit
                                      ? COFFEE_TXT_DEGREE_F
                                      : COFFEE_TXT_DEGREE_C);

    coffee_toggle_set(toggle_preheat, coffee_state.preheat);
    coffee_toggle_set(toggle_sound, coffee_state.sound);
    coffee_toggle_set(toggle_eco, coffee_state.eco);

    coffee_profile_t * profile = coffee_profile();
    int week_total = 0;
    for(int i = 0; i < 7; i++) week_total += profile->week[i];
    char summary[64];
    snprintf(summary, sizeof(summary), "%s %d %s %s %s %d %s",
             COFFEE_TXT_TODAY, profile->today, COFFEE_TXT_CUP_UNIT,
             COFFEE_TXT_DIVIDER, COFFEE_TXT_WEEK, week_total,
             COFFEE_TXT_CUP_UNIT);
    lv_label_set_text(summary_label, summary);
}

lv_obj_t * coffee_settings_create(lv_obj_t * parent)
{
    page = coffee_box(parent, 0, 0, COFFEE_PAGE_W, COFFEE_PAGE_H);
    coffee_label_at(page, COFFEE_TXT_SET_TITLE, COFFEE_FT_24B,
                    COFFEE_CREAM, 20, 12, 300, 32);
    coffee_label_at(page, COFFEE_TXT_SET_SUB, COFFEE_FT_13, COFFEE_MUTED,
                    20, 48, 420, 18);

    build_left_card(page);
    build_right_card(page);

    coffee_label_at(page, COFFEE_TXT_FIRMWARE, COFFEE_FT_12, COFFEE_MUTED,
                    20, 500, 260, 16);
    coffee_label_at(page, COFFEE_TXT_FIRMWARE_SUB, COFFEE_FT_12,
                    COFFEE_DIM, 20, 518, 300, 16);
    lv_obj_t * reset = coffee_button(page, 500, 494, 184, 40, false,
                                     COFFEE_TXT_RESET, COFFEE_FT_13,
                                     "setting_reset");
    lv_obj_add_event_cb(reset, reset_event_cb, LV_EVENT_CLICKED, NULL);

    coffee_settings_refresh();
    return page;
}

#endif
