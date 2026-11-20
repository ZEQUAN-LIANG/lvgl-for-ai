
#ifndef COFFEE_UI_H
#define COFFEE_UI_H

#include "lvgl.h"
#include "coffee_texts.h"

#include <stdbool.h>
#include <stdint.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#define COFFEE_SCREEN_W 800
#define COFFEE_SCREEN_H 600
#define COFFEE_TOP_H    58
#define COFFEE_NAV_W    96
#define COFFEE_PAGE_W   (COFFEE_SCREEN_W - COFFEE_NAV_W)
#define COFFEE_PAGE_H   (COFFEE_SCREEN_H - COFFEE_TOP_H)

#define COFFEE_BG          0x0D0B09
#define COFFEE_BG_DEEP     0x070605
#define COFFEE_BG_WARM     0x1B1510
#define COFFEE_CARD        0x17140F
#define COFFEE_CARD_UP     0x211B14
#define COFFEE_LINE        0x2E261C
#define COFFEE_LINE_SOFT   0x241E17
#define COFFEE_GOLD        0xC8A464
#define COFFEE_GOLD_BRIGHT 0xE6C68C
#define COFFEE_GOLD_DIM    0x7C6440
#define COFFEE_CREAM       0xF3EBDD
#define COFFEE_TEXT        0xF3EBDD
#define COFFEE_MUTED       0x9A8E7D
#define COFFEE_DIM         0x6E6355
#define COFFEE_GREEN       0x8FB47E
#define COFFEE_AMBER       0xD9A441
#define COFFEE_RED         0xC56C5A
#define COFFEE_BLUE        0x7FA7B8
#define COFFEE_SHADOW      0x000000

typedef enum {
    COFFEE_FT_12,
    COFFEE_FT_13,
    COFFEE_FT_14,
    COFFEE_FT_14B,
    COFFEE_FT_16,
    COFFEE_FT_18B,
    COFFEE_FT_24B,
    COFFEE_FT_32B,
    COFFEE_FT_44B,
} coffee_font_id_t;

typedef enum {
    COFFEE_ICON_BEAN,
    COFFEE_ICON_WATER,
    COFFEE_ICON_MILK,
    COFFEE_ICON_GROUNDS,
    COFFEE_ICON_TEMP,
    COFFEE_ICON_PRESSURE,
    COFFEE_ICON_CLOCK,
    COFFEE_ICON_WIFI,
    COFFEE_ICON_GEAR,
    COFFEE_ICON_HEART,
    COFFEE_ICON_HEART_FILLED,
    COFFEE_ICON_STAR,
    COFFEE_ICON_STAR_FILLED,
    COFFEE_ICON_BACK,
    COFFEE_ICON_CHEVRON_LEFT,
    COFFEE_ICON_CHEVRON_RIGHT,
    COFFEE_ICON_PLUS,
    COFFEE_ICON_MINUS,
    COFFEE_ICON_CHECK,
    COFFEE_ICON_CLOSE,
    COFFEE_ICON_POWER,
    COFFEE_ICON_CLEAN,
    COFFEE_ICON_DESCALE,
    COFFEE_ICON_FILTER,
    COFFEE_ICON_CUP,
    COFFEE_ICON_STEAM,
    COFFEE_ICON_PROFILE,
    COFFEE_ICON_DOUBLE_CUP,
    COFFEE_ICON_PREHEAT,
    COFFEE_ICON_LEAF,
    COFFEE_ICON_MACHINE,
    COFFEE_ICON_ARROW_RIGHT,
    COFFEE_ICON_WARNING,
    COFFEE_ICON_SOUND,
    COFFEE_ICON_BRIGHTNESS,
    COFFEE_ICON_ECO,
    COFFEE_ICON_INFO,
    COFFEE_ICON_COUNT
} coffee_icon_id_t;

typedef enum {
    COFFEE_ART_ESPRESSO,
    COFFEE_ART_DOPPIO,
    COFFEE_ART_RISTRETTO,
    COFFEE_ART_AMERICANO,
    COFFEE_ART_CAPPUCCINO,
    COFFEE_ART_LATTE,
    COFFEE_ART_FLATWHITE,
    COFFEE_ART_MACCHIATO,
    COFFEE_ART_MOCHA,
    COFFEE_ART_COLDBREW,
    COFFEE_ART_HOTWATER,
    COFFEE_ART_STEAM,
    COFFEE_ART_COUNT
} coffee_art_id_t;

typedef enum {
    COFFEE_DRINK_ESPRESSO = 0,
    COFFEE_DRINK_DOPPIO,
    COFFEE_DRINK_RISTRETTO,
    COFFEE_DRINK_AMERICANO,
    COFFEE_DRINK_CAPPUCCINO,
    COFFEE_DRINK_LATTE,
    COFFEE_DRINK_FLATWHITE,
    COFFEE_DRINK_MACCHIATO,
    COFFEE_DRINK_MOCHA,
    COFFEE_DRINK_COLDBREW,
    COFFEE_DRINK_HOTWATER,
    COFFEE_DRINK_STEAM,
    COFFEE_DRINK_COUNT
} coffee_drink_id_t;

typedef enum {
    COFFEE_PAGE_HOME = 0,
    COFFEE_PAGE_FAVORITES,
    COFFEE_PAGE_MAINTENANCE,
    COFFEE_PAGE_SETTINGS,
    COFFEE_PAGE_COUNT
} coffee_page_id_t;

typedef struct {
    const char * name;
    const char * italian;
    const char * desc;
    coffee_art_id_t art;
    int volume;
    int volume_min;
    int volume_max;
    int volume_step;
    int strength;
    int temp_c;
    int milk_ml;
    int milk_max;
    int foam;
    bool milk_drink;
    bool cold;
    bool water_only;
    bool steam_only;
    bool double_cup;
    bool preheat;
    int brews;
} coffee_drink_t;

typedef struct {
    const char * name;
    const char * initial;
    uint32_t color;
    int today;
    int week[7];
    uint32_t favorites;
} coffee_profile_t;

typedef struct {
    int water_ml;
    int water_cap_ml;
    int beans_g;
    int beans_cap_g;
    int milk_ml;
    int milk_cap_ml;
    int grounds_pct;
    int rinse_pct;
    int milk_clean_pct;
    int scale_pct;
    int filter_pct;
    int brew_count;
    int cups_since_descale;
    int active_profile;
    int selected_drink;
    int page;
    int brightness;
    int grind;
    int temp_c;
    int hardness;
    int auto_off_min;
    bool sound;
    bool eco;
    bool preheat;
    bool use_fahrenheit;
    bool standby;
} coffee_state_t;

extern coffee_state_t coffee_state;
extern coffee_drink_t coffee_drinks[COFFEE_DRINK_COUNT];
extern coffee_profile_t coffee_profiles[3];

const lv_font_t * coffee_font(coffee_font_id_t id);
const lv_image_dsc_t * coffee_icon(coffee_icon_id_t id);
const lv_image_dsc_t * coffee_art(coffee_art_id_t id);
const lv_image_dsc_t * coffee_brew_cup_asset(void);

lv_obj_t * coffee_box(lv_obj_t * parent, int x, int y, int w, int h);
lv_obj_t * coffee_card(lv_obj_t * parent, int x, int y, int w, int h,
                       int radius, uint32_t bg, uint32_t border);
lv_obj_t * coffee_label(lv_obj_t * parent, const char * text,
                        coffee_font_id_t font, uint32_t color);
lv_obj_t * coffee_label_at(lv_obj_t * parent, const char * text,
                           coffee_font_id_t font, uint32_t color, int x, int y,
                           int w, int h);
lv_obj_t * coffee_icon_obj(lv_obj_t * parent, coffee_icon_id_t icon, int x,
                           int y, int size, uint32_t color);
lv_obj_t * coffee_art_obj(lv_obj_t * parent, coffee_art_id_t art, int x, int y,
                          int size);
lv_obj_t * coffee_icon_button(lv_obj_t * parent, int x, int y, int size,
                              coffee_icon_id_t icon, uint32_t color,
                              uint32_t bg, const char * name);
lv_obj_t * coffee_pill(lv_obj_t * parent, int x, int y, int w, int h,
                       uint32_t bg, const char * text, coffee_font_id_t font,
                       uint32_t fg, int radius);
lv_obj_t * coffee_button(lv_obj_t * parent, int x, int y, int w, int h,
                         bool primary, const char * text, coffee_font_id_t font,
                         const char * name);
lv_obj_t * coffee_bar(lv_obj_t * parent, int x, int y, int w, int h,
                      uint32_t track, uint32_t fill, const char * name);
void coffee_bar_set(lv_obj_t * fill, int pct);
lv_obj_t * coffee_toggle(lv_obj_t * parent, int x, int y, int w, int h, bool on,
                         const char * name);
void coffee_toggle_set(lv_obj_t * track, bool on);
void coffee_clickable(lv_obj_t * obj, const char * name);
void coffee_hide(lv_obj_t * obj, bool hidden);

coffee_drink_t * coffee_selected(void);
coffee_profile_t * coffee_profile(void);
bool coffee_is_favorite(int drink);
void coffee_toggle_favorite(int drink);
void coffee_select_drink(int drink);
void coffee_profile_next(void);
void coffee_format_temp(char * buffer, size_t size, int celsius);
void coffee_format_clock(char * buffer, size_t size);
void coffee_log(const char * format, ...);

void coffee_toast(const char * text);
void coffee_apply_brightness(void);
void coffee_dim_overlay_set(lv_obj_t * obj);
void coffee_refresh_all(void);

void coffee_create(void);
void coffee_show_page(coffee_page_id_t page);
void coffee_toggle_standby(void);
lv_obj_t * coffee_modal_host(void);
void coffee_set_modal_host(lv_obj_t * host);
lv_obj_t * coffee_modal_open(int w, int h);
void coffee_modal_close(void);
void coffee_brew_abort(void);
void coffee_maintenance_abort(void);

lv_obj_t * coffee_home_create(lv_obj_t * parent);
lv_obj_t * coffee_favorites_create(lv_obj_t * parent);
lv_obj_t * coffee_maintenance_create(lv_obj_t * parent);
lv_obj_t * coffee_settings_create(lv_obj_t * parent);
void coffee_home_refresh(void);
void coffee_favorites_refresh(void);
void coffee_maintenance_refresh(void);
void coffee_settings_refresh(void);
void coffee_shell_refresh(void);
void coffee_open_custom(int drink);
void coffee_start_brew(int drink);
void coffee_open_maintenance_run(int which);

static inline void * coffee_int(int value)
{
    return (void *)(intptr_t)value;
}

static inline int coffee_int_of(void * value)
{
    return (int)(intptr_t)value;
}

#endif

#endif
