
#include "coffee_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include <stdio.h>

static int drink_id;
static int backup_temp;
static coffee_drink_t backup;
static lv_obj_t * strength_buttons[5];
static lv_obj_t * strength_value;
static lv_obj_t * volume_value;
static lv_obj_t * temp_pills[3];
static lv_obj_t * temp_labels[3];
static lv_obj_t * milk_value;
static lv_obj_t * foam_pills[4];
static lv_obj_t * foam_labels[4];
static lv_obj_t * favorite_icon;
static lv_obj_t * favorite_label;
static lv_obj_t * double_track;
static lv_obj_t * preheat_track;

static const char * const strength_ids[5] = {
    "custom_strength_1", "custom_strength_2", "custom_strength_3",
    "custom_strength_4", "custom_strength_5",
};
static const char * const temp_ids[3] = {
    "custom_temp_88", "custom_temp_93", "custom_temp_96",
};
static const char * const foam_ids[4] = {
    "custom_foam_none", "custom_foam_light",
    "custom_foam_creamy", "custom_foam_rich",
};

static void style_pill(lv_obj_t * pill, lv_obj_t * label, bool on)
{
    lv_obj_set_style_bg_color(pill, lv_color_hex(on ? COFFEE_GOLD
                                                    : COFFEE_CARD_UP), 0);
    lv_obj_set_style_border_width(pill, 1, 0);
    lv_obj_set_style_border_color(pill, lv_color_hex(on ? COFFEE_GOLD
                                                        : COFFEE_LINE), 0);
    lv_obj_set_style_text_color(label,
                                lv_color_hex(on ? 0x191207 : COFFEE_MUTED), 0);
}

static void custom_refresh(void)
{
    coffee_drink_t * drink = &coffee_drinks[drink_id];

    for(int i = 0; i < 5; i++) {
        lv_obj_t * icon = lv_obj_get_child(strength_buttons[i], 0);
        if(icon != NULL) {
            lv_obj_set_style_image_recolor(icon,
                                           lv_color_hex(i < drink->strength
                                                            ? COFFEE_GOLD_BRIGHT
                                                            : COFFEE_LINE), 0);
        }
    }
    if(strength_value != NULL) {
        char buffer[16];
        if(drink->strength > 0) {
            snprintf(buffer, sizeof(buffer), "%d/5", drink->strength);
        }
        else {
            snprintf(buffer, sizeof(buffer), "--");
        }
        lv_label_set_text(strength_value, buffer);
    }

    if(volume_value != NULL) {
        char buffer[24];
        snprintf(buffer, sizeof(buffer), "%d %s", drink->volume, COFFEE_TXT_ML);
        lv_label_set_text(volume_value, buffer);
    }

    static const int temps[3] = { 88, 93, 96 };
    for(int i = 0; i < 3; i++) {
        if(temp_pills[i] == NULL) continue;
        char temp_text[16];
        coffee_format_temp(temp_text, sizeof(temp_text), temps[i]);
        lv_label_set_text(temp_labels[i], temp_text);
        style_pill(temp_pills[i], temp_labels[i],
                   drink->temp_c == temps[i]);
    }

    if(milk_value != NULL) {
        char buffer[24];
        snprintf(buffer, sizeof(buffer), "%d %s", drink->milk_ml, COFFEE_TXT_ML);
        lv_label_set_text(milk_value, buffer);
    }

    for(int i = 0; i < 4; i++) {
        if(foam_pills[i] == NULL) continue;
        style_pill(foam_pills[i], foam_labels[i], drink->foam == i);
    }

    if(double_track != NULL) coffee_toggle_set(double_track, drink->double_cup);
    if(preheat_track != NULL) coffee_toggle_set(preheat_track, drink->preheat);

    bool favorite = coffee_is_favorite(drink_id);
    if(favorite_icon != NULL) {
        lv_image_set_src(favorite_icon,
                         coffee_icon(favorite ? COFFEE_ICON_HEART_FILLED
                                              : COFFEE_ICON_HEART));
        lv_obj_set_style_image_recolor(favorite_icon,
                                       lv_color_hex(favorite
                                                        ? COFFEE_GOLD_BRIGHT
                                                        : COFFEE_MUTED), 0);
    }
    if(favorite_label != NULL) {
        lv_label_set_text(favorite_label, favorite ? COFFEE_TXT_FAVORITED
                                                   : COFFEE_TXT_SAVE_TO_FAVORITE);
    }
}

static void strength_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int strength = (int)(intptr_t)lv_event_get_user_data(event) + 1;
    coffee_drinks[drink_id].strength = strength;
    coffee_log("custom strength=%d drink=%d", strength, drink_id);
    custom_refresh();
}

static void volume_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_drink_t * drink = &coffee_drinks[drink_id];
    int step = (int)(intptr_t)lv_event_get_user_data(event);
    if(drink->steam_only) {
        drink->milk_ml += step * 10;
        if(drink->milk_ml < 100) drink->milk_ml = 100;
        if(drink->milk_ml > drink->milk_max) drink->milk_ml = drink->milk_max;
        drink->volume = drink->milk_ml;
    }
    else {
        drink->volume += step * drink->volume_step;
        if(drink->volume < drink->volume_min) drink->volume = drink->volume_min;
        if(drink->volume > drink->volume_max) drink->volume = drink->volume_max;
    }
    coffee_log("custom volume=%d drink=%d", drink->volume, drink_id);
    custom_refresh();
}

static void temp_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int temp = (int)(intptr_t)lv_event_get_user_data(event);
    coffee_drinks[drink_id].temp_c = temp;
    coffee_state.temp_c = temp;
    coffee_log("custom temp=%d drink=%d", temp, drink_id);
    coffee_shell_refresh();
    custom_refresh();
}

static void milk_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_drink_t * drink = &coffee_drinks[drink_id];
    int step = (int)(intptr_t)lv_event_get_user_data(event);
    drink->milk_ml += step * 10;
    if(drink->milk_ml < 0) drink->milk_ml = 0;
    if(drink->milk_ml > drink->milk_max) drink->milk_ml = drink->milk_max;
    if(drink->steam_only) drink->volume = drink->milk_ml;
    coffee_log("custom milk=%d drink=%d", drink->milk_ml, drink_id);
    custom_refresh();
}

static void foam_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int foam = (int)(intptr_t)lv_event_get_user_data(event);
    coffee_drinks[drink_id].foam = foam;
    coffee_log("custom foam=%d drink=%d", foam, drink_id);
    custom_refresh();
}

static void double_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_drink_t * drink = &coffee_drinks[drink_id];
    drink->double_cup = !drink->double_cup;
    coffee_log("custom double=%d drink=%d", drink->double_cup ? 1 : 0, drink_id);
    custom_refresh();
}

static void preheat_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_drink_t * drink = &coffee_drinks[drink_id];
    drink->preheat = !drink->preheat;
    coffee_log("custom preheat=%d drink=%d", drink->preheat ? 1 : 0, drink_id);
    custom_refresh();
}

static void favorite_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_toggle_favorite(drink_id);
    custom_refresh();
}

static void cancel_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_drinks[drink_id] = backup;
    coffee_state.temp_c = backup_temp;
    coffee_log("custom cancel drink=%d", drink_id);
    coffee_modal_close();
    coffee_shell_refresh();
    coffee_home_refresh();
    coffee_toast(COFFEE_TXT_CANCELED);
}

static void save_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_log("custom save drink=%d volume=%d strength=%d temp=%d milk=%d foam=%d",
               drink_id, coffee_drinks[drink_id].volume,
               coffee_drinks[drink_id].strength,
               coffee_drinks[drink_id].temp_c,
               coffee_drinks[drink_id].milk_ml,
               coffee_drinks[drink_id].foam);
    coffee_modal_close();
    coffee_toast(COFFEE_TXT_SAVED);
    coffee_home_refresh();
}

static void start_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int drink = drink_id;
    coffee_modal_close();
    coffee_start_brew(drink);
}

static lv_obj_t * add_divider(lv_obj_t * panel, int x, int y, int w)
{
    lv_obj_t * line = coffee_box(panel, x, y, w, 1);
    lv_obj_set_style_bg_color(line, lv_color_hex(COFFEE_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);
    return line;
}

void coffee_open_custom(int drink)
{
    if(drink < 0 || drink >= COFFEE_DRINK_COUNT) return;
    drink_id = drink;
    backup = coffee_drinks[drink];
    backup_temp = coffee_state.temp_c;
    coffee_drink_t * drink_ptr = &coffee_drinks[drink];
    coffee_log("custom open drink=%d", drink);

    for(int i = 0; i < 5; i++) strength_buttons[i] = NULL;
    strength_value = NULL;
    volume_value = NULL;
    for(int i = 0; i < 3; i++) {
        temp_pills[i] = NULL;
        temp_labels[i] = NULL;
    }
    milk_value = NULL;
    for(int i = 0; i < 4; i++) {
        foam_pills[i] = NULL;
        foam_labels[i] = NULL;
    }
    favorite_icon = NULL;
    favorite_label = NULL;
    double_track = NULL;
    preheat_track = NULL;

    lv_obj_t * panel = coffee_modal_open(640, 480);
    if(panel == NULL) return;

    coffee_label_at(panel, COFFEE_TXT_CUSTOM_TITLE, COFFEE_FT_18B,
                    COFFEE_CREAM, 24, 16, 300, 24);
    coffee_label_at(panel, COFFEE_TXT_CUSTOM_SUB, COFFEE_FT_12,
                    COFFEE_MUTED, 24, 42, 360, 16);

    lv_obj_t * close = coffee_icon_button(panel, 586, 16, 34,
                                           COFFEE_ICON_CLOSE, COFFEE_MUTED,
                                           COFFEE_CARD_UP, "custom_close");
    lv_obj_add_event_cb(close, cancel_event_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * art_glow = coffee_box(panel, 24, 74, 176, 176);
    lv_obj_set_style_radius(art_glow, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(art_glow, lv_color_hex(COFFEE_GOLD), 0);
    lv_obj_set_style_bg_opa(art_glow, 10, 0);
    coffee_art_obj(panel, drink_ptr->art, 24, 74, 176);

    lv_obj_t * name = coffee_label_at(panel, drink_ptr->name, COFFEE_FT_18B,
                                      COFFEE_CREAM, 24, 260, 176, 24);
    lv_obj_set_style_text_align(name, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_t * italian = coffee_label_at(panel, drink_ptr->italian,
                                         COFFEE_FT_12, COFFEE_GOLD,
                                         24, 286, 176, 16);
    lv_obj_set_style_text_align(italian, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t * fav = coffee_card(panel, 24, 316, 176, 42, 21,
                                 COFFEE_CARD_UP, COFFEE_GOLD_DIM);
    coffee_clickable(fav, "custom_favorite");
    lv_obj_add_event_cb(fav, favorite_event_cb, LV_EVENT_CLICKED, NULL);
    favorite_icon = coffee_icon_obj(fav, COFFEE_ICON_HEART, 14, 11, 20,
                                    COFFEE_MUTED);
    favorite_label = coffee_label_at(fav, COFFEE_TXT_SAVE_TO_FAVORITE,
                                     COFFEE_FT_13, COFFEE_CREAM,
                                     42, 11, 124, 20);
    lv_obj_set_style_text_align(favorite_label, LV_TEXT_ALIGN_CENTER, 0);

    int x = 228;
    int width = 388;
    int y = 76;

    if(drink_ptr->strength > 0) {
        coffee_label_at(panel, COFFEE_TXT_STRENGTH, COFFEE_FT_13,
                        COFFEE_MUTED, x, y + 12, 60, 18);
        for(int i = 0; i < 5; i++) {
            lv_obj_t * button = coffee_icon_button(panel, x + 70 + i * 32,
                                                    y + 4, 30,
                                                    COFFEE_ICON_BEAN,
                                                    COFFEE_LINE,
                                                    COFFEE_CARD,
                                                    strength_ids[i]);
            lv_obj_add_event_cb(button, strength_event_cb, LV_EVENT_CLICKED,
                                coffee_int(i));
            strength_buttons[i] = button;
        }
        strength_value = coffee_label_at(panel, "", COFFEE_FT_13,
                                          COFFEE_MUTED, x + 290, y + 12,
                                          50, 18);
        lv_obj_set_style_text_align(strength_value, LV_TEXT_ALIGN_RIGHT, 0);
    }
    y += 46;
    add_divider(panel, x, y - 8, width);

    if(!drink_ptr->steam_only) {
        coffee_label_at(panel, COFFEE_TXT_VOLUME, COFFEE_FT_13,
                        COFFEE_MUTED, x, y + 18, 60, 18);
        lv_obj_t * minus = coffee_icon_button(panel, x + 70, y + 4, 38,
                                               COFFEE_ICON_MINUS,
                                               COFFEE_GOLD_BRIGHT,
                                               COFFEE_CARD_UP,
                                               "custom_volume_minus");
        lv_obj_add_event_cb(minus, volume_event_cb, LV_EVENT_CLICKED,
                            coffee_int(-1));
        volume_value = coffee_label_at(panel, "", COFFEE_FT_32B,
                                        COFFEE_CREAM, x + 120, y, 130, 42);
        lv_obj_set_style_text_align(volume_value, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_t * plus = coffee_icon_button(panel, x + 258, y + 4, 38,
                                              COFFEE_ICON_PLUS,
                                              COFFEE_GOLD_BRIGHT,
                                              COFFEE_CARD_UP,
                                              "custom_volume_plus");
        lv_obj_add_event_cb(plus, volume_event_cb, LV_EVENT_CLICKED,
                            coffee_int(1));
    }
    else {
        coffee_label_at(panel, COFFEE_TXT_MILK_AMOUNT, COFFEE_FT_13,
                        COFFEE_MUTED, x, y + 18, 60, 18);
        lv_obj_t * minus = coffee_icon_button(panel, x + 70, y + 4, 38,
                                               COFFEE_ICON_MINUS,
                                               COFFEE_GOLD_BRIGHT,
                                               COFFEE_CARD_UP,
                                               "custom_volume_minus");
        lv_obj_add_event_cb(minus, volume_event_cb, LV_EVENT_CLICKED,
                            coffee_int(-1));
        volume_value = coffee_label_at(panel, "", COFFEE_FT_32B,
                                        COFFEE_CREAM, x + 120, y, 130, 42);
        lv_obj_set_style_text_align(volume_value, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_t * plus = coffee_icon_button(panel, x + 258, y + 4, 38,
                                              COFFEE_ICON_PLUS,
                                              COFFEE_GOLD_BRIGHT,
                                              COFFEE_CARD_UP,
                                              "custom_volume_plus");
        lv_obj_add_event_cb(plus, volume_event_cb, LV_EVENT_CLICKED,
                            coffee_int(1));
    }
    y += 60;
    add_divider(panel, x, y - 8, width);

    coffee_label_at(panel, COFFEE_TXT_TEMPERATURE, COFFEE_FT_13,
                    COFFEE_MUTED, x, y + 12, 60, 18);
    if(drink_ptr->cold) {
        char cold_text[32];
        char cold_temp[16];
        coffee_format_temp(cold_temp, sizeof(cold_temp), 4);
        snprintf(cold_text, sizeof(cold_text), "%s %s",
                 COFFEE_TXT_COLD_EXTRACT, cold_temp);
        lv_obj_t * cold = coffee_pill(panel, x + 70, y, 180, 36,
                                      COFFEE_CARD_UP, cold_text,
                                      COFFEE_FT_13, COFFEE_BLUE, 18);
        (void)cold;
    }
    else {
        static const int temps[3] = { 88, 93, 96 };
        for(int i = 0; i < 3; i++) {
            char text[8];
            snprintf(text, sizeof(text), "%d", temps[i]);
            lv_obj_t * pill = coffee_card(panel, x + 70 + i * 74, y,
                                          64, 36, 18, COFFEE_CARD_UP,
                                          COFFEE_LINE);
            coffee_clickable(pill, temp_ids[i]);
            lv_obj_add_event_cb(pill, temp_event_cb, LV_EVENT_CLICKED,
                                coffee_int(temps[i]));
            lv_obj_t * label = coffee_label(pill, text, COFFEE_FT_14,
                                            COFFEE_MUTED);
            lv_obj_center(label);
            temp_pills[i] = pill;
            temp_labels[i] = label;
        }
    }
    y += 52;
    add_divider(panel, x, y - 8, width);

    if(drink_ptr->milk_drink && !drink_ptr->steam_only) {
        coffee_label_at(panel, COFFEE_TXT_MILK_AMOUNT, COFFEE_FT_13,
                        COFFEE_MUTED, x, y + 18, 60, 18);
        lv_obj_t * minus = coffee_icon_button(panel, x + 70, y + 4, 38,
                                               COFFEE_ICON_MINUS,
                                               COFFEE_GOLD_BRIGHT,
                                               COFFEE_CARD_UP,
                                               "custom_milk_minus");
        lv_obj_add_event_cb(minus, milk_event_cb, LV_EVENT_CLICKED,
                            coffee_int(-1));
        milk_value = coffee_label_at(panel, "", COFFEE_FT_32B,
                                      COFFEE_CREAM, x + 120, y, 130, 42);
        lv_obj_set_style_text_align(milk_value, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_t * plus = coffee_icon_button(panel, x + 258, y + 4, 38,
                                              COFFEE_ICON_PLUS,
                                              COFFEE_GOLD_BRIGHT,
                                              COFFEE_CARD_UP,
                                              "custom_milk_plus");
        lv_obj_add_event_cb(plus, milk_event_cb, LV_EVENT_CLICKED,
                            coffee_int(1));
        y += 60;

        coffee_label_at(panel, COFFEE_TXT_FOAM, COFFEE_FT_13, COFFEE_MUTED,
                        x, y + 10, 60, 18);
        static const char * const foam_texts[4] = {
            COFFEE_TXT_FOAM_NONE, COFFEE_TXT_FOAM_LIGHT,
            COFFEE_TXT_FOAM_CREAMY, COFFEE_TXT_FOAM_RICH,
        };
        for(int i = 0; i < 4; i++) {
            lv_obj_t * pill = coffee_card(panel, x + 70 + i * 66, y,
                                          56, 34, 17, COFFEE_CARD_UP,
                                          COFFEE_LINE);
            coffee_clickable(pill, foam_ids[i]);
            lv_obj_add_event_cb(pill, foam_event_cb, LV_EVENT_CLICKED,
                                coffee_int(i));
            lv_obj_t * label = coffee_label(pill, foam_texts[i],
                                            COFFEE_FT_12, COFFEE_MUTED);
            lv_obj_center(label);
            foam_pills[i] = pill;
            foam_labels[i] = label;
        }
        y += 48;
    }

    int toggle_y = y + 4;
    if(!drink_ptr->water_only && !drink_ptr->steam_only) {
        coffee_label_at(panel, COFFEE_TXT_DOUBLE_CUP, COFFEE_FT_13,
                        COFFEE_MUTED, x, toggle_y + 4, 56, 20);
        double_track = coffee_toggle(panel, x + 62, toggle_y, 52, 28,
                                     drink_ptr->double_cup,
                                     "custom_double");
        lv_obj_add_event_cb(double_track, double_event_cb, LV_EVENT_CLICKED,
                            NULL);
    }
    int preheat_x = x + 160;
    coffee_label_at(panel, COFFEE_TXT_PREHEAT_CUP, COFFEE_FT_13,
                    COFFEE_MUTED, preheat_x, toggle_y + 4, 70, 20);
    preheat_track = coffee_toggle(panel, preheat_x + 76, toggle_y, 52, 28,
                                  drink_ptr->preheat, "custom_preheat");
    lv_obj_add_event_cb(preheat_track, preheat_event_cb, LV_EVENT_CLICKED,
                        NULL);

    lv_obj_t * cancel = coffee_button(panel, x, 406, 96, 44, false,
                                      COFFEE_TXT_CANCEL, COFFEE_FT_14B,
                                      "custom_cancel");
    lv_obj_add_event_cb(cancel, cancel_event_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t * save = coffee_button(panel, x + 108, 406, 124, 44, false,
                                    COFFEE_TXT_SAVE_RECIPE, COFFEE_FT_14B,
                                    "custom_save");
    lv_obj_add_event_cb(save, save_event_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t * start = coffee_button(panel, x + 244, 406, 144, 44, true,
                                     COFFEE_TXT_BREW, COFFEE_FT_14B,
                                     "custom_brew");
    lv_obj_add_event_cb(start, start_event_cb, LV_EVENT_CLICKED, NULL);

    custom_refresh();
}

#endif
