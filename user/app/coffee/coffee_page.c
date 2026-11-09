/**
 * @file coffee_page.c
 * The machine shell: ambient backdrop, top status bar, vertical navigation,
 * page host, standby layer and brightness overlay.
 */

#include "coffee_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include <stdio.h>

static lv_obj_t * page_host;
static lv_obj_t * pages[COFFEE_PAGE_COUNT];
static lv_obj_t * nav_items[COFFEE_PAGE_COUNT];
static lv_obj_t * nav_icons[COFFEE_PAGE_COUNT];
static lv_obj_t * nav_labels[COFFEE_PAGE_COUNT];
static lv_obj_t * nav_bars[COFFEE_PAGE_COUNT];
static lv_obj_t * top_clock;
static lv_obj_t * top_temp;
static lv_obj_t * profile_avatar;
static lv_obj_t * profile_initial;
static lv_obj_t * profile_name;
static lv_obj_t * standby_layer;
static lv_obj_t * standby_clock;
static lv_obj_t * dim_layer;

static const char * const nav_texts[COFFEE_PAGE_COUNT] = {
    COFFEE_TXT_NAV_COFFEE,
    COFFEE_TXT_NAV_FAVORITES,
    COFFEE_TXT_NAV_MAINTENANCE,
    COFFEE_TXT_NAV_SETTINGS,
};

static const coffee_icon_id_t nav_icon_ids[COFFEE_PAGE_COUNT] = {
    COFFEE_ICON_CUP,
    COFFEE_ICON_HEART,
    COFFEE_ICON_CLEAN,
    COFFEE_ICON_GEAR,
};

static const char * const nav_names[COFFEE_PAGE_COUNT] = {
    "nav_coffee", "nav_favorites", "nav_maintenance", "nav_settings",
};

static void nav_style(int active)
{
    for(int i = 0; i < COFFEE_PAGE_COUNT; i++) {
        bool on = i == active;
        lv_obj_set_style_bg_color(nav_items[i],
                                  lv_color_hex(on ? COFFEE_CARD_UP
                                                  : COFFEE_BG),
                                  0);
        lv_obj_set_style_bg_opa(nav_items[i], on ? LV_OPA_COVER
                                                 : LV_OPA_TRANSP, 0);
        lv_obj_set_style_border_width(nav_items[i], on ? 1 : 0, 0);
        lv_obj_set_style_border_color(nav_items[i],
                                      lv_color_hex(COFFEE_GOLD_DIM), 0);
        lv_obj_set_style_image_recolor(nav_icons[i],
                                       lv_color_hex(on ? COFFEE_GOLD_BRIGHT
                                                       : COFFEE_MUTED), 0);
        lv_obj_set_style_text_color(nav_labels[i],
                                    lv_color_hex(on ? COFFEE_CREAM
                                                    : COFFEE_MUTED), 0);
        coffee_hide(nav_bars[i], !on);
    }
}

void coffee_show_page(coffee_page_id_t page)
{
    if(page < 0 || page >= COFFEE_PAGE_COUNT) return;
    for(int i = 0; i < COFFEE_PAGE_COUNT; i++) {
        coffee_hide(pages[i], i != (int)page);
    }
    coffee_state.page = page;
    nav_style(page);
    coffee_log("page=%d", page);
    switch(page) {
        case COFFEE_PAGE_HOME:
            coffee_home_refresh();
            break;
        case COFFEE_PAGE_FAVORITES:
            coffee_favorites_refresh();
            break;
        case COFFEE_PAGE_MAINTENANCE:
            coffee_maintenance_refresh();
            break;
        case COFFEE_PAGE_SETTINGS:
            coffee_settings_refresh();
            break;
        default:
            break;
    }
}

static void nav_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int page = (int)(intptr_t)lv_event_get_user_data(event);
    coffee_show_page((coffee_page_id_t)page);
}

static void profile_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_profile_next();
}

static void standby_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_toggle_standby();
}

static void power_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    coffee_toggle_standby();
}

void coffee_toggle_standby(void)
{
    coffee_state.standby = !coffee_state.standby;
    if(coffee_state.standby) {
        coffee_log("standby=on");
        lv_obj_set_hidden(standby_layer, false);
        lv_obj_move_foreground(standby_layer);
    }
    else {
        coffee_log("standby=off");
        lv_obj_set_hidden(standby_layer, true);
        coffee_toast(COFFEE_TXT_TOAST_WAKE);
    }
}

static void clock_timer_cb(lv_timer_t * timer)
{
    (void)timer;
    char buffer[16];
    coffee_format_clock(buffer, sizeof(buffer));
    if(top_clock != NULL) lv_label_set_text(top_clock, buffer);
    if(standby_clock != NULL) lv_label_set_text(standby_clock, buffer);
}

void coffee_shell_refresh(void)
{
    char buffer[16];
    coffee_format_temp(buffer, sizeof(buffer), coffee_state.temp_c);
    if(top_temp != NULL) lv_label_set_text(top_temp, buffer);

    coffee_profile_t * profile = coffee_profile();
    if(profile_avatar != NULL) {
        lv_obj_set_style_bg_color(profile_avatar,
                                  lv_color_hex(profile->color), 0);
    }
    if(profile_initial != NULL) {
        lv_label_set_text(profile_initial, profile->initial);
    }
    if(profile_name != NULL) {
        lv_label_set_text(profile_name, profile->name);
    }
}

static void build_backdrop(lv_obj_t * screen)
{
    lv_obj_set_style_bg_color(screen, lv_color_hex(COFFEE_BG), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_hex(COFFEE_BG_WARM), 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(screen, 0, 0);
    lv_obj_set_scrollable(screen, false);

    lv_obj_t * glow = coffee_box(screen, -180, -220, 560, 560);
    lv_obj_set_style_radius(glow, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(glow, lv_color_hex(COFFEE_GOLD), 0);
    lv_obj_set_style_bg_opa(glow, 10, 0);

    glow = coffee_box(screen, 620, 380, 320, 320);
    lv_obj_set_style_radius(glow, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(glow, lv_color_hex(0xB4783C), 0);
    lv_obj_set_style_bg_opa(glow, 12, 0);

    lv_obj_t * ring = coffee_box(screen, 660, -90, 260, 260);
    lv_obj_set_style_radius(ring, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_border_width(ring, 1, 0);
    lv_obj_set_style_border_color(ring, lv_color_hex(COFFEE_LINE), 0);
    lv_obj_set_style_border_opa(ring, 150, 0);
}

static void build_top_bar(lv_obj_t * screen)
{
    lv_obj_t * bar = coffee_box(screen, 0, 0, COFFEE_SCREEN_W, COFFEE_TOP_H);
    lv_obj_t * line = coffee_box(bar, 0, COFFEE_TOP_H - 1, COFFEE_SCREEN_W, 1);
    lv_obj_set_style_bg_color(line, lv_color_hex(COFFEE_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);

    lv_obj_t * mark = coffee_card(bar, 20, 12, 34, 34, 17, COFFEE_GOLD, 0);
    lv_obj_t * bean = coffee_icon_obj(mark, COFFEE_ICON_BEAN, 0, 0, 22,
                                      0x1A1308);
    lv_obj_center(bean);

    coffee_label_at(bar, COFFEE_TXT_BRAND, COFFEE_FT_18B, COFFEE_CREAM,
                    64, 6, 180, 26);
    coffee_label_at(bar, COFFEE_TXT_BRAND_SUB, COFFEE_FT_12,
                    COFFEE_GOLD_DIM, 64, 32, 180, 16);

    lv_obj_t * status = coffee_card(bar, 236, 13, 170, 32, 16,
                                    COFFEE_CARD_UP, COFFEE_LINE);
    lv_obj_t * ready_dot = coffee_box(status, 14, 12, 7, 7);
    lv_obj_set_style_radius(ready_dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(ready_dot, lv_color_hex(COFFEE_GREEN), 0);
    lv_obj_set_style_bg_opa(ready_dot, LV_OPA_COVER, 0);
    coffee_label_at(status, COFFEE_TXT_READY, COFFEE_FT_13, COFFEE_CREAM,
                    28, 6, 44, 20);
    lv_obj_t * separator = coffee_box(status, 80, 20, 1, 16);
    lv_obj_set_style_bg_color(separator, lv_color_hex(COFFEE_LINE), 0);
    lv_obj_set_style_bg_opa(separator, LV_OPA_COVER, 0);
    top_temp = coffee_label_at(status, "", COFFEE_FT_13, COFFEE_MUTED,
                               94, 6, 64, 20);

    coffee_label_at(bar, COFFEE_TXT_WEATHER, COFFEE_FT_13, COFFEE_MUTED,
                    420, 19, 100, 20);

    coffee_icon_obj(bar, COFFEE_ICON_WIFI, 524, 17, 24, COFFEE_DIM);

    top_clock = coffee_label_at(bar, "09:41:00", COFFEE_FT_24B,
                                COFFEE_CREAM, 552, 6, 112, 30);
    coffee_label_at(bar, COFFEE_TXT_DATE, COFFEE_FT_12, COFFEE_MUTED,
                    552, 36, 112, 16);

    lv_obj_t * profile = coffee_card(bar, 680, 9, 104, 40, 20,
                                     COFFEE_CARD_UP, COFFEE_LINE);
    coffee_clickable(profile, "profile_switch");
    lv_obj_add_event_cb(profile, profile_event_cb, LV_EVENT_CLICKED, NULL);
    profile_avatar = coffee_card(profile, 6, 5, 30, 30, 15, COFFEE_GOLD, 0);
    profile_initial = coffee_label(profile_avatar, "A", COFFEE_FT_14B,
                                   0x1A1308);
    lv_obj_center(profile_initial);
    profile_name = coffee_label_at(profile, "", COFFEE_FT_13, COFFEE_CREAM,
                                   42, 12, 38, 18);
    coffee_icon_obj(profile, COFFEE_ICON_CHEVRON_RIGHT, 88, 17, 14,
                    COFFEE_GOLD_DIM);
}

static void build_nav(lv_obj_t * screen)
{
    lv_obj_t * nav = coffee_card(screen, 0, COFFEE_TOP_H, COFFEE_NAV_W,
                                 COFFEE_PAGE_H, 0, 0x110E0B, 0);
    lv_obj_t * divider = coffee_box(nav, COFFEE_NAV_W - 1, 0, 1,
                                    COFFEE_PAGE_H);
    lv_obj_set_style_bg_color(divider, lv_color_hex(COFFEE_LINE_SOFT), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);

    for(int i = 0; i < COFFEE_PAGE_COUNT; i++) {
        lv_obj_t * item = coffee_card(nav, 16, 22 + i * 78, 64, 64, 18,
                                      COFFEE_BG, 0);
        coffee_clickable(item, nav_names[i]);
        lv_obj_add_event_cb(item, nav_event_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        lv_obj_t * icon = coffee_icon_obj(item, nav_icon_ids[i], 0, 0, 24,
                                          COFFEE_MUTED);
        lv_obj_align(icon, LV_ALIGN_TOP_MID, 0, 8);
        lv_obj_t * label = coffee_label(item, nav_texts[i], COFFEE_FT_12,
                                        COFFEE_MUTED);
        lv_obj_align(label, LV_ALIGN_BOTTOM_MID, 0, -7);
        lv_obj_t * bar = coffee_box(nav, 0, 22 + i * 78 + 20, 3, 24);
        lv_obj_set_style_radius(bar, 2, 0);
        lv_obj_set_style_bg_color(bar, lv_color_hex(COFFEE_GOLD), 0);
        lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
        coffee_hide(bar, true);

        nav_items[i] = item;
        nav_icons[i] = icon;
        nav_labels[i] = label;
        nav_bars[i] = bar;
    }

    lv_obj_t * power = coffee_icon_button(nav, 26, COFFEE_PAGE_H - 62, 44,
                                           COFFEE_ICON_POWER, COFFEE_MUTED,
                                           COFFEE_CARD_UP, "nav_power");
    lv_obj_add_event_cb(power, power_event_cb, LV_EVENT_CLICKED, NULL);
}

static void build_standby(lv_obj_t * screen)
{
    standby_layer = coffee_card(screen, 0, 0, COFFEE_SCREEN_W,
                                COFFEE_SCREEN_H, 0, COFFEE_BG_DEEP, 0);
    coffee_clickable(standby_layer, "standby_wake");
    lv_obj_add_event_cb(standby_layer, standby_event_cb, LV_EVENT_CLICKED,
                        NULL);

    lv_obj_t * line = coffee_box(standby_layer, 350, 168, 100, 2);
    lv_obj_set_style_radius(line, 1, 0);
    lv_obj_set_style_bg_color(line, lv_color_hex(COFFEE_GOLD), 0);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);

    lv_obj_t * brand = coffee_label_at(standby_layer, COFFEE_TXT_BRAND,
                                       COFFEE_FT_44B, COFFEE_GOLD,
                                       0, 190, COFFEE_SCREEN_W, 56);
    lv_obj_set_style_text_align(brand, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_t * sub = coffee_label_at(standby_layer, COFFEE_TXT_BRAND_SUB,
                                     COFFEE_FT_14, COFFEE_GOLD_DIM,
                                     0, 252, COFFEE_SCREEN_W, 22);
    lv_obj_set_style_text_align(sub, LV_TEXT_ALIGN_CENTER, 0);

    standby_clock = coffee_label_at(standby_layer, "09:41:00",
                                    COFFEE_FT_32B, COFFEE_CREAM,
                                    0, 300, COFFEE_SCREEN_W, 42);
    lv_obj_set_style_text_align(standby_clock, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t * hint = coffee_label_at(standby_layer, COFFEE_TXT_WAKE,
                                      COFFEE_FT_14, COFFEE_MUTED,
                                      0, 378, COFFEE_SCREEN_W, 22);
    lv_obj_set_style_text_align(hint, LV_TEXT_ALIGN_CENTER, 0);

    coffee_hide(standby_layer, true);
}

void coffee_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    build_backdrop(screen);
    build_top_bar(screen);
    build_nav(screen);

    page_host = coffee_box(screen, COFFEE_NAV_W, COFFEE_TOP_H,
                           COFFEE_PAGE_W, COFFEE_PAGE_H);
    pages[COFFEE_PAGE_HOME] = coffee_home_create(page_host);
    pages[COFFEE_PAGE_FAVORITES] = coffee_favorites_create(page_host);
    pages[COFFEE_PAGE_MAINTENANCE] = coffee_maintenance_create(page_host);
    pages[COFFEE_PAGE_SETTINGS] = coffee_settings_create(page_host);
    coffee_hide(pages[COFFEE_PAGE_FAVORITES], true);
    coffee_hide(pages[COFFEE_PAGE_MAINTENANCE], true);
    coffee_hide(pages[COFFEE_PAGE_SETTINGS], true);

    lv_obj_t * modal = coffee_box(screen, 0, 0, COFFEE_SCREEN_W,
                                  COFFEE_SCREEN_H);
    coffee_set_modal_host(modal);
    coffee_hide(modal, true);

    build_standby(screen);

    dim_layer = coffee_box(screen, 0, 0, COFFEE_SCREEN_W, COFFEE_SCREEN_H);
    lv_obj_set_style_bg_color(dim_layer, lv_color_hex(0x000000), 0);
    lv_obj_set_style_bg_opa(dim_layer, 0, 0);
    lv_obj_set_clickable(dim_layer, false);
    coffee_dim_overlay_set(dim_layer);

    coffee_show_page(COFFEE_PAGE_HOME);
    coffee_shell_refresh();
    coffee_apply_brightness();

    lv_timer_create(clock_timer_cb, 1000, NULL);
    coffee_log("create drinks=%d", COFFEE_DRINK_COUNT);
}

#endif /* LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6 */
