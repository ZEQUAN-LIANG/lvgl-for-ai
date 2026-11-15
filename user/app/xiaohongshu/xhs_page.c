
#include "app.h"
#include "xhs_page.h"
#include "xhs_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include <stdint.h>
#include <stdio.h>

static lv_obj_t * root_pages[4];
static lv_obj_t * nav_labels[4];
static lv_obj_t * tab_host;
static lv_obj_t * overlay_host;
static lv_obj_t * bottom_nav;

static const char * const nav_texts[4] = {
    XHS_TXT_NAV_HOME,
    XHS_TXT_NAV_MARKET,
    XHS_TXT_NAV_MESSAGE,
    XHS_TXT_NAV_ME,
};

static void xhs_nav_style(int active)
{
    for(int i = 0; i < 4; i++) {
        lv_obj_set_style_text_font(
            nav_labels[i], xhs_font(i == active ? XHS_FT_12B : XHS_FT_12), 0);
        lv_obj_set_style_text_color(
            nav_labels[i], lv_color_hex(i == active ? XHS_TEXT : XHS_MUTED), 0);
    }
}

void xhs_show_root(int index)
{
    if(index < 0 || index >= 4) return;
    for(int i = 0; i < 4; i++) {
        if(root_pages[i] != NULL) {
            xhs_set_hidden(root_pages[i], i != index);
        }
    }
    xhs_set_hidden(overlay_host, true);
    xhs_set_hidden(bottom_nav, false);
    xhs_nav_style(index);
    printf("[xhs] nav=%s\n", nav_texts[index]);
}

void xhs_open_overlay(lv_obj_t * page)
{
    if(page == NULL) return;
    xhs_set_hidden(bottom_nav, true);
    xhs_set_hidden(overlay_host, false);
    uint32_t count = lv_obj_get_child_count(overlay_host);
    for(uint32_t i = 0; i < count; i++) {
        lv_obj_t * child = lv_obj_get_child(overlay_host, (int32_t)i);
        xhs_set_hidden(child, child != page);
    }
    xhs_set_hidden(page, false);
    lv_obj_move_to_index(page, -1);
}

void xhs_close_overlay(void)
{
    xhs_set_hidden(overlay_host, true);
    xhs_set_hidden(bottom_nav, false);
    xhs_home_sync_likes();
}

lv_obj_t * xhs_overlay_host(void)
{
    return overlay_host;
}

static void xhs_nav_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    xhs_show_root((int)(intptr_t)lv_event_get_user_data(event));
}

static void xhs_publish_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    printf("[xhs] publish clicked\n");
    xhs_publish_open();
}

static void xhs_build_status_bar(lv_obj_t * panel)
{
    lv_obj_t * time = xhs_label(panel, "9:41", XHS_FT_14, 0x111113);
    lv_obj_set_pos(time, 18, 3);

    xhs_image(panel, XHS_ICON_SIGNAL, 228, 10);
    xhs_image(panel, XHS_ICON_WIFI, 247, 10);
    xhs_image(panel, XHS_ICON_BATTERY, 266, 9);
}

static void xhs_bottom_nav(lv_obj_t * panel)
{
    bottom_nav =
        xhs_box(panel, 0, XHS_SCREEN_H - XHS_NAV_H, XHS_SCREEN_W, XHS_NAV_H);
    lv_obj_set_style_bg_color(bottom_nav, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(bottom_nav, LV_OPA_COVER, 0);

    lv_obj_t * divider = xhs_box(bottom_nav, 0, 0, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(divider, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);

    const int centers[4] = {38, 104, 200, 266};
    for(int i = 0; i < 4; i++) {
        lv_obj_t * label =
            xhs_label(bottom_nav, nav_texts[i], XHS_FT_12, XHS_MUTED);
        lv_obj_set_pos(label, centers[i] - 20, 11);
        lv_obj_set_size(label, 40, 17);
        lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
        xhs_clickable(label, NULL);
        lv_obj_add_event_cb(label, xhs_nav_event_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        nav_labels[i] = label;
    }

    lv_obj_t * dot = xhs_box(bottom_nav, 220, 9, 6, 6);
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(dot, lv_color_hex(XHS_RED), 0);
    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);

    lv_obj_t * publish = xhs_pill(bottom_nav, 131, 9, 42, 28, XHS_RED, "",
                                  XHS_FT_12, XHS_WHITE, 14);
    lv_obj_set_style_shadow_color(publish, lv_color_hex(XHS_RED), 0);
    lv_obj_set_style_shadow_width(publish, 8, 0);
    lv_obj_set_style_shadow_opa(publish, 55, 0);
    xhs_clickable(publish, "publish_button");
    lv_obj_set_ext_click_area(publish, 4);
    lv_obj_add_event_cb(publish, xhs_publish_event_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t * plus = xhs_image(publish, XHS_ICON_PLUS, 0, 0);
    lv_obj_center(plus);

    lv_obj_t * home = xhs_box(bottom_nav, 102, 38, 100, 4);
    lv_obj_set_style_radius(home, 2, 0);
    lv_obj_set_style_bg_color(home, lv_color_hex(0x111113), 0);
    lv_obj_set_style_bg_opa(home, 60, 0);
}

void xhs_page_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    lv_obj_set_scrollable(screen, false);
    lv_obj_set_style_pad_all(screen, 0, 0);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0xF6F2EC), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_hex(0xEDE7F1), 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    lv_obj_t * blob = lv_obj_create(screen);
    lv_obj_set_pos(blob, -190, -230);
    lv_obj_set_size(blob, 520, 520);
    lv_obj_set_style_radius(blob, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(blob, lv_color_hex(XHS_RED), 0);
    lv_obj_set_style_bg_opa(blob, 18, 0);
    lv_obj_set_style_border_width(blob, 0, 0);
    lv_obj_set_style_pad_all(blob, 0, 0);
    lv_obj_set_scrollable(blob, false);
    lv_obj_set_clickable(blob, false);

    blob = lv_obj_create(screen);
    lv_obj_set_pos(blob, 560, 350);
    lv_obj_set_size(blob, 380, 380);
    lv_obj_set_style_radius(blob, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(blob, lv_color_hex(0xFFD9A8), 0);
    lv_obj_set_style_bg_opa(blob, 55, 0);
    lv_obj_set_style_border_width(blob, 0, 0);
    lv_obj_set_style_pad_all(blob, 0, 0);
    lv_obj_set_scrollable(blob, false);
    lv_obj_set_clickable(blob, false);

    lv_obj_t * ring = lv_obj_create(screen);
    lv_obj_set_pos(ring, 610, -80);
    lv_obj_set_size(ring, 250, 250);
    lv_obj_set_style_radius(ring, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(ring, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ring, 1, 0);
    lv_obj_set_style_border_color(ring, lv_color_hex(0xE4D8CE), 0);
    lv_obj_set_style_border_opa(ring, 160, 0);
    lv_obj_set_style_pad_all(ring, 0, 0);
    lv_obj_set_scrollable(ring, false);
    lv_obj_set_clickable(ring, false);

    lv_obj_t * phone = lv_obj_create(screen);
    lv_obj_set_pos(phone, 238, 8);
    lv_obj_set_size(phone, 324, 584);
    lv_obj_set_style_radius(phone, 46, 0);
    lv_obj_set_style_bg_color(phone, lv_color_hex(0x17171A), 0);
    lv_obj_set_style_bg_opa(phone, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(phone, 1, 0);
    lv_obj_set_style_border_color(phone, lv_color_hex(0x3C3C42), 0);
    lv_obj_set_style_pad_all(phone, 0, 0);
    lv_obj_set_style_shadow_color(phone, lv_color_hex(0x2B2320), 0);
    lv_obj_set_style_shadow_width(phone, 30, 0);
    lv_obj_set_style_shadow_opa(phone, 64, 0);
    lv_obj_set_style_shadow_ofs_y(phone, 14, 0);
    lv_obj_set_style_shadow_spread(phone, 2, 0);
    lv_obj_set_scrollable(phone, false);
    lv_obj_set_clickable(phone, false);

    lv_obj_t * button;
    button = lv_obj_create(screen);
    lv_obj_set_pos(button, 234, 154);
    lv_obj_set_size(button, 4, 26);
    lv_obj_set_style_radius(button, 2, 0);
    lv_obj_set_style_bg_color(button, lv_color_hex(0x2C2C31), 0);
    lv_obj_set_style_bg_opa(button, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(button, 0, 0);
    lv_obj_set_scrollable(button, false);
    lv_obj_set_clickable(button, false);

    button = lv_obj_create(screen);
    lv_obj_set_pos(button, 234, 192);
    lv_obj_set_size(button, 4, 44);
    lv_obj_set_style_radius(button, 2, 0);
    lv_obj_set_style_bg_color(button, lv_color_hex(0x2C2C31), 0);
    lv_obj_set_style_bg_opa(button, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(button, 0, 0);
    lv_obj_set_scrollable(button, false);
    lv_obj_set_clickable(button, false);

    button = lv_obj_create(screen);
    lv_obj_set_pos(button, 562, 170);
    lv_obj_set_size(button, 4, 60);
    lv_obj_set_style_radius(button, 2, 0);
    lv_obj_set_style_bg_color(button, lv_color_hex(0x2C2C31), 0);
    lv_obj_set_style_bg_opa(button, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(button, 0, 0);
    lv_obj_set_scrollable(button, false);
    lv_obj_set_clickable(button, false);

    lv_obj_t * panel = lv_obj_create(phone);
    lv_obj_set_pos(panel, 10, 10);
    lv_obj_set_size(panel, XHS_SCREEN_W, XHS_SCREEN_H);
    lv_obj_set_style_radius(panel, 38, 0);
    lv_obj_set_style_clip_corner(panel, true, 0);
    lv_obj_set_style_bg_color(panel, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(panel, 0, 0);
    lv_obj_set_style_pad_all(panel, 0, 0);
    lv_obj_set_scrollable(panel, false);
    lv_obj_set_clickable(panel, false);

    tab_host = xhs_box(panel, 0, XHS_STATUS_H, XHS_SCREEN_W, XHS_TAB_HOST_H);
    overlay_host = xhs_box(panel, 0, XHS_STATUS_H, XHS_SCREEN_W, XHS_OVERLAY_H);
    xhs_set_hidden(overlay_host, true);

    xhs_build_status_bar(panel);
    xhs_bottom_nav(panel);

    root_pages[0] = xhs_home_create(tab_host);
    root_pages[1] = xhs_market_create(tab_host);
    root_pages[2] = xhs_messages_create(tab_host);
    root_pages[3] = xhs_profile_create(tab_host);

    lv_obj_t * notch = xhs_box(panel, 115, 7, 74, 20);
    lv_obj_set_style_radius(notch, 10, 0);
    lv_obj_set_style_bg_color(notch, lv_color_hex(0x0B0B0D), 0);
    lv_obj_set_style_bg_opa(notch, LV_OPA_COVER, 0);
    lv_obj_t * camera = xhs_box(panel, 177, 15, 5, 5);
    lv_obj_set_style_radius(camera, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(camera, lv_color_hex(0x223040), 0);
    lv_obj_set_style_bg_opa(camera, LV_OPA_COVER, 0);

    lv_obj_update_layout(panel);
    xhs_show_root(0);

    printf("[xhs] page ready notes=%d\n", XHS_NOTE_COUNT);
}

#endif
