
#include "app.h"
#include "xhs_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "xhs_assets.h"

#include <stdio.h>

const lv_font_t * xhs_font(xhs_font_id_t id)
{
    switch(id) {
        case XHS_FT_11:
            return &xhs_font_11;
        case XHS_FT_12:
            return &xhs_font_12;
        case XHS_FT_12B:
            return &xhs_font_12b;
        case XHS_FT_13:
            return &xhs_font_13;
        case XHS_FT_14:
            return &xhs_font_14;
        case XHS_FT_14B:
        default:
            return &xhs_font_14b;
    }
}

const lv_image_dsc_t * xhs_icon(xhs_icon_id_t id)
{
    switch(id) {
        case XHS_ICON_SEARCH:
            return &xhs_icon_search;
        case XHS_ICON_HEART_OUTLINE:
            return &xhs_icon_heart_outline;
        case XHS_ICON_HEART_FILLED:
            return &xhs_icon_heart_filled;
        case XHS_ICON_CHEVRON:
            return &xhs_icon_chevron_down;
        case XHS_ICON_PLUS:
            return &xhs_icon_plus;
        case XHS_ICON_PLAY:
            return &xhs_icon_play_badge;
        case XHS_ICON_BACK:
            return &xhs_icon_back;
        case XHS_ICON_MORE:
            return &xhs_icon_more;
        case XHS_ICON_COMMENT:
            return &xhs_icon_comment;
        case XHS_ICON_STAR:
            return &xhs_icon_star;
        case XHS_ICON_STAR_FILLED:
            return &xhs_icon_star_filled;
        case XHS_ICON_LOCATION:
            return &xhs_icon_location;
        case XHS_ICON_CLOSE:
            return &xhs_icon_close;
        case XHS_ICON_PLANE:
            return &xhs_icon_plane;
        case XHS_ICON_SIGNAL:
            return &xhs_icon_signal;
        case XHS_ICON_WIFI:
            return &xhs_icon_wifi;
        case XHS_ICON_BATTERY:
            return &xhs_icon_battery;
        case XHS_ICON_CHECK:
            return &xhs_icon_check;
        default:
            return &xhs_icon_more;
    }
}

const lv_image_dsc_t * xhs_cover(int index)
{
    static const lv_image_dsc_t * const covers[XHS_NOTE_COUNT] = {
        &xhs_cover_0, &xhs_cover_2, &xhs_cover_4,
        &xhs_cover_1, &xhs_cover_3, &xhs_cover_5,
    };
    if(index < 0 || index >= XHS_NOTE_COUNT) index = 0;
    return covers[index];
}

int xhs_cover_height(int index)
{
    return (int)xhs_cover(index)->header.h;
}

xhs_note_t xhs_notes[XHS_NOTE_COUNT] = {
    {
        .title = XHS_TXT_NOTE_0_TITLE,
        .author = XHS_TXT_NOTE_0_AUTHOR,
        .avatar = XHS_TXT_NOTE_0_AVATAR,
        .body = XHS_TXT_NOTE_0_BODY,
        .tag = XHS_TXT_NOTE_0_TAG,
        .location = XHS_TXT_NOTE_0_LOCATION,
        .distance = XHS_TXT_NEARBY_0,
        .cover_index = 0,
        .avatar_color = 0xF0B49C,
        .likes = 1950,
        .collects = 312,
        .following = true,
    },
    {
        .title = XHS_TXT_NOTE_1_TITLE,
        .author = XHS_TXT_NOTE_1_AUTHOR,
        .avatar = XHS_TXT_NOTE_1_AVATAR,
        .body = XHS_TXT_NOTE_1_BODY,
        .tag = XHS_TXT_NOTE_1_TAG,
        .location = XHS_TXT_NOTE_1_LOCATION,
        .distance = XHS_TXT_NEARBY_1,
        .cover_index = 1,
        .avatar_color = 0xF2C96C,
        .likes = 866,
        .collects = 188,
        .collected = true,
        .following = true,
    },
    {
        .title = XHS_TXT_NOTE_2_TITLE,
        .author = XHS_TXT_NOTE_2_AUTHOR,
        .avatar = XHS_TXT_NOTE_2_AVATAR,
        .body = XHS_TXT_NOTE_2_BODY,
        .tag = XHS_TXT_NOTE_2_TAG,
        .location = XHS_TXT_NOTE_2_LOCATION,
        .distance = XHS_TXT_NEARBY_2,
        .cover_index = 2,
        .avatar_color = 0xE8A87C,
        .likes = 642,
        .collects = 421,
        .collected = true,
        .following = true,
    },
    {
        .title = XHS_TXT_NOTE_3_TITLE,
        .author = XHS_TXT_NOTE_3_AUTHOR,
        .avatar = XHS_TXT_NOTE_3_AVATAR,
        .body = XHS_TXT_NOTE_3_BODY,
        .tag = XHS_TXT_NOTE_3_TAG,
        .location = XHS_TXT_NOTE_3_LOCATION,
        .distance = XHS_TXT_NEARBY_3,
        .cover_index = 3,
        .avatar_color = 0x9DC5AD,
        .likes = 3348,
        .collects = 702,
    },
    {
        .title = XHS_TXT_NOTE_4_TITLE,
        .author = XHS_TXT_NOTE_4_AUTHOR,
        .avatar = XHS_TXT_NOTE_4_AVATAR,
        .body = XHS_TXT_NOTE_4_BODY,
        .tag = XHS_TXT_NOTE_4_TAG,
        .location = XHS_TXT_NOTE_4_LOCATION,
        .distance = XHS_TXT_NEARBY_4,
        .cover_index = 4,
        .avatar_color = 0xAEB9E8,
        .likes = 1203,
        .collects = 266,
    },
    {
        .title = XHS_TXT_NOTE_5_TITLE,
        .author = XHS_TXT_NOTE_5_AUTHOR,
        .avatar = XHS_TXT_NOTE_5_AVATAR,
        .body = XHS_TXT_NOTE_5_BODY,
        .tag = XHS_TXT_NOTE_5_TAG,
        .location = XHS_TXT_NOTE_5_LOCATION,
        .distance = XHS_TXT_NEARBY_5,
        .cover_index = 5,
        .avatar_color = 0xD9A8C7,
        .likes = 987,
        .collects = 534,
        .following = true,
    },
};

lv_obj_t * xhs_box(lv_obj_t * parent, int x, int y, int w, int h)
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

lv_obj_t * xhs_label(lv_obj_t * parent, const char * text, xhs_font_id_t font,
                     uint32_t color)
{
    lv_obj_t * label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, xhs_font(font), 0);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    app_obj_set_scrollable(label, false);
    return label;
}

lv_obj_t * xhs_label_at(lv_obj_t * parent, const char * text,
                        xhs_font_id_t font, uint32_t color, int x, int y, int w,
                        int h)
{
    lv_obj_t * label = xhs_label(parent, text, font, color);
    lv_obj_set_pos(label, x, y);
    lv_obj_set_size(label, w, h);
    return label;
}

lv_obj_t * xhs_image(lv_obj_t * parent, xhs_icon_id_t icon, int x, int y)
{
    lv_obj_t * image = lv_image_create(parent);
    lv_image_set_src(image, xhs_icon(icon));
    lv_obj_set_pos(image, x, y);
    app_obj_set_scrollable(image, false);
    app_obj_set_clickable(image, false);
    return image;
}

lv_obj_t * xhs_cover_thumb(lv_obj_t * parent, int cover_index, int x, int y,
                           int w, int h, int radius)
{
    lv_obj_t * thumb = xhs_box(parent, x, y, w, h);
    lv_obj_set_style_radius(thumb, radius, 0);
    lv_obj_set_style_clip_corner(thumb, true, 0);
    lv_obj_set_style_bg_color(thumb, lv_color_hex(0xECECEE), 0);
    lv_obj_set_style_bg_opa(thumb, LV_OPA_COVER, 0);

    const lv_image_dsc_t * src = xhs_cover(cover_index);
    int src_w = (int)src->header.w;
    int src_h = (int)src->header.h;
    int scale_x = (w * 100 + src_w - 1) / src_w;
    int scale_y = (h * 100 + src_h - 1) / src_h;
    int scale = scale_x > scale_y ? scale_x : scale_y;

    lv_obj_t * image = lv_image_create(thumb);
    lv_image_set_src(image, src);
    lv_image_set_scale(image, (uint32_t)(LV_SCALE_NONE * scale / 100));
    lv_obj_set_pos(image, (w - src_w) / 2, (h - src_h) / 2);
    app_obj_set_scrollable(image, false);
    app_obj_set_clickable(image, false);
    return thumb;
}

lv_obj_t * xhs_cover_scaled(lv_obj_t * parent, int cover_index, int scale_pct,
                            int center_x, int top_y)
{
    const lv_image_dsc_t * src = xhs_cover(cover_index);
    int src_w = (int)src->header.w;
    int src_h = (int)src->header.h;
    int drawn_h = src_h * scale_pct / 100;

    lv_obj_t * image = lv_image_create(parent);
    lv_image_set_src(image, src);
    lv_image_set_scale(image, (uint32_t)(LV_SCALE_NONE * scale_pct / 100));
    lv_obj_set_pos(image, center_x - src_w / 2, top_y + (drawn_h - src_h) / 2);
    app_obj_set_scrollable(image, false);
    app_obj_set_clickable(image, false);
    return image;
}

lv_obj_t * xhs_avatar(lv_obj_t * parent, int x, int y, int size, uint32_t color,
                      const char * text, xhs_font_id_t font)
{
    lv_obj_t * avatar = xhs_box(parent, x, y, size, size);
    lv_obj_set_style_radius(avatar, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(avatar, lv_color_hex(color), 0);
    lv_obj_set_style_bg_opa(avatar, LV_OPA_COVER, 0);
    lv_obj_t * label = xhs_label(avatar, text, font, XHS_WHITE);
    lv_obj_center(label);
    return avatar;
}

lv_obj_t * xhs_pill(lv_obj_t * parent, int x, int y, int w, int h, uint32_t bg,
                    const char * text, xhs_font_id_t font, uint32_t fg,
                    int radius)
{
    lv_obj_t * pill = xhs_box(parent, x, y, w, h);
    lv_obj_set_style_radius(pill, radius, 0);
    lv_obj_set_style_bg_color(pill, lv_color_hex(bg), 0);
    lv_obj_set_style_bg_opa(pill, LV_OPA_COVER, 0);
    lv_obj_t * label = xhs_label(pill, text, font, fg);
    lv_obj_center(label);
    return pill;
}

lv_obj_t * xhs_page(lv_obj_t * parent)
{
    lv_obj_t * page = lv_obj_create(parent);
    lv_obj_set_pos(page, 0, 0);
    lv_obj_set_size(page, XHS_SCREEN_W, XHS_OVERLAY_H);
    lv_obj_set_style_bg_color(page, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(page, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(page, 0, 0);
    lv_obj_set_style_radius(page, 0, 0);
    lv_obj_set_style_pad_all(page, 0, 0);
    app_obj_set_scrollable(page, false);
    app_obj_set_clickable(page, true);
    app_obj_set_hidden(page, true);
    return page;
}

lv_obj_t * xhs_root_page(lv_obj_t * parent)
{
    lv_obj_t * page = lv_obj_create(parent);
    lv_obj_set_pos(page, 0, 0);
    lv_obj_set_size(page, XHS_SCREEN_W, XHS_TAB_HOST_H);
    lv_obj_set_style_bg_color(page, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(page, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(page, 0, 0);
    lv_obj_set_style_radius(page, 0, 0);
    lv_obj_set_style_pad_all(page, 0, 0);
    app_obj_set_scrollable(page, false);
    app_obj_set_clickable(page, true);
    return page;
}

lv_obj_t * xhs_scroll(lv_obj_t * parent, int x, int y, int w, int h)
{
    lv_obj_t * area = lv_obj_create(parent);
    lv_obj_set_pos(area, x, y);
    lv_obj_set_size(area, w, h);
    lv_obj_set_style_bg_opa(area, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(area, 0, 0);
    lv_obj_set_style_radius(area, 0, 0);
    lv_obj_set_style_pad_all(area, 0, 0);
    lv_obj_set_scroll_dir(area, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(area, LV_SCROLLBAR_MODE_OFF);
    lv_obj_set_scroll_snap_y(area, LV_SCROLL_SNAP_NONE);
    return area;
}

void xhs_clickable(lv_obj_t * obj, const char * name)
{
    app_obj_set_clickable(obj, true);
    if(name != NULL) {
        lv_obj_set_name(obj, name);
    }
}

void xhs_set_hidden(lv_obj_t * obj, bool hidden)
{
    app_obj_set_hidden(obj, hidden);
}

void xhs_back_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    printf("[xhs] back\n");
    xhs_close_overlay();
}

void xhs_home_sync_likes(void)
{
    for(int i = 0; i < XHS_NOTE_COUNT; i++) {
        xhs_note_t * note = &xhs_notes[i];
        if(note->like_icon != NULL) {
            lv_image_set_src(note->like_icon,
                             note->liked ? xhs_icon(XHS_ICON_HEART_FILLED)
                                         : xhs_icon(XHS_ICON_HEART_OUTLINE));
        }
        if(note->like_label != NULL) {
            char buffer[12];
            snprintf(buffer, sizeof(buffer), "%d", note->likes);
            lv_label_set_text(note->like_label, buffer);
        }
    }
}

#endif
