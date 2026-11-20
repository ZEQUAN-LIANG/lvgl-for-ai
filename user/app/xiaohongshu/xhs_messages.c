
#include "xhs_ui.h"

#include <stdint.h>
#include <stdio.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

typedef struct {
    const char * name;
    const char * preview;
    const char * time;
    const char * avatar;
    uint32_t color;
} xhs_message_t;

static xhs_message_t messages[4] = {
    {XHS_TXT_MSG_ROW_0_NAME, XHS_TXT_MSG_ROW_0_TEXT, XHS_TXT_MSG_ROW_0_TIME,
     "M", 0xD9A8C7},
    {XHS_TXT_MSG_ROW_1_NAME, XHS_TXT_MSG_ROW_1_TEXT, XHS_TXT_MSG_ROW_1_TIME,
     "厨", 0xE8A87C},
    {XHS_TXT_MSG_ROW_2_NAME, XHS_TXT_MSG_ROW_2_TEXT, XHS_TXT_MSG_ROW_2_TIME,
     "运", 0xAEB9E8},
    {XHS_TXT_MSG_ROW_3_NAME, XHS_TXT_MSG_ROW_3_TEXT, XHS_TXT_MSG_ROW_3_TIME,
     "通", 0xFF8FA3},
};

static const char * const channel_names[4] = {
    XHS_TXT_MSG_LIKE,
    XHS_TXT_MSG_FOLLOW,
    XHS_TXT_MSG_COMMENT,
    XHS_TXT_MSG_DM,
};

static const char * const channel_items[3] = {
    XHS_TXT_CHANNEL_ITEM_0,
    XHS_TXT_CHANNEL_ITEM_1,
    XHS_TXT_CHANNEL_ITEM_2,
};
static const char * const channel_times[3] = {
    XHS_TXT_CHANNEL_TIME_0,
    XHS_TXT_CHANNEL_TIME_1,
    XHS_TXT_CHANNEL_TIME_2,
};
static const char * const channel_initials[3] = {"赞", "藏", "评"};
static const uint32_t channel_avatar_colors[3] = {
    0xE7A6A0,
    0xF2C96C,
    0x9DC5AD,
};

static lv_obj_t * messages_page;
static lv_obj_t * chat_overlay;
static lv_obj_t * channel_overlay;
static lv_obj_t * chat_messages;
static int open_chat = -1;
static int chat_next_y;

static lv_obj_t * xhs_chat_bubble(lv_obj_t * parent, const char * text,
                                  bool mine, int y, int * advance)
{
    lv_point_t size;
    lv_text_get_size(&size, text, xhs_font(XHS_FT_12), 0, 2, 190,
                     LV_TEXT_FLAG_NONE);
    int width = size.x + 20;
    if(width < 64) width = 64;
    if(width > 210) width = 210;
    int height = size.y + 16;

    lv_obj_t * bubble;
    if(mine) {
        bubble = xhs_box(parent, 288 - width, y, width, height);
    }
    else {
        xhs_avatar(parent, 12, y, 28, messages[open_chat].color,
                   messages[open_chat].avatar, XHS_FT_11);
        bubble = xhs_box(parent, 48, y, width, height);
    }
    lv_obj_set_style_radius(bubble, 10, 0);
    lv_obj_set_style_bg_color(bubble, lv_color_hex(mine ? XHS_RED : 0xF2F2F5),
                              0);
    lv_obj_set_style_bg_opa(bubble, LV_OPA_COVER, 0);

    lv_obj_t * label =
        xhs_label(bubble, text, XHS_FT_12, mine ? XHS_WHITE : XHS_TEXT);
    lv_obj_set_pos(label, 10, 8);
    lv_obj_set_width(label, width - 20);
    lv_label_set_long_mode(label, LV_LABEL_LONG_MODE_WRAP);

    if(advance != NULL) *advance = height + 12;
    return bubble;
}

static void xhs_chat_send_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int advance = 0;
    lv_obj_t * bubble = xhs_chat_bubble(chat_messages, XHS_TXT_CHAT_REPLY, true,
                                        chat_next_y, &advance);
    chat_next_y += advance;
    lv_obj_update_layout(chat_messages);
    lv_obj_scroll_to_view(bubble, LV_ANIM_OFF);
    printf("[xhs] message sent index=%d\n", open_chat);
}

static void xhs_chat_input_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] chat input clicked\n");
    }
}

static void xhs_chat_more_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] chat more clicked\n");
    }
}

static void xhs_chat_build(lv_obj_t * page, int index)
{
    lv_obj_clean(page);
    xhs_message_t * message = &messages[index];

    lv_obj_t * back = xhs_image(page, XHS_ICON_BACK, 12, 13);
    xhs_clickable(back, "chat_back");
    lv_obj_set_ext_click_area(back, 8);
    lv_obj_add_event_cb(back, xhs_back_event_cb, LV_EVENT_CLICKED, NULL);

    xhs_avatar(page, 42, 9, 26, message->color, message->avatar, XHS_FT_11);
    lv_obj_t * name = xhs_label_at(page, message->name, XHS_FT_12B, XHS_TEXT,
                                   76, 13, 150, 18);
    lv_label_set_long_mode(name, LV_LABEL_LONG_MODE_DOTS);

    lv_obj_t * more = xhs_image(page, XHS_ICON_MORE, 272, 18);
    xhs_clickable(more, "chat_more");
    lv_obj_set_ext_click_area(more, 8);
    lv_obj_add_event_cb(more, xhs_chat_more_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * top_line = xhs_box(page, 0, 43, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(top_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(top_line, LV_OPA_COVER, 0);

    chat_messages = xhs_scroll(page, 0, 44, XHS_SCREEN_W, 448);
    lv_obj_set_name(chat_messages, "chat_messages");

    chat_next_y = 12;
    int advance = 0;
    xhs_chat_bubble(chat_messages, XHS_TXT_CHAT_BUBBLE_0, false, chat_next_y,
                    &advance);
    chat_next_y += advance;
    xhs_chat_bubble(chat_messages, XHS_TXT_CHAT_BUBBLE_1, true, chat_next_y,
                    &advance);
    chat_next_y += advance;
    xhs_chat_bubble(chat_messages, XHS_TXT_CHAT_BUBBLE_2, false, chat_next_y,
                    &advance);
    chat_next_y += advance;
    xhs_box(chat_messages, 0, chat_next_y, 1, 1);

    lv_obj_t * bar = xhs_box(page, 0, 492, XHS_SCREEN_W, 48);
    lv_obj_set_style_bg_color(bar, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_t * bar_line = xhs_box(bar, 0, 0, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(bar_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(bar_line, LV_OPA_COVER, 0);

    lv_obj_t * input = xhs_pill(bar, 12, 8, 218, 32, XHS_SOFT,
                                XHS_TXT_CHAT_INPUT, XHS_FT_11, XHS_MUTED, 16);
    xhs_clickable(input, "chat_input");
    lv_obj_add_event_cb(input, xhs_chat_input_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * send = xhs_pill(bar, 240, 8, 52, 32, XHS_RED, XHS_TXT_CHAT_SEND,
                               XHS_FT_12B, XHS_WHITE, 16);
    xhs_clickable(send, "chat_send");
    lv_obj_add_event_cb(send, xhs_chat_send_cb, LV_EVENT_CLICKED, NULL);
}

static void xhs_message_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    if(chat_overlay == NULL) {
        chat_overlay = xhs_page(xhs_overlay_host());
    }
    open_chat = index;
    xhs_chat_build(chat_overlay, index);
    xhs_open_overlay(chat_overlay);
    printf("[xhs] chat open index=%d\n", index);
}

static void xhs_channel_row_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] channel item clicked\n");
    }
}

static void xhs_channel_build(lv_obj_t * page, int index)
{
    lv_obj_clean(page);

    lv_obj_t * back = xhs_image(page, XHS_ICON_BACK, 12, 13);
    xhs_clickable(back, "channel_back");
    lv_obj_set_ext_click_area(back, 8);
    lv_obj_add_event_cb(back, xhs_back_event_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * title = xhs_label_at(page, channel_names[index], XHS_FT_14B,
                                    XHS_TEXT, 0, 13, XHS_SCREEN_W, 18);
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t * top_line = xhs_box(page, 0, 43, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(top_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(top_line, LV_OPA_COVER, 0);

    for(int i = 0; i < 3; i++) {
        int y = 56 + i * 74;
        lv_obj_t * row = xhs_box(page, 0, y, XHS_SCREEN_W, 72);
        xhs_clickable(row, NULL);
        lv_obj_add_event_cb(row, xhs_channel_row_cb, LV_EVENT_CLICKED, NULL);

        xhs_avatar(row, 14, 18, 36, channel_avatar_colors[i],
                   channel_initials[i], XHS_FT_12B);
        lv_obj_t * text = xhs_label_at(row, channel_items[i], XHS_FT_12,
                                       XHS_TEXT, 62, 15, 186, 40);
        lv_label_set_long_mode(text, LV_LABEL_LONG_MODE_WRAP);
        lv_obj_t * time = xhs_label_at(row, channel_times[i], XHS_FT_11,
                                       XHS_META, 256, 16, 38, 16);
        lv_obj_set_style_text_align(time, LV_TEXT_ALIGN_RIGHT, 0);

        lv_obj_t * line = xhs_box(row, 62, 71, 232, 1);
        lv_obj_set_style_bg_color(line, lv_color_hex(XHS_LINE), 0);
        lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);
    }
}

static void xhs_channel_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    if(channel_overlay == NULL) {
        channel_overlay = xhs_page(xhs_overlay_host());
    }
    xhs_channel_build(channel_overlay, index);
    xhs_open_overlay(channel_overlay);
    printf("[xhs] channel open=%s\n", channel_names[index]);
}

static void xhs_channel_entry(lv_obj_t * page, int index)
{
    int x = 8 + index * 72;
    uint32_t bg = index == 0   ? 0xFFE9ED
                  : index == 1 ? 0x4C8DFF
                  : index == 2 ? 0xEAF7EF
                               : 0xEAF2FF;
    lv_obj_t * circle =
        xhs_pill(page, x + 19, 46, 38, 38, bg, "", XHS_FT_11, XHS_TEXT, 19);
    xhs_clickable(circle, NULL);
    lv_obj_add_event_cb(circle, xhs_channel_event_cb, LV_EVENT_CLICKED,
                        (void *)(intptr_t)index);

    if(index == 0) {
        xhs_image(circle, XHS_ICON_HEART_FILLED, 12, 12);
    }
    else if(index == 1) {
        xhs_image(circle, XHS_ICON_PLUS, 12, 12);
    }
    else if(index == 2) {
        xhs_image(circle, XHS_ICON_COMMENT, 11, 11);
    }
    else {
        xhs_image(circle, XHS_ICON_PLANE, 11, 11);
    }

    lv_obj_t * name = xhs_label_at(page, channel_names[index], XHS_FT_11,
                                   XHS_MUTED, x, 88, 76, 16);
    lv_obj_set_style_text_align(name, LV_TEXT_ALIGN_CENTER, 0);

    if(index == 0 || index == 2) {
        lv_obj_t * badge =
            xhs_pill(page, x + 46, 42, 14, 14, XHS_RED, index == 0 ? "2" : "5",
                     XHS_FT_11, XHS_WHITE, 7);
        (void)badge;
    }
}

static void xhs_messages_page_build(lv_obj_t * page)
{
    lv_obj_t * title = xhs_label_at(page, XHS_TXT_MSG_TITLE, XHS_FT_14B,
                                    XHS_TEXT, 0, 12, XHS_SCREEN_W, 20);
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t * search = xhs_image(page, XHS_ICON_SEARCH, 272, 12);
    xhs_clickable(search, "message_search");
    lv_obj_set_ext_click_area(search, 6);

    for(int i = 0; i < 4; i++) {
        xhs_channel_entry(page, i);
    }

    lv_obj_t * divider = xhs_box(page, 0, 128, XHS_SCREEN_W, 8);
    lv_obj_set_style_bg_color(divider, lv_color_hex(XHS_SOFT), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);

    lv_obj_t * list = xhs_scroll(page, 0, 136, XHS_SCREEN_W, 358);
    lv_obj_set_name(list, "message_list");

    for(int i = 0; i < 4; i++) {
        int y = i * 72;
        lv_obj_t * row = xhs_box(list, 0, y, XHS_SCREEN_W, 72);
        xhs_clickable(row, i == 0   ? "chat_0"
                           : i == 1 ? "chat_1"
                           : i == 2 ? "chat_2"
                                    : "chat_3");
        lv_obj_add_event_cb(row, xhs_message_event_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);

        xhs_avatar(row, 14, 13, 44, messages[i].color, messages[i].avatar,
                   XHS_FT_12B);
        lv_obj_t * name = xhs_label_at(row, messages[i].name, XHS_FT_12B,
                                       XHS_TEXT, 70, 13, 170, 18);
        lv_label_set_long_mode(name, LV_LABEL_LONG_MODE_DOTS);
        lv_obj_t * preview = xhs_label_at(row, messages[i].preview, XHS_FT_11,
                                          XHS_MUTED, 70, 37, 172, 16);
        lv_label_set_long_mode(preview, LV_LABEL_LONG_MODE_DOTS);
        lv_obj_t * time = xhs_label_at(row, messages[i].time, XHS_FT_11,
                                       XHS_META, 250, 15, 44, 16);
        lv_obj_set_style_text_align(time, LV_TEXT_ALIGN_RIGHT, 0);

        if(i == 2) {
            lv_obj_t * unread = xhs_pill(row, 252, 38, 18, 16, XHS_RED, "3",
                                         XHS_FT_11, XHS_WHITE, 8);
            (void)unread;
        }

        lv_obj_t * line = xhs_box(row, 70, 71, 224, 1);
        lv_obj_set_style_bg_color(line, lv_color_hex(XHS_LINE), 0);
        lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);
    }
    xhs_box(list, 0, 4 * 72, 1, 1);
}

lv_obj_t * xhs_messages_create(lv_obj_t * parent)
{
    messages_page = xhs_root_page(parent);
    xhs_messages_page_build(messages_page);
    return messages_page;
}

#endif
