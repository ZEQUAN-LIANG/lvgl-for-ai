
#include "app.h"
#include "coffee_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include <stdio.h>

static lv_obj_t * page;
static lv_obj_t * grid;
static lv_obj_t * subtitle;

static const char * const card_ids[COFFEE_DRINK_COUNT] = {
    "favorite_card_0", "favorite_card_1",  "favorite_card_2",
    "favorite_card_3", "favorite_card_4",  "favorite_card_5",
    "favorite_card_6", "favorite_card_7",  "favorite_card_8",
    "favorite_card_9", "favorite_card_10", "favorite_card_11",
};
static const char * const brew_ids[COFFEE_DRINK_COUNT] = {
    "favorite_brew_0", "favorite_brew_1",  "favorite_brew_2",
    "favorite_brew_3", "favorite_brew_4",  "favorite_brew_5",
    "favorite_brew_6", "favorite_brew_7",  "favorite_brew_8",
    "favorite_brew_9", "favorite_brew_10", "favorite_brew_11",
};
static const char * const edit_ids[COFFEE_DRINK_COUNT] = {
    "favorite_edit_0", "favorite_edit_1",  "favorite_edit_2",
    "favorite_edit_3", "favorite_edit_4",  "favorite_edit_5",
    "favorite_edit_6", "favorite_edit_7",  "favorite_edit_8",
    "favorite_edit_9", "favorite_edit_10", "favorite_edit_11",
};

static void card_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_open_custom((int)(intptr_t)lv_event_get_user_data(event));
}

static void brew_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_start_brew((int)(intptr_t)lv_event_get_user_data(event));
}

static int favorite_count(void)
{
    uint32_t mask = coffee_profile()->favorites;
    int count = 0;
    for(int i = 0; i < COFFEE_DRINK_COUNT; i++) {
        if(mask & (1u << i)) count++;
    }
    return count;
}

static void build_empty(lv_obj_t * parent)
{
    coffee_icon_obj(parent, COFFEE_ICON_HEART, 320, 88, 64, COFFEE_GOLD_DIM);
    coffee_label_at(parent, COFFEE_TXT_FAV_EMPTY, COFFEE_FT_18B, COFFEE_MUTED,
                    0, 190, COFFEE_PAGE_W, 24);
    lv_obj_t * label =
        coffee_label_at(parent, COFFEE_TXT_FAV_EMPTY_HINT, COFFEE_FT_13,
                        COFFEE_DIM, 0, 222, COFFEE_PAGE_W, 20);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
}

static void build_card(lv_obj_t * parent, int drink, int column, int row)
{
    coffee_drink_t * item = &coffee_drinks[drink];
    int x = 20 + column * 222;
    int y = 12 + row * 206;

    lv_obj_t * card =
        coffee_card(parent, x, y, 208, 190, 18, COFFEE_CARD, COFFEE_LINE);
    coffee_clickable(card, card_ids[drink]);
    lv_obj_add_event_cb(card, card_event_cb, LV_EVENT_CLICKED,
                        coffee_int(drink));

    coffee_art_obj(card, item->art, 14, 16, 96);

    lv_obj_t * name = coffee_label_at(card, item->name, COFFEE_FT_18B,
                                      COFFEE_CREAM, 118, 18, 78, 42);
    lv_label_set_long_mode(name, LV_LABEL_LONG_WRAP);
    coffee_label_at(card, item->italian, COFFEE_FT_12, COFFEE_GOLD_DIM, 118, 58,
                    82, 16);

    char buffer[40];
    snprintf(buffer, sizeof(buffer), "%d %s", item->volume, COFFEE_TXT_ML);
    coffee_label_at(card, buffer, COFFEE_FT_12, COFFEE_MUTED, 118, 80, 82, 16);
    if(item->strength > 0) {
        snprintf(buffer, sizeof(buffer), "%d/5", item->strength);
    }
    else {
        snprintf(buffer, sizeof(buffer), "--");
    }
    coffee_label_at(card, buffer, COFFEE_FT_12, COFFEE_MUTED, 118, 98, 82, 16);

    lv_obj_t * brew =
        coffee_button(card, 14, 140, 84, 38, true, COFFEE_TXT_FAV_BREW,
                      COFFEE_FT_13, brew_ids[drink]);
    lv_obj_add_event_cb(brew, brew_event_cb, LV_EVENT_CLICKED,
                        coffee_int(drink));
    lv_obj_t * edit =
        coffee_button(card, 110, 140, 84, 38, false, COFFEE_TXT_FAV_EDIT,
                      COFFEE_FT_13, edit_ids[drink]);
    lv_obj_add_event_cb(edit, card_event_cb, LV_EVENT_CLICKED,
                        coffee_int(drink));
}

void coffee_favorites_refresh(void)
{
    if(page == NULL) return;
    int count = favorite_count();
    char buffer[96];
    snprintf(buffer, sizeof(buffer), "%s%s%d%s", coffee_profile()->name,
             COFFEE_TXT_FAV_SUB, count, COFFEE_TXT_FAV_COUNT_SUFFIX);
    lv_label_set_text(subtitle, buffer);

    lv_obj_clean(grid);
    if(count == 0) {
        build_empty(grid);
        return;
    }

    uint32_t mask = coffee_profile()->favorites;
    int index = 0;
    for(int drink = 0; drink < COFFEE_DRINK_COUNT; drink++) {
        if((mask & (1u << drink)) == 0) continue;
        build_card(grid, drink, index % 3, index / 3);
        index++;
    }
}

lv_obj_t * coffee_favorites_create(lv_obj_t * parent)
{
    page = coffee_box(parent, 0, 0, COFFEE_PAGE_W, COFFEE_PAGE_H);
    coffee_label_at(page, COFFEE_TXT_FAV_TITLE, COFFEE_FT_24B, COFFEE_CREAM, 20,
                    12, 300, 32);
    subtitle =
        coffee_label_at(page, "", COFFEE_FT_13, COFFEE_MUTED, 20, 48, 360, 18);
    grid = coffee_box(page, 0, 80, COFFEE_PAGE_W, COFFEE_PAGE_H - 80);
    app_obj_set_scrollable(grid, true);
    lv_obj_set_scroll_dir(grid, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(grid, LV_SCROLLBAR_MODE_OFF);
    coffee_favorites_refresh();
    return page;
}

#endif
