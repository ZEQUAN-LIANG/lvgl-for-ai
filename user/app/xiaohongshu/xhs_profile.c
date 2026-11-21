#include "xhs_ui.h"

#include <stdint.h>
#include <stdio.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

static const char * const profile_tabs[3] = {
    XHS_TXT_PROFILE_NOTES,
    XHS_TXT_PROFILE_FAV,
    XHS_TXT_PROFILE_LIKED,
};
static const char * const stat_labels[3] = {
    XHS_TXT_STAT_FOLLOW,
    XHS_TXT_STAT_FANS,
    XHS_TXT_STAT_LIKES,
};
static const char * const stat_values[3] = {
    XHS_TXT_STAT_FOLLOW_N,
    XHS_TXT_STAT_FANS_N,
    XHS_TXT_STAT_LIKES_N,
};
static const int stat_centers[3] = {58, 152, 246};

static lv_obj_t * profile_grid;
static lv_obj_t * profile_tab_labels[3];
static lv_obj_t * profile_underline;
static int active_profile_tab = 0;

static const int * profile_set(int tab)
{
    static const int notes[6] = {0, 1, 2, 3, 4, 5};
    static const int favorites[3] = {1, 2, 5};
    static const int liked[3] = {0, 3, 4};
    return tab == 1 ? favorites : tab == 2 ? liked : notes;
}

static int profile_set_size(int tab)
{
    return tab == 0 ? 6 : 3;
}

static void xhs_profile_note_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    xhs_note_open((int)(intptr_t)lv_event_get_user_data(event));
}

static void xhs_profile_grid_build(void)
{
    lv_obj_clean(profile_grid);
    const int * set = profile_set(active_profile_tab);
    int count = profile_set_size(active_profile_tab);
    for(int i = 0; i < count; i++) {
        int note_index = set[i];
        int column = i % 3;
        int row = i / 3;
        lv_obj_t * tile = xhs_cover_thumb(
            profile_grid, note_index, 8 + column * 98, row * 112, 94, 104, 8);
        xhs_clickable(tile, NULL);
        lv_obj_add_event_cb(tile, xhs_profile_note_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)note_index);
    }
}

static void xhs_profile_tab_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    active_profile_tab = index;
    for(int i = 0; i < 3; i++) {
        lv_obj_set_style_text_font(
            profile_tab_labels[i],
            xhs_font(i == index ? XHS_FT_12B : XHS_FT_12), 0);
        lv_obj_set_style_text_color(
            profile_tab_labels[i],
            lv_color_hex(i == index ? XHS_TEXT : XHS_MUTED), 0);
    }
    lv_obj_align_to(profile_underline, profile_tab_labels[index],
                    LV_ALIGN_OUT_BOTTOM_MID, 0, 1);
    xhs_profile_grid_build();
    printf("[xhs] profile tab=%s\n", profile_tabs[index]);
}

static void xhs_profile_more_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] profile settings clicked\n");
    }
}

static void xhs_profile_edit_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] profile edit clicked\n");
    }
}

static void xhs_profile_stat_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    printf("[xhs] profile stat=%s\n", stat_labels[index]);
}

lv_obj_t * xhs_profile_create(lv_obj_t * parent)
{
    lv_obj_t * page = xhs_root_page(parent);

    lv_obj_t * header = xhs_box(page, 0, 0, XHS_SCREEN_W, 190);
    lv_obj_set_style_bg_color(header, lv_color_hex(0xFFF0F1), 0);
    lv_obj_set_style_bg_grad_color(header, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_grad_dir(header, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_opa(header, LV_OPA_COVER, 0);

    lv_obj_t * more = xhs_image(header, XHS_ICON_MORE, 272, 18);
    xhs_clickable(more, "profile_settings");
    lv_obj_set_ext_click_area(more, 8);
    lv_obj_add_event_cb(more, xhs_profile_more_cb, LV_EVENT_CLICKED, NULL);

    xhs_avatar(header, 16, 36, 60, XHS_RED, "小", XHS_FT_14B);

    xhs_label_at(header, XHS_TXT_PROFILE_NAME, XHS_FT_14B, XHS_TEXT, 90, 40,
                 160, 22);
    xhs_label_at(header, XHS_TXT_PROFILE_ID, XHS_FT_11, XHS_MUTED, 90, 66, 170,
                 16);

    lv_obj_t * edit = xhs_pill(header, 214, 38, 74, 24, XHS_WHITE,
                               XHS_TXT_PROFILE_EDIT, XHS_FT_11, XHS_MUTED, 12);
    lv_obj_set_style_border_width(edit, 1, 0);
    lv_obj_set_style_border_color(edit, lv_color_hex(0xE3E3E7), 0);
    xhs_clickable(edit, "profile_edit");
    lv_obj_add_event_cb(edit, xhs_profile_edit_cb, LV_EVENT_CLICKED, NULL);

    xhs_label_at(header, XHS_TXT_PROFILE_BIO, XHS_FT_12, XHS_TEXT, 16, 108, 272,
                 18);
    xhs_image(header, XHS_ICON_LOCATION, 16, 130);
    xhs_label_at(header, XHS_TXT_PROFILE_LOCATION, XHS_FT_11, XHS_MUTED, 32,
                 131, 120, 16);

    for(int i = 0; i < 3; i++) {
        lv_obj_t * value =
            xhs_label_at(header, stat_values[i], XHS_FT_12B, XHS_TEXT,
                         stat_centers[i] - 40, 152, 80, 18);
        lv_obj_set_style_text_align(value, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_t * label =
            xhs_label_at(header, stat_labels[i], XHS_FT_11, XHS_MUTED,
                         stat_centers[i] - 40, 171, 80, 16);
        lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);

        lv_obj_t * hit = xhs_box(header, stat_centers[i] - 40, 148, 80, 42);
        xhs_clickable(hit, NULL);
        lv_obj_add_event_cb(hit, xhs_profile_stat_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        lv_obj_move_to_index(hit, -1);
    }

    lv_obj_t * divider = xhs_box(page, 0, 190, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(divider, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);

    for(int i = 0; i < 3; i++) {
        lv_obj_t * tab = xhs_label_at(page, profile_tabs[i], XHS_FT_12,
                                      XHS_MUTED, 10 + i * 98, 199, 80, 18);
        lv_obj_set_style_text_align(tab, LV_TEXT_ALIGN_CENTER, 0);
        xhs_clickable(tab, NULL);
        lv_obj_add_event_cb(tab, xhs_profile_tab_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        profile_tab_labels[i] = tab;
    }

    profile_underline = xhs_box(page, 0, 0, 22, 3);
    lv_obj_set_style_radius(profile_underline, 2, 0);
    lv_obj_set_style_bg_color(profile_underline, lv_color_hex(XHS_RED), 0);
    lv_obj_set_style_bg_opa(profile_underline, LV_OPA_COVER, 0);

    lv_obj_t * tab_line = xhs_box(page, 0, 223, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(tab_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(tab_line, LV_OPA_COVER, 0);

    profile_grid = xhs_scroll(page, 0, 228, XHS_SCREEN_W, 266);
    lv_obj_set_name(profile_grid, "profile_grid");
    xhs_profile_grid_build();

    lv_obj_update_layout(page);
    lv_obj_align_to(profile_underline, profile_tab_labels[active_profile_tab],
                    LV_ALIGN_OUT_BOTTOM_MID, 0, 1);
    return page;
}

#endif
