
#include "app.h"
#include "coffee_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "coffee_assets.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

coffee_state_t coffee_state = {
    .water_ml = 2050,
    .water_cap_ml = 2500,
    .beans_g = 340,
    .beans_cap_g = 500,
    .milk_ml = 480,
    .milk_cap_ml = 1000,
    .grounds_pct = 23,
    .rinse_pct = 92,
    .milk_clean_pct = 64,
    .scale_pct = 68,
    .filter_pct = 41,
    .brew_count = 128,
    .cups_since_descale = 128,
    .active_profile = 0,
    .selected_drink = COFFEE_DRINK_LATTE,
    .page = COFFEE_PAGE_HOME,
    .brightness = 100,
    .grind = 6,
    .temp_c = 93,
    .hardness = 2,
    .auto_off_min = 30,
    .sound = true,
    .eco = false,
    .preheat = false,
    .use_fahrenheit = false,
    .standby = false,
};

coffee_drink_t coffee_drinks[COFFEE_DRINK_COUNT] = {
    [COFFEE_DRINK_ESPRESSO] =
        {
            .name = COFFEE_TXT_D0_NAME,
            .italian = COFFEE_TXT_D0_IT,
            .desc = COFFEE_TXT_D0_DESC,
            .art = COFFEE_ART_ESPRESSO,
            .volume = 30,
            .volume_min = 20,
            .volume_max = 60,
            .volume_step = 5,
            .strength = 5,
            .temp_c = 93,
            .milk_ml = 0,
            .milk_max = 0,
            .foam = 0,
        },
    [COFFEE_DRINK_DOPPIO] =
        {
            .name = COFFEE_TXT_D1_NAME,
            .italian = COFFEE_TXT_D1_IT,
            .desc = COFFEE_TXT_D1_DESC,
            .art = COFFEE_ART_DOPPIO,
            .volume = 60,
            .volume_min = 40,
            .volume_max = 100,
            .volume_step = 5,
            .strength = 5,
            .temp_c = 93,
            .milk_ml = 0,
            .milk_max = 0,
            .foam = 0,
        },
    [COFFEE_DRINK_RISTRETTO] =
        {
            .name = COFFEE_TXT_D2_NAME,
            .italian = COFFEE_TXT_D2_IT,
            .desc = COFFEE_TXT_D2_DESC,
            .art = COFFEE_ART_RISTRETTO,
            .volume = 20,
            .volume_min = 15,
            .volume_max = 40,
            .volume_step = 5,
            .strength = 5,
            .temp_c = 93,
            .milk_ml = 0,
            .milk_max = 0,
            .foam = 0,
        },
    [COFFEE_DRINK_AMERICANO] =
        {
            .name = COFFEE_TXT_D3_NAME,
            .italian = COFFEE_TXT_D3_IT,
            .desc = COFFEE_TXT_D3_DESC,
            .art = COFFEE_ART_AMERICANO,
            .volume = 150,
            .volume_min = 80,
            .volume_max = 300,
            .volume_step = 10,
            .strength = 3,
            .temp_c = 93,
            .milk_ml = 0,
            .milk_max = 0,
            .foam = 0,
        },
    [COFFEE_DRINK_CAPPUCCINO] =
        {
            .name = COFFEE_TXT_D4_NAME,
            .italian = COFFEE_TXT_D4_IT,
            .desc = COFFEE_TXT_D4_DESC,
            .art = COFFEE_ART_CAPPUCCINO,
            .volume = 160,
            .volume_min = 120,
            .volume_max = 260,
            .volume_step = 10,
            .strength = 3,
            .temp_c = 93,
            .milk_ml = 120,
            .milk_max = 200,
            .foam = 3,
            .milk_drink = true,
        },
    [COFFEE_DRINK_LATTE] =
        {
            .name = COFFEE_TXT_D5_NAME,
            .italian = COFFEE_TXT_D5_IT,
            .desc = COFFEE_TXT_D5_DESC,
            .art = COFFEE_ART_LATTE,
            .volume = 220,
            .volume_min = 150,
            .volume_max = 320,
            .volume_step = 10,
            .strength = 3,
            .temp_c = 93,
            .milk_ml = 160,
            .milk_max = 240,
            .foam = 2,
            .milk_drink = true,
        },
    [COFFEE_DRINK_FLATWHITE] =
        {
            .name = COFFEE_TXT_D6_NAME,
            .italian = COFFEE_TXT_D6_IT,
            .desc = COFFEE_TXT_D6_DESC,
            .art = COFFEE_ART_FLATWHITE,
            .volume = 160,
            .volume_min = 120,
            .volume_max = 240,
            .volume_step = 10,
            .strength = 4,
            .temp_c = 93,
            .milk_ml = 110,
            .milk_max = 200,
            .foam = 1,
            .milk_drink = true,
        },
    [COFFEE_DRINK_MACCHIATO] =
        {
            .name = COFFEE_TXT_D7_NAME,
            .italian = COFFEE_TXT_D7_IT,
            .desc = COFFEE_TXT_D7_DESC,
            .art = COFFEE_ART_MACCHIATO,
            .volume = 40,
            .volume_min = 30,
            .volume_max = 80,
            .volume_step = 5,
            .strength = 5,
            .temp_c = 93,
            .milk_ml = 20,
            .milk_max = 60,
            .foam = 1,
            .milk_drink = true,
        },
    [COFFEE_DRINK_MOCHA] =
        {
            .name = COFFEE_TXT_D8_NAME,
            .italian = COFFEE_TXT_D8_IT,
            .desc = COFFEE_TXT_D8_DESC,
            .art = COFFEE_ART_MOCHA,
            .volume = 200,
            .volume_min = 150,
            .volume_max = 300,
            .volume_step = 10,
            .strength = 4,
            .temp_c = 93,
            .milk_ml = 130,
            .milk_max = 220,
            .foam = 2,
            .milk_drink = true,
        },
    [COFFEE_DRINK_COLDBREW] =
        {
            .name = COFFEE_TXT_D9_NAME,
            .italian = COFFEE_TXT_D9_IT,
            .desc = COFFEE_TXT_D9_DESC,
            .art = COFFEE_ART_COLDBREW,
            .volume = 200,
            .volume_min = 150,
            .volume_max = 300,
            .volume_step = 10,
            .strength = 4,
            .temp_c = 4,
            .milk_ml = 0,
            .milk_max = 0,
            .foam = 0,
            .cold = true,
        },
    [COFFEE_DRINK_HOTWATER] =
        {
            .name = COFFEE_TXT_D10_NAME,
            .italian = COFFEE_TXT_D10_IT,
            .desc = COFFEE_TXT_D10_DESC,
            .art = COFFEE_ART_HOTWATER,
            .volume = 200,
            .volume_min = 100,
            .volume_max = 300,
            .volume_step = 10,
            .strength = 0,
            .temp_c = 93,
            .milk_ml = 0,
            .milk_max = 0,
            .foam = 0,
            .water_only = true,
        },
    [COFFEE_DRINK_STEAM] =
        {
            .name = COFFEE_TXT_D11_NAME,
            .italian = COFFEE_TXT_D11_IT,
            .desc = COFFEE_TXT_D11_DESC,
            .art = COFFEE_ART_STEAM,
            .volume = 150,
            .volume_min = 100,
            .volume_max = 300,
            .volume_step = 10,
            .strength = 0,
            .temp_c = 93,
            .milk_ml = 150,
            .milk_max = 300,
            .foam = 3,
            .milk_drink = true,
            .steam_only = true,
        },
};

#define FAVORITE_BIT(drink) (1u << (drink))

coffee_profile_t coffee_profiles[3] = {
    {
        .name = COFFEE_TXT_PROFILE_0,
        .initial = "A",
        .color = 0xC8A464,
        .today = 2,
        .week = {1, 2, 3, 2, 4, 3, 2},
        .favorites = FAVORITE_BIT(COFFEE_DRINK_LATTE) |
                     FAVORITE_BIT(COFFEE_DRINK_ESPRESSO) |
                     FAVORITE_BIT(COFFEE_DRINK_FLATWHITE),
    },
    {
        .name = COFFEE_TXT_PROFILE_1,
        .initial = "M",
        .color = 0xB9857A,
        .today = 1,
        .week = {0, 1, 0, 2, 1, 1, 1},
        .favorites = FAVORITE_BIT(COFFEE_DRINK_CAPPUCCINO) |
                     FAVORITE_BIT(COFFEE_DRINK_MOCHA) |
                     FAVORITE_BIT(COFFEE_DRINK_COLDBREW),
    },
    {
        .name = COFFEE_TXT_PROFILE_2,
        .initial = "访",
        .color = 0x7F8FA6,
        .today = 0,
        .week = {0, 0, 1, 0, 0, 0, 0},
        .favorites = FAVORITE_BIT(COFFEE_DRINK_AMERICANO),
    },
};

coffee_drink_t * coffee_selected(void)
{
    int index = coffee_state.selected_drink;
    if(index < 0 || index >= COFFEE_DRINK_COUNT) index = 0;
    return &coffee_drinks[index];
}

coffee_profile_t * coffee_profile(void)
{
    int index = coffee_state.active_profile;
    if(index < 0 || index >= 3) index = 0;
    return &coffee_profiles[index];
}

bool coffee_is_favorite(int drink)
{
    if(drink < 0 || drink >= COFFEE_DRINK_COUNT) return false;
    return (coffee_profile()->favorites & FAVORITE_BIT(drink)) != 0;
}

void coffee_toggle_favorite(int drink)
{
    if(drink < 0 || drink >= COFFEE_DRINK_COUNT) return;
    coffee_profile_t * profile = coffee_profile();
    profile->favorites ^= FAVORITE_BIT(drink);
    bool added = (profile->favorites & FAVORITE_BIT(drink)) != 0;
    coffee_log("favorite drink=%d profile=%s added=%d", drink, profile->name,
               added ? 1 : 0);
    coffee_toast(added ? COFFEE_TXT_FAVORITE_ADDED
                       : COFFEE_TXT_FAVORITE_REMOVED);
    coffee_home_refresh();
    coffee_favorites_refresh();
}

void coffee_select_drink(int drink)
{
    if(drink < 0 || drink >= COFFEE_DRINK_COUNT) return;
    coffee_state.selected_drink = drink;
    coffee_log("select drink=%d name=%s", drink, coffee_drinks[drink].name);
    coffee_home_refresh();
}

void coffee_profile_next(void)
{
    coffee_state.active_profile = (coffee_state.active_profile + 1) % 3;
    coffee_profile_t * profile = coffee_profile();
    coffee_log("profile=%s", profile->name);
    char message[48];
    snprintf(message, sizeof(message), "%s%s", COFFEE_TXT_PROFILE_SWITCHED,
             profile->name);
    coffee_toast(message);
    coffee_shell_refresh();
    coffee_home_refresh();
    coffee_favorites_refresh();
}

void coffee_format_temp(char * buffer, size_t size, int celsius)
{
    if(coffee_state.use_fahrenheit) {
        int fahrenheit = celsius * 9 / 5 + 32;
        snprintf(buffer, size, "%d%s", fahrenheit, COFFEE_TXT_DEGREE_F);
    }
    else {
        snprintf(buffer, size, "%d%s", celsius, COFFEE_TXT_DEGREE_C);
    }
}

void coffee_format_clock(char * buffer, size_t size)
{
    uint32_t seconds = lv_tick_get() / 1000u;
    uint32_t total = 9u * 3600u + 41u * 60u + seconds;
    uint32_t hours = (total / 3600u) % 24u;
    uint32_t minutes = (total / 60u) % 60u;
    uint32_t secs = total % 60u;
    snprintf(buffer, size, "%02u:%02u:%02u", (unsigned)hours, (unsigned)minutes,
             (unsigned)secs);
}

void coffee_log(const char * format, ...)
{
    va_list args;
    va_start(args, format);
    printf("[coffee] ");
    vprintf(format, args);
    printf("\n");
    va_end(args);
}

const lv_font_t * coffee_font(coffee_font_id_t id)
{
    switch(id) {
        case COFFEE_FT_12:
            return &coffee_font_12;
        case COFFEE_FT_13:
            return &coffee_font_13;
        case COFFEE_FT_14:
            return &coffee_font_14;
        case COFFEE_FT_14B:
            return &coffee_font_14b;
        case COFFEE_FT_16:
            return &coffee_font_16;
        case COFFEE_FT_18B:
            return &coffee_font_18b;
        case COFFEE_FT_24B:
            return &coffee_font_24b;
        case COFFEE_FT_32B:
            return &coffee_font_32b;
        case COFFEE_FT_44B:
        default:
            return &coffee_font_44b;
    }
}

const lv_image_dsc_t * coffee_icon(coffee_icon_id_t id)
{
    switch(id) {
        case COFFEE_ICON_BEAN:
            return &coffee_icon_bean;
        case COFFEE_ICON_WATER:
            return &coffee_icon_water;
        case COFFEE_ICON_MILK:
            return &coffee_icon_milk;
        case COFFEE_ICON_GROUNDS:
            return &coffee_icon_grounds;
        case COFFEE_ICON_TEMP:
            return &coffee_icon_temp;
        case COFFEE_ICON_PRESSURE:
            return &coffee_icon_pressure;
        case COFFEE_ICON_CLOCK:
            return &coffee_icon_clock;
        case COFFEE_ICON_WIFI:
            return &coffee_icon_wifi;
        case COFFEE_ICON_GEAR:
            return &coffee_icon_gear;
        case COFFEE_ICON_HEART:
            return &coffee_icon_heart;
        case COFFEE_ICON_HEART_FILLED:
            return &coffee_icon_heart_filled;
        case COFFEE_ICON_STAR:
            return &coffee_icon_star;
        case COFFEE_ICON_STAR_FILLED:
            return &coffee_icon_star_filled;
        case COFFEE_ICON_BACK:
            return &coffee_icon_back;
        case COFFEE_ICON_CHEVRON_LEFT:
            return &coffee_icon_chevron_left;
        case COFFEE_ICON_CHEVRON_RIGHT:
            return &coffee_icon_chevron_right;
        case COFFEE_ICON_PLUS:
            return &coffee_icon_plus;
        case COFFEE_ICON_MINUS:
            return &coffee_icon_minus;
        case COFFEE_ICON_CHECK:
            return &coffee_icon_check;
        case COFFEE_ICON_CLOSE:
            return &coffee_icon_close;
        case COFFEE_ICON_POWER:
            return &coffee_icon_power;
        case COFFEE_ICON_CLEAN:
            return &coffee_icon_clean;
        case COFFEE_ICON_DESCALE:
            return &coffee_icon_descale;
        case COFFEE_ICON_FILTER:
            return &coffee_icon_filter;
        case COFFEE_ICON_CUP:
            return &coffee_icon_cup;
        case COFFEE_ICON_STEAM:
            return &coffee_icon_steam;
        case COFFEE_ICON_PROFILE:
            return &coffee_icon_profile;
        case COFFEE_ICON_DOUBLE_CUP:
            return &coffee_icon_double_cup;
        case COFFEE_ICON_PREHEAT:
            return &coffee_icon_preheat;
        case COFFEE_ICON_LEAF:
            return &coffee_icon_leaf;
        case COFFEE_ICON_MACHINE:
            return &coffee_icon_machine;
        case COFFEE_ICON_ARROW_RIGHT:
            return &coffee_icon_arrow_right;
        case COFFEE_ICON_WARNING:
            return &coffee_icon_warning;
        case COFFEE_ICON_SOUND:
            return &coffee_icon_sound;
        case COFFEE_ICON_BRIGHTNESS:
            return &coffee_icon_brightness;
        case COFFEE_ICON_ECO:
            return &coffee_icon_eco;
        case COFFEE_ICON_INFO:
        default:
            return &coffee_icon_info;
    }
}

const lv_image_dsc_t * coffee_brew_cup_asset(void)
{
    return &coffee_brew_cup;
}

const lv_image_dsc_t * coffee_art(coffee_art_id_t id)
{
    switch(id) {
        case COFFEE_ART_ESPRESSO:
            return &coffee_art_espresso;
        case COFFEE_ART_DOPPIO:
            return &coffee_art_doppio;
        case COFFEE_ART_RISTRETTO:
            return &coffee_art_ristretto;
        case COFFEE_ART_AMERICANO:
            return &coffee_art_americano;
        case COFFEE_ART_CAPPUCCINO:
            return &coffee_art_cappuccino;
        case COFFEE_ART_LATTE:
            return &coffee_art_latte;
        case COFFEE_ART_FLATWHITE:
            return &coffee_art_flatwhite;
        case COFFEE_ART_MACCHIATO:
            return &coffee_art_macchiato;
        case COFFEE_ART_MOCHA:
            return &coffee_art_mocha;
        case COFFEE_ART_COLDBREW:
            return &coffee_art_coldbrew;
        case COFFEE_ART_HOTWATER:
            return &coffee_art_hotwater;
        case COFFEE_ART_STEAM:
        default:
            return &coffee_art_steam;
    }
}

lv_obj_t * coffee_box(lv_obj_t * parent, int x, int y, int w, int h)
{
    lv_obj_t * obj = lv_obj_create(parent);
    lv_obj_set_pos(obj, x, y);
    lv_obj_set_size(obj, w, h);
    lv_obj_set_style_bg_opa(obj, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(obj, 0, 0);
    lv_obj_set_style_radius(obj, 0, 0);
    lv_obj_set_style_pad_all(obj, 0, 0);
    lv_obj_set_style_shadow_opa(obj, LV_OPA_TRANSP, 0);
    app_obj_set_scrollable(obj, false);
    app_obj_set_clickable(obj, false);
    return obj;
}

lv_obj_t * coffee_card(lv_obj_t * parent, int x, int y, int w, int h,
                       int radius, uint32_t bg, uint32_t border)
{
    lv_obj_t * card = coffee_box(parent, x, y, w, h);
    lv_obj_set_style_radius(card, radius, 0);
    lv_obj_set_style_bg_color(card, lv_color_hex(bg), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    if(border != 0) {
        lv_obj_set_style_border_width(card, 1, 0);
        lv_obj_set_style_border_color(card, lv_color_hex(border), 0);
        lv_obj_set_style_border_opa(card, LV_OPA_COVER, 0);
    }
    return card;
}

lv_obj_t * coffee_label(lv_obj_t * parent, const char * text,
                        coffee_font_id_t font, uint32_t color)
{
    lv_obj_t * label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, coffee_font(font), 0);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    app_obj_set_scrollable(label, false);
    app_obj_set_clickable(label, false);
    return label;
}

lv_obj_t * coffee_label_at(lv_obj_t * parent, const char * text,
                           coffee_font_id_t font, uint32_t color, int x, int y,
                           int w, int h)
{
    lv_obj_t * label = coffee_label(parent, text, font, color);
    lv_obj_set_pos(label, x, y);
    lv_obj_set_size(label, w, h);
    return label;
}

lv_obj_t * coffee_icon_obj(lv_obj_t * parent, coffee_icon_id_t icon, int x,
                           int y, int size, uint32_t color)
{
    lv_obj_t * image = lv_image_create(parent);
    lv_image_set_src(image, coffee_icon(icon));
    int offset = (28 - size) / 2;
    lv_obj_set_pos(image, x - offset, y - offset);
    if(size != 28) {
        lv_image_set_scale(image, (uint32_t)(LV_SCALE_NONE * size / 28));
    }
    lv_obj_set_style_image_recolor(image, lv_color_hex(color), 0);
    lv_obj_set_style_image_recolor_opa(image, LV_OPA_COVER, 0);
    app_obj_set_scrollable(image, false);
    app_obj_set_clickable(image, false);
    return image;
}

lv_obj_t * coffee_art_obj(lv_obj_t * parent, coffee_art_id_t art, int x, int y,
                          int size)
{
    lv_obj_t * image = lv_image_create(parent);
    lv_image_set_src(image, coffee_art(art));
    if(size != 176) {
        lv_image_set_scale(image, (uint32_t)(LV_SCALE_NONE * size / 176));
    }
    int offset = (176 - size) / 2;
    lv_obj_set_pos(image, x - offset, y - offset);
    app_obj_set_scrollable(image, false);
    app_obj_set_clickable(image, false);
    return image;
}

lv_obj_t * coffee_icon_button(lv_obj_t * parent, int x, int y, int size,
                              coffee_icon_id_t icon, uint32_t color,
                              uint32_t bg, const char * name)
{
    lv_obj_t * button = coffee_card(parent, x, y, size, size, size / 2, bg, 0);
    lv_obj_t * image = coffee_icon_obj(button, icon, 0, 0, 22, color);
    lv_obj_center(image);
    coffee_clickable(button, name);
    return button;
}

lv_obj_t * coffee_pill(lv_obj_t * parent, int x, int y, int w, int h,
                       uint32_t bg, const char * text, coffee_font_id_t font,
                       uint32_t fg, int radius)
{
    lv_obj_t * pill = coffee_card(parent, x, y, w, h, radius, bg, 0);
    lv_obj_t * label = coffee_label(pill, text, font, fg);
    lv_obj_center(label);
    return pill;
}

lv_obj_t * coffee_button(lv_obj_t * parent, int x, int y, int w, int h,
                         bool primary, const char * text, coffee_font_id_t font,
                         const char * name)
{
    lv_obj_t * button = coffee_card(parent, x, y, w, h, h / 2,
                                    primary ? COFFEE_GOLD : COFFEE_CARD_UP,
                                    primary ? 0 : COFFEE_GOLD_DIM);
    lv_obj_t * label = coffee_label(button, text, font,
                                    primary ? 0x191207 : COFFEE_GOLD_BRIGHT);
    lv_obj_center(label);
    coffee_clickable(button, name);
    return button;
}

lv_obj_t * coffee_bar(lv_obj_t * parent, int x, int y, int w, int h,
                      uint32_t track, uint32_t fill, const char * name)
{
    lv_obj_t * bar = coffee_card(parent, x, y, w, h, h / 2, track, 0);
    if(name != NULL) lv_obj_set_name(bar, name);
    lv_obj_t * value = lv_obj_create(bar);
    lv_obj_set_pos(value, 0, 0);
    lv_obj_set_size(value, 0, h);
    lv_obj_set_style_radius(value, h / 2, 0);
    lv_obj_set_style_bg_color(value, lv_color_hex(fill), 0);
    lv_obj_set_style_bg_opa(value, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(value, 0, 0);
    lv_obj_set_style_pad_all(value, 0, 0);
    app_obj_set_scrollable(value, false);
    app_obj_set_clickable(value, false);
    return value;
}

void coffee_bar_set(lv_obj_t * fill, int pct)
{
    if(fill == NULL) return;
    lv_obj_t * track = lv_obj_get_parent(fill);
    int width = lv_obj_get_width(track);
    if(pct < 0) pct = 0;
    if(pct > 100) pct = 100;
    lv_obj_set_width(fill, width * pct / 100);
}

lv_obj_t * coffee_toggle(lv_obj_t * parent, int x, int y, int w, int h, bool on,
                         const char * name)
{
    lv_obj_t * track = coffee_card(parent, x, y, w, h, h / 2,
                                   on ? COFFEE_GOLD : COFFEE_LINE, 0);
    lv_obj_t * knob = lv_obj_create(track);
    lv_obj_set_size(knob, h - 6, h - 6);
    lv_obj_set_style_radius(knob, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(knob, lv_color_hex(COFFEE_CREAM), 0);
    lv_obj_set_style_bg_opa(knob, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(knob, 0, 0);
    lv_obj_set_style_shadow_color(knob, lv_color_hex(0x000000), 0);
    lv_obj_set_style_shadow_width(knob, 4, 0);
    lv_obj_set_style_shadow_opa(knob, 90, 0);
    app_obj_set_scrollable(knob, false);
    app_obj_set_clickable(knob, false);
    coffee_clickable(track, name);
    coffee_toggle_set(track, on);
    return track;
}

void coffee_toggle_set(lv_obj_t * track, bool on)
{
    if(track == NULL) return;
    lv_obj_t * knob = lv_obj_get_child(track, 0);
    if(knob == NULL) return;
    int track_w = lv_obj_get_width(track);
    int track_h = lv_obj_get_height(track);
    int knob_w = lv_obj_get_width(knob);
    int knob_h = lv_obj_get_height(knob);
    lv_obj_set_pos(knob, on ? track_w - knob_w - 3 : 3, (track_h - knob_h) / 2);
    lv_obj_set_style_bg_color(track,
                              lv_color_hex(on ? COFFEE_GOLD : COFFEE_LINE), 0);
}

void coffee_clickable(lv_obj_t * obj, const char * name)
{
    app_obj_set_clickable(obj, true);
    if(name != NULL) {
        lv_obj_set_name(obj, name);
    }
}

void coffee_hide(lv_obj_t * obj, bool hidden)
{
    if(obj != NULL) app_obj_set_hidden(obj, hidden);
}

static lv_obj_t * toast_box;
static lv_obj_t * toast_label;
static lv_timer_t * toast_timer;
static lv_obj_t * dim_overlay;
static lv_obj_t * modal_host;

static void toast_timer_cb(lv_timer_t * timer)
{
    (void)timer;
    toast_timer = NULL;
    coffee_hide(toast_box, true);
}

void coffee_toast(const char * text)
{
    if(text == NULL) return;
    if(toast_box == NULL) {
        toast_box = coffee_card(lv_screen_active(), 210, 540, 380, 46, 23,
                                COFFEE_CARD_UP, COFFEE_GOLD_DIM);
        lv_obj_set_style_shadow_color(toast_box, lv_color_hex(0x000000), 0);
        lv_obj_set_style_shadow_width(toast_box, 18, 0);
        lv_obj_set_style_shadow_opa(toast_box, 110, 0);
        coffee_icon_obj(toast_box, COFFEE_ICON_CHECK, 14, 11, 22,
                        COFFEE_GOLD_BRIGHT);
        toast_label = coffee_label_at(toast_box, "", COFFEE_FT_13, COFFEE_CREAM,
                                      44, 12, 320, 22);
    }
    lv_label_set_text(toast_label, text);
    app_obj_set_hidden(toast_box, false);
    lv_obj_move_foreground(toast_box);
    if(toast_timer != NULL) {
        lv_timer_delete(toast_timer);
        toast_timer = NULL;
    }
    toast_timer = lv_timer_create(toast_timer_cb, 1800, NULL);
    lv_timer_set_repeat_count(toast_timer, 1);
}

void coffee_dim_overlay_set(lv_obj_t * obj)
{
    dim_overlay = obj;
}

void coffee_apply_brightness(void)
{
    if(dim_overlay == NULL) return;
    int opa = (100 - coffee_state.brightness) * 3;
    if(opa < 0) opa = 0;
    if(opa > 200) opa = 200;
    lv_obj_set_style_bg_opa(dim_overlay, (lv_opa_t)opa, 0);
}

lv_obj_t * coffee_modal_host(void)
{
    return modal_host;
}

void coffee_set_modal_host(lv_obj_t * host)
{
    modal_host = host;
}

lv_obj_t * coffee_modal_open(int w, int h)
{
    if(modal_host == NULL) return NULL;
    coffee_brew_abort();
    coffee_maintenance_abort();
    lv_obj_clean(modal_host);
    app_obj_set_hidden(modal_host, false);
    lv_obj_move_foreground(modal_host);

    lv_obj_t * scrim = lv_obj_create(modal_host);
    lv_obj_set_pos(scrim, 0, 0);
    lv_obj_set_size(scrim, COFFEE_SCREEN_W, COFFEE_SCREEN_H);
    lv_obj_set_style_bg_color(scrim, lv_color_hex(0x000000), 0);
    lv_obj_set_style_bg_opa(scrim, 205, 0);
    lv_obj_set_style_border_width(scrim, 0, 0);
    lv_obj_set_style_radius(scrim, 0, 0);
    lv_obj_set_style_pad_all(scrim, 0, 0);
    app_obj_set_scrollable(scrim, false);
    coffee_clickable(scrim, "modal_scrim");

    lv_obj_t * panel = coffee_card(modal_host, (COFFEE_SCREEN_W - w) / 2,
                                   (COFFEE_SCREEN_H - h) / 2, w, h, 22,
                                   COFFEE_CARD, COFFEE_LINE);
    lv_obj_set_style_shadow_color(panel, lv_color_hex(0x000000), 0);
    lv_obj_set_style_shadow_width(panel, 40, 0);
    lv_obj_set_style_shadow_opa(panel, 150, 0);
    lv_obj_set_style_shadow_ofs_y(panel, 16, 0);
    return panel;
}

void coffee_modal_close(void)
{
    coffee_brew_abort();
    coffee_maintenance_abort();
    if(modal_host == NULL) return;
    lv_obj_clean(modal_host);
    app_obj_set_hidden(modal_host, true);
}

void coffee_refresh_all(void)
{
    coffee_shell_refresh();
    coffee_home_refresh();
    coffee_favorites_refresh();
    coffee_maintenance_refresh();
    coffee_settings_refresh();
}

#endif
