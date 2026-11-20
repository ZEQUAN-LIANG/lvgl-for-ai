
#include "xhs_ui.h"

#include <stdint.h>
#include <stdio.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

static const char * const publish_modes[3] = {
    XHS_TXT_PUBLISH_PHOTO,
    XHS_TXT_PUBLISH_VIDEO,
    XHS_TXT_PUBLISH_LIVE,
};

static lv_obj_t * publish_overlay;
static lv_obj_t * publish_mode_labels[3];
static lv_obj_t * publish_underline;
static lv_obj_t * publish_visibility_label;
static lv_obj_t * publish_plus_circle;
static lv_obj_t * publish_plus_label;
static lv_obj_t * publish_preview;
static int publish_mode = 0;
static bool publish_public = true;

static void xhs_publish_done_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    printf("[xhs] publish done\n");
    xhs_show_root(0);
}

static void xhs_publish_submit_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    printf("[xhs] publish submitted mode=%d public=%d\n", publish_mode,
           publish_public ? 1 : 0);

    lv_obj_t * page = publish_overlay;
    lv_obj_clean(page);

    lv_obj_t * title = xhs_label_at(page, XHS_TXT_PUBLISH_SUCCESS, XHS_FT_14B,
                                    XHS_TEXT, 0, 168, XHS_SCREEN_W, 24);
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_t * sub = xhs_label_at(page, XHS_TXT_PUBLISH_SUCCESS_SUB, XHS_FT_12,
                                  XHS_MUTED, 0, 200, XHS_SCREEN_W, 20);
    lv_obj_set_style_text_align(sub, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t * ring = xhs_box(page, 120, 68, 64, 64);
    lv_obj_set_style_radius(ring, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(ring, lv_color_hex(0xEAF7EF), 0);
    lv_obj_set_style_bg_opa(ring, LV_OPA_COVER, 0);
    lv_obj_t * mark = xhs_image(ring, XHS_ICON_CHECK, 0, 0);
    lv_obj_center(mark);

    lv_obj_t * done = xhs_pill(page, 72, 252, 160, 40, XHS_RED,
                               XHS_TXT_PUBLISH_DONE, XHS_FT_14B, XHS_WHITE, 20);
    xhs_clickable(done, "publish_done");
    lv_obj_add_event_cb(done, xhs_publish_done_cb, LV_EVENT_CLICKED, NULL);
}

static void xhs_publish_add_image_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    if(publish_plus_circle != NULL) {
        xhs_set_hidden(publish_plus_circle, true);
    }
    if(publish_plus_label != NULL) {
        xhs_set_hidden(publish_plus_label, true);
    }
    if(publish_preview != NULL) {
        xhs_set_hidden(publish_preview, false);
    }
    printf("[xhs] publish image added\n");
}

static void xhs_publish_mode_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    publish_mode = index;
    for(int i = 0; i < 3; i++) {
        lv_obj_set_style_text_font(
            publish_mode_labels[i],
            xhs_font(i == index ? XHS_FT_12B : XHS_FT_12), 0);
        lv_obj_set_style_text_color(
            publish_mode_labels[i],
            lv_color_hex(i == index ? XHS_TEXT : XHS_MUTED), 0);
    }
    lv_obj_align_to(publish_underline, publish_mode_labels[index],
                    LV_ALIGN_OUT_BOTTOM_MID, 0, 1);
    printf("[xhs] publish mode=%s\n", publish_modes[index]);
}

static void xhs_publish_draft_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    lv_obj_t * label = lv_event_get_target_obj(event);
    lv_label_set_text(label, XHS_TXT_PUBLISH_SAVED);
    printf("[xhs] publish draft saved\n");
}

static void xhs_publish_row_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    const char * name = (const char *)lv_event_get_user_data(event);
    printf("[xhs] publish option=%s\n", name != NULL ? name : "row");
}

static void xhs_publish_field_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    const char * name = (const char *)lv_event_get_user_data(event);
    printf("[xhs] publish field=%s\n", name != NULL ? name : "field");
}

static void xhs_publish_visibility_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    publish_public = !publish_public;
    if(publish_visibility_label != NULL) {
        lv_label_set_text(publish_visibility_label,
                          publish_public ? XHS_TXT_PUBLISH_PUBLIC
                                         : XHS_TXT_PUBLISH_PRIVATE);
    }
    printf("[xhs] publish visible=%d\n", publish_public ? 1 : 0);
}

static void xhs_publish_option_row(lv_obj_t * page, int y, xhs_icon_id_t icon,
                                   const char * text, const char * name,
                                   lv_event_cb_t cb)
{
    lv_obj_t * row = xhs_box(page, 0, y, XHS_SCREEN_W, 42);
    xhs_clickable(row, name);
    lv_obj_add_event_cb(row, cb, LV_EVENT_CLICKED, (void *)name);

    if(icon == XHS_ICON_LOCATION) {
        xhs_image(row, icon, 16, 13);
    }
    else {
        lv_obj_t * hash =
            xhs_label_at(row, "#", XHS_FT_12B, XHS_RED, 16, 11, 16, 18);
        (void)hash;
    }
    xhs_label_at(row, text, XHS_FT_12, XHS_TEXT, 38, 11, 170, 18);
    xhs_image(row, XHS_ICON_CHEVRON, 276, 15);

    lv_obj_t * line = xhs_box(row, 16, 41, 272, 1);
    lv_obj_set_style_bg_color(line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);
}

static void xhs_publish_build(lv_obj_t * page)
{
    lv_obj_t * close = xhs_image(page, XHS_ICON_CLOSE, 12, 14);
    xhs_clickable(close, "publish_close");
    lv_obj_set_ext_click_area(close, 8);
    lv_obj_add_event_cb(close, xhs_back_event_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * title = xhs_label_at(page, XHS_TXT_PUBLISH_TITLE, XHS_FT_14B,
                                    XHS_TEXT, 0, 13, XHS_SCREEN_W, 18);
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t * draft = xhs_label_at(page, XHS_TXT_PUBLISH_DRAFT, XHS_FT_11,
                                    XHS_MUTED, 238, 14, 54, 16);
    lv_obj_set_style_text_align(draft, LV_TEXT_ALIGN_RIGHT, 0);
    xhs_clickable(draft, "publish_draft");
    lv_obj_add_event_cb(draft, xhs_publish_draft_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * top_line = xhs_box(page, 0, 43, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(top_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(top_line, LV_OPA_COVER, 0);

    for(int i = 0; i < 3; i++) {
        lv_obj_t * tab = xhs_label_at(page, publish_modes[i], XHS_FT_12,
                                      XHS_MUTED, 28 + i * 86, 52, 64, 18);
        lv_obj_set_style_text_align(tab, LV_TEXT_ALIGN_CENTER, 0);
        xhs_clickable(tab, NULL);
        lv_obj_add_event_cb(tab, xhs_publish_mode_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        publish_mode_labels[i] = tab;
    }

    publish_underline = xhs_box(page, 0, 0, 24, 3);
    lv_obj_set_style_radius(publish_underline, 2, 0);
    lv_obj_set_style_bg_color(publish_underline, lv_color_hex(XHS_RED), 0);
    lv_obj_set_style_bg_opa(publish_underline, LV_OPA_COVER, 0);

    lv_obj_t * mode_line = xhs_box(page, 0, 80, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(mode_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(mode_line, LV_OPA_COVER, 0);

    for(int i = 0; i < 3; i++) {
        lv_obj_t * tile = xhs_box(page, 12 + i * 96, 92, 88, 88);
        lv_obj_set_style_radius(tile, 8, 0);
        lv_obj_set_style_bg_color(tile, lv_color_hex(XHS_SOFT), 0);
        lv_obj_set_style_bg_opa(tile, LV_OPA_COVER, 0);
    }

    lv_obj_t * add_tile = xhs_box(page, 12, 92, 88, 88);
    xhs_clickable(add_tile, "publish_add_image");
    lv_obj_add_event_cb(add_tile, xhs_publish_add_image_cb, LV_EVENT_CLICKED,
                        NULL);

    publish_preview = xhs_cover_thumb(add_tile, 5, 0, 0, 88, 88, 8);
    xhs_set_hidden(publish_preview, true);

    publish_plus_circle = xhs_pill(add_tile, 30, 28, 28, 28, XHS_RED, "",
                                   XHS_FT_11, XHS_WHITE, 14);
    xhs_image(publish_plus_circle, XHS_ICON_PLUS, 7, 7);
    publish_plus_label = xhs_label_at(add_tile, XHS_TXT_PUBLISH_ADD_IMAGE,
                                      XHS_FT_11, XHS_MUTED, 0, 62, 88, 16);
    lv_obj_set_style_text_align(publish_plus_label, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t * title_field = xhs_box(page, 12, 192, 280, 40);
    lv_obj_set_style_radius(title_field, 8, 0);
    lv_obj_set_style_bg_color(title_field, lv_color_hex(XHS_SOFT), 0);
    lv_obj_set_style_bg_opa(title_field, LV_OPA_COVER, 0);
    xhs_clickable(title_field, "publish_title");
    lv_obj_add_event_cb(title_field, xhs_publish_field_cb, LV_EVENT_CLICKED,
                        (void *)"title");
    xhs_label_at(title_field, XHS_TXT_PUBLISH_TITLE_HINT, XHS_FT_12, XHS_MUTED,
                 12, 11, 250, 18);

    lv_obj_t * body_field = xhs_box(page, 12, 240, 280, 96);
    lv_obj_set_style_radius(body_field, 8, 0);
    lv_obj_set_style_bg_color(body_field, lv_color_hex(XHS_SOFT), 0);
    lv_obj_set_style_bg_opa(body_field, LV_OPA_COVER, 0);
    xhs_clickable(body_field, "publish_body");
    lv_obj_add_event_cb(body_field, xhs_publish_field_cb, LV_EVENT_CLICKED,
                        (void *)"body");
    lv_obj_t * hint = xhs_label_at(body_field, XHS_TXT_PUBLISH_BODY_HINT,
                                   XHS_FT_12, XHS_MUTED, 12, 12, 252, 60);
    lv_label_set_long_mode(hint, LV_LABEL_LONG_MODE_WRAP);

    xhs_publish_option_row(page, 348, XHS_ICON_LOCATION,
                           XHS_TXT_PUBLISH_LOCATION, "location",
                           xhs_publish_row_cb);
    xhs_publish_option_row(page, 390, XHS_ICON_STAR, XHS_TXT_PUBLISH_TAG, "tag",
                           xhs_publish_row_cb);

    lv_obj_t * visibility = xhs_box(page, 0, 432, XHS_SCREEN_W, 42);
    xhs_clickable(visibility, "visibility");
    lv_obj_add_event_cb(visibility, xhs_publish_visibility_cb, LV_EVENT_CLICKED,
                        NULL);
    xhs_label_at(visibility, XHS_TXT_PUBLISH_VISIBLE, XHS_FT_12, XHS_TEXT, 16,
                 11, 120, 18);
    publish_visibility_label =
        xhs_label_at(visibility, XHS_TXT_PUBLISH_PUBLIC, XHS_FT_12, XHS_MUTED,
                     176, 11, 90, 18);
    lv_obj_set_style_text_align(publish_visibility_label, LV_TEXT_ALIGN_RIGHT,
                                0);
    xhs_image(visibility, XHS_ICON_CHEVRON, 276, 15);
    lv_obj_t * visibility_line = xhs_box(visibility, 16, 41, 272, 1);
    lv_obj_set_style_bg_color(visibility_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(visibility_line, LV_OPA_COVER, 0);

    lv_obj_t * bar = xhs_box(page, 0, 488, XHS_SCREEN_W, 52);
    lv_obj_set_style_bg_color(bar, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_t * bar_line = xhs_box(bar, 0, 0, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(bar_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(bar_line, LV_OPA_COVER, 0);

    lv_obj_t * submit =
        xhs_pill(bar, 16, 6, 272, 40, XHS_RED, XHS_TXT_PUBLISH_SUBMIT,
                 XHS_FT_12B, XHS_WHITE, 20);
    xhs_clickable(submit, "publish_submit");
    lv_obj_add_event_cb(submit, xhs_publish_submit_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_update_layout(page);
    lv_obj_align_to(publish_underline, publish_mode_labels[publish_mode],
                    LV_ALIGN_OUT_BOTTOM_MID, 0, 1);
}

void xhs_publish_open(void)
{
    if(publish_overlay == NULL) {
        publish_overlay = xhs_page(xhs_overlay_host());
    }
    lv_obj_clean(publish_overlay);
    publish_mode = 0;
    publish_public = true;
    publish_plus_circle = NULL;
    publish_plus_label = NULL;
    publish_preview = NULL;
    publish_visibility_label = NULL;
    xhs_publish_build(publish_overlay);
    xhs_open_overlay(publish_overlay);
    printf("[xhs] publish open\n");
}

#endif
