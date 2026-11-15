
#include "coffee_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include <stdio.h>

#define CARD_W 116
#define CARD_H 146
#define CARD_GAP 8

static lv_obj_t * page;
static lv_obj_t * greeting;
static lv_obj_t * carousel;
static lv_obj_t * cards[COFFEE_DRINK_COUNT];
static lv_obj_t * card_names[COFFEE_DRINK_COUNT];
static lv_obj_t * hero_art;
static lv_obj_t * hero_name;
static lv_obj_t * hero_italian;
static lv_obj_t * hero_desc;
static lv_obj_t * hero_strength_beans[5];
static lv_obj_t * hero_strength_value;
static lv_obj_t * hero_volume;
static lv_obj_t * hero_temp;
static lv_obj_t * hero_favorite;
static lv_obj_t * hero_brew_label;
static lv_obj_t * meter_fill[4];
static lv_obj_t * meter_value[4];
static lv_obj_t * today_label;
static lv_obj_t * week_bars[7];

static const coffee_icon_id_t meter_icons[4] = {
    COFFEE_ICON_WATER, COFFEE_ICON_BEAN, COFFEE_ICON_MILK,
    COFFEE_ICON_GROUNDS,
};

static const char * const meter_names[4] = {
    COFFEE_TXT_WATER, COFFEE_TXT_BEANS, COFFEE_TXT_MILK, COFFEE_TXT_GROUNDS,
};

static const char * const card_ids[COFFEE_DRINK_COUNT] = {
    "drink_card_0", "drink_card_1", "drink_card_2", "drink_card_3",
    "drink_card_4", "drink_card_5", "drink_card_6", "drink_card_7",
    "drink_card_8", "drink_card_9", "drink_card_10", "drink_card_11",
};

static void card_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_select_drink((int)(intptr_t)lv_event_get_user_data(event));
}

static void favorite_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_toggle_favorite(coffee_state.selected_drink);
}

static void custom_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_open_custom(coffee_state.selected_drink);
}

static void brew_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_start_brew(coffee_state.selected_drink);
}

static void arrow_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int step = (int)(intptr_t)lv_event_get_user_data(event);
    int drink = coffee_state.selected_drink + step;
    if(drink < 0) drink = COFFEE_DRINK_COUNT - 1;
    if(drink >= COFFEE_DRINK_COUNT) drink = 0;
    coffee_select_drink(drink);
}

static void build_carousel(lv_obj_t * parent)
{
    carousel = coffee_box(parent, 20, 72, 664, 154);
    lv_obj_set_scroll_dir(carousel, LV_DIR_HOR);
    lv_obj_set_scrollbar_mode(carousel, LV_SCROLLBAR_MODE_OFF);
    lv_obj_set_scroll_snap_x(carousel, LV_SCROLL_SNAP_NONE);
    lv_obj_set_style_pad_all(carousel, 0, 0);

    for(int i = 0; i < COFFEE_DRINK_COUNT; i++) {
        lv_obj_t * card = coffee_card(carousel, i * (CARD_W + CARD_GAP), 4,
                                      CARD_W, CARD_H, 18, COFFEE_CARD,
                                      COFFEE_LINE);
        coffee_clickable(card, card_ids[i]);
        lv_obj_add_event_cb(card, card_event_cb, LV_EVENT_CLICKED,
                            coffee_int(i));
        lv_obj_t * art = coffee_art_obj(card, coffee_drinks[i].art,
                                        10, 10, 96);
        (void)art;
        lv_obj_t * name = coffee_label_at(card, coffee_drinks[i].name,
                                         COFFEE_FT_14B, COFFEE_CREAM,
                                         4, 108, CARD_W - 8, 20);
        lv_obj_set_style_text_align(name, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_t * it = coffee_label_at(card, coffee_drinks[i].italian,
                                        COFFEE_FT_12, COFFEE_GOLD_DIM,
                                        4, 128, CARD_W - 8, 16);
        lv_obj_set_style_text_align(it, LV_TEXT_ALIGN_CENTER, 0);
        cards[i] = card;
        card_names[i] = name;
    }
}

static void build_hero(lv_obj_t * parent)
{
    lv_obj_t * hero = coffee_card(parent, 20, 236, 444, 284, 20,
                                  COFFEE_CARD, COFFEE_LINE);
    lv_obj_set_style_shadow_color(hero, lv_color_hex(0x000000), 0);
    lv_obj_set_style_shadow_width(hero, 24, 0);
    lv_obj_set_style_shadow_opa(hero, 80, 0);
    lv_obj_set_style_shadow_ofs_y(hero, 10, 0);

    lv_obj_t * glow = coffee_box(hero, 0, 30, 200, 200);
    lv_obj_set_style_radius(glow, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(glow, lv_color_hex(COFFEE_GOLD), 0);
    lv_obj_set_style_bg_opa(glow, 12, 0);

    hero_art = coffee_art_obj(hero, coffee_drinks[coffee_state.selected_drink].art,
                              10, 54, 176);

    hero_favorite = coffee_icon_button(hero, 398, 12, 34,
                                       COFFEE_ICON_HEART, COFFEE_MUTED,
                                       COFFEE_CARD_UP, "favorite_toggle");
    lv_obj_add_event_cb(hero_favorite, favorite_event_cb, LV_EVENT_CLICKED,
                        NULL);

    hero_name = coffee_label_at(hero, "", COFFEE_FT_24B, COFFEE_CREAM,
                                196, 12, 200, 32);
    hero_italian = coffee_label_at(hero, "", COFFEE_FT_12, COFFEE_GOLD,
                                   198, 48, 200, 18);
    hero_desc = coffee_label_at(hero, "", COFFEE_FT_13, COFFEE_MUTED,
                                198, 74, 226, 54);
    lv_label_set_long_mode(hero_desc, LV_LABEL_LONG_WRAP);

    coffee_label_at(hero, COFFEE_TXT_STRENGTH, COFFEE_FT_12, COFFEE_MUTED,
                    198, 140, 34, 16);
    for(int i = 0; i < 5; i++) {
        hero_strength_beans[i] = coffee_icon_obj(hero, COFFEE_ICON_BEAN,
                                                 234 + i * 21, 134, 18,
                                                 COFFEE_GOLD);
    }
    hero_strength_value = coffee_label_at(hero, "", COFFEE_FT_12,
                                          COFFEE_MUTED, 350, 140, 48, 16);

    lv_obj_t * vol_card = coffee_card(hero, 198, 164, 104, 30, 15,
                                      COFFEE_CARD_UP, 0);
    hero_volume = coffee_label(vol_card, "", COFFEE_FT_13, COFFEE_CREAM);
    lv_obj_center(hero_volume);
    lv_obj_t * temp_card = coffee_card(hero, 310, 164, 104, 30, 15,
                                       COFFEE_CARD_UP, 0);
    hero_temp = coffee_label(temp_card, "", COFFEE_FT_13, COFFEE_CREAM);
    lv_obj_center(hero_temp);

    lv_obj_t * custom = coffee_button(hero, 198, 214, 104, 48, false,
                                      COFFEE_TXT_CUSTOMIZE, COFFEE_FT_14B,
                                      "customize_button");
    lv_obj_add_event_cb(custom, custom_event_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t * brew = coffee_button(hero, 310, 214, 122, 48, true,
                                    COFFEE_TXT_BREW, COFFEE_FT_14B,
                                    "brew_button");
    lv_obj_add_event_cb(brew, brew_event_cb, LV_EVENT_CLICKED, NULL);
    hero_brew_label = lv_obj_get_child(brew, 0);
}

static void build_status(lv_obj_t * parent)
{
    lv_obj_t * panel = coffee_card(parent, 476, 236, 208, 284, 20,
                                   COFFEE_CARD, COFFEE_LINE);
    coffee_label_at(panel, COFFEE_TXT_MACHINE_STATUS, COFFEE_FT_14B,
                    COFFEE_CREAM, 14, 10, 120, 20);
    lv_obj_t * ready = coffee_pill(panel, 142, 8, 52, 22, COFFEE_CARD_UP,
                                   COFFEE_TXT_READY, COFFEE_FT_12,
                                   COFFEE_GREEN, 11);
    (void)ready;

    for(int i = 0; i < 4; i++) {
        int y = 42 + i * 44;
        coffee_icon_obj(panel, meter_icons[i], 14, y + 4, 18, COFFEE_GOLD_DIM);
        coffee_label_at(panel, meter_names[i], COFFEE_FT_12, COFFEE_MUTED,
                        40, y, 90, 16);
        meter_value[i] = coffee_label_at(panel, "", COFFEE_FT_12,
                                         COFFEE_CREAM, 130, y, 58, 16);
        lv_obj_set_style_text_align(meter_value[i], LV_TEXT_ALIGN_RIGHT, 0);
        meter_fill[i] = coffee_bar(panel, 40, y + 22, 154, 5, COFFEE_LINE,
                                   COFFEE_GOLD, NULL);
    }

    lv_obj_t * divider = coffee_box(panel, 14, 222, 180, 1);
    lv_obj_set_style_bg_color(divider, lv_color_hex(COFFEE_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);

    today_label = coffee_label_at(panel, "", COFFEE_FT_14, COFFEE_CREAM,
                                  14, 232, 100, 20);
    coffee_label_at(panel, COFFEE_TXT_WEEK, COFFEE_FT_12, COFFEE_MUTED,
                    14, 256, 60, 16);

    for(int i = 0; i < 7; i++) {
        week_bars[i] = coffee_card(panel, 104 + i * 13, 248, 8, 12, 2,
                                   COFFEE_GOLD_DIM, 0);
    }
}

lv_obj_t * coffee_home_create(lv_obj_t * parent)
{
    page = coffee_box(parent, 0, 0, COFFEE_PAGE_W, COFFEE_PAGE_H);

    greeting = coffee_label_at(page, "", COFFEE_FT_24B, COFFEE_CREAM,
                               20, 10, 420, 32);
    coffee_label_at(page, COFFEE_TXT_GREETING_SUB, COFFEE_FT_13,
                    COFFEE_MUTED, 20, 46, 360, 18);

    lv_obj_t * prev = coffee_icon_button(page, 600, 14, 30,
                                          COFFEE_ICON_CHEVRON_LEFT,
                                          COFFEE_GOLD_BRIGHT, COFFEE_CARD,
                                          "carousel_prev");
    lv_obj_add_event_cb(prev, arrow_event_cb, LV_EVENT_CLICKED, coffee_int(-1));
    lv_obj_t * next = coffee_icon_button(page, 640, 14, 30,
                                          COFFEE_ICON_CHEVRON_RIGHT,
                                          COFFEE_GOLD_BRIGHT, COFFEE_CARD,
                                          "carousel_next");
    lv_obj_add_event_cb(next, arrow_event_cb, LV_EVENT_CLICKED, coffee_int(1));

    build_carousel(page);
    build_hero(page);
    build_status(page);
    return page;
}

static void refresh_cards(void)
{
    int selected = coffee_state.selected_drink;
    for(int i = 0; i < COFFEE_DRINK_COUNT; i++) {
        bool on = i == selected;
        lv_obj_set_style_border_width(cards[i], on ? 2 : 1, 0);
        lv_obj_set_style_border_color(cards[i],
                                      lv_color_hex(on ? COFFEE_GOLD
                                                      : COFFEE_LINE), 0);
        lv_obj_set_style_bg_color(cards[i], lv_color_hex(COFFEE_CARD), 0);
        lv_obj_set_style_text_color(card_names[i],
                                    lv_color_hex(on ? COFFEE_GOLD_BRIGHT
                                                    : COFFEE_CREAM), 0);
    }
    lv_obj_update_layout(carousel);
    int target = (selected - 2) * (CARD_W + CARD_GAP);
    int maximum = COFFEE_DRINK_COUNT * (CARD_W + CARD_GAP) - CARD_GAP - 664;
    if(target < 0) target = 0;
    if(target > maximum) target = maximum;
    lv_obj_scroll_to_x(carousel, target, LV_ANIM_OFF);
}

static void refresh_hero(void)
{
    coffee_drink_t * drink = coffee_selected();
    lv_image_set_src(hero_art, coffee_art(drink->art));
    lv_label_set_text(hero_name, drink->name);
    lv_label_set_text(hero_italian, drink->italian);
    lv_label_set_text(hero_desc, drink->desc);

    for(int i = 0; i < 5; i++) {
        bool on = i < drink->strength;
        lv_obj_set_style_image_recolor(hero_strength_beans[i],
                                       lv_color_hex(on ? COFFEE_GOLD
                                                       : COFFEE_LINE), 0);
    }
    char buffer[32];
    if(drink->strength > 0) {
        snprintf(buffer, sizeof(buffer), "%d/5", drink->strength);
    }
    else {
        snprintf(buffer, sizeof(buffer), "--");
    }
    lv_label_set_text(hero_strength_value, buffer);

    snprintf(buffer, sizeof(buffer), "%d %s", drink->volume, COFFEE_TXT_ML);
    lv_label_set_text(hero_volume, buffer);
    coffee_format_temp(buffer, sizeof(buffer), drink->cold ? 4
                                                          : drink->temp_c);
    lv_label_set_text(hero_temp, buffer);

    bool favorite = coffee_is_favorite(coffee_state.selected_drink);
    lv_obj_t * icon = lv_obj_get_child(hero_favorite, 0);
    if(icon != NULL) {
        lv_image_set_src(icon, coffee_icon(favorite ? COFFEE_ICON_HEART_FILLED
                                                    : COFFEE_ICON_HEART));
        lv_obj_set_style_image_recolor(icon,
                                       lv_color_hex(favorite ? COFFEE_GOLD_BRIGHT
                                                             : COFFEE_MUTED), 0);
    }

    if(drink->water_only) {
        lv_label_set_text(hero_brew_label, COFFEE_TXT_START_WATER);
    }
    else if(drink->steam_only) {
        lv_label_set_text(hero_brew_label, COFFEE_TXT_START_STEAM);
    }
    else {
        lv_label_set_text(hero_brew_label, COFFEE_TXT_BREW);
    }
}

static void refresh_status(void)
{
    int values[4];
    values[0] = coffee_state.water_ml * 100 / coffee_state.water_cap_ml;
    values[1] = coffee_state.beans_g * 100 / coffee_state.beans_cap_g;
    values[2] = coffee_state.milk_ml * 100 / coffee_state.milk_cap_ml;
    values[3] = coffee_state.grounds_pct;

    static const uint32_t colors[4] = {
        COFFEE_BLUE, COFFEE_GOLD, COFFEE_CREAM, COFFEE_AMBER,
    };
    for(int i = 0; i < 4; i++) {
        char buffer[16];
        snprintf(buffer, sizeof(buffer), "%d%%", values[i]);
        lv_label_set_text(meter_value[i], buffer);
        lv_obj_set_style_bg_color(lv_obj_get_parent(meter_fill[i]),
                                  lv_color_hex(COFFEE_LINE), 0);
        lv_obj_set_style_bg_color(meter_fill[i],
                                  lv_color_hex(values[i] < 15 ? COFFEE_RED
                                                              : colors[i]), 0);
        coffee_bar_set(meter_fill[i], values[i]);
    }

    coffee_profile_t * profile = coffee_profile();
    char buffer[48];
    snprintf(buffer, sizeof(buffer), "%s %d %s", COFFEE_TXT_TODAY,
             profile->today, COFFEE_TXT_CUP_UNIT);
    lv_label_set_text(today_label, buffer);

    for(int i = 0; i < 7; i++) {
        int height = 5 + profile->week[i] * 5;
        if(height > 28) height = 28;
        lv_obj_set_height(week_bars[i], height);
        lv_obj_set_y(week_bars[i], 274 - height);
        lv_obj_set_style_bg_color(week_bars[i],
                                  lv_color_hex(i == 6 ? COFFEE_GOLD_BRIGHT
                                                      : COFFEE_GOLD_DIM), 0);
    }
}

void coffee_home_refresh(void)
{
    if(page == NULL) return;
    coffee_profile_t * profile = coffee_profile();
    char buffer[64];
    snprintf(buffer, sizeof(buffer), "%s%s", COFFEE_TXT_GREETING_MORNING,
             profile->name);
    lv_label_set_text(greeting, buffer);
    refresh_cards();
    refresh_hero();
    refresh_status();
}

#endif
