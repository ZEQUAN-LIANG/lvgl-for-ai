
#include "xhs_ui.h"

#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

static const char * const tab_texts[3] = {
    XHS_TXT_TAB_FOLLOW, XHS_TXT_TAB_FOR_YOU, XHS_TXT_TAB_NEARBY,
};
static const char * const category_texts[6] = {
    XHS_TXT_CAT_RECOMMEND, XHS_TXT_CAT_LIVE, XHS_TXT_CAT_DRAMA,
    XHS_TXT_CAT_OUTFIT, XHS_TXT_CAT_TRAVEL, XHS_TXT_CAT_ANIME,
};
static const char * const category_more_texts[6] = {
    XHS_TXT_CAT_MORE_0, XHS_TXT_CAT_MORE_1, XHS_TXT_CAT_MORE_2,
    XHS_TXT_CAT_MORE_3, XHS_TXT_CAT_MORE_4, XHS_TXT_CAT_MORE_5,
};

#define XHS_CATEGORY_COUNT 12

static const char * xhs_category_name(int index)
{
    return index < 6 ? category_texts[index]
                     : category_more_texts[index - 6];
}

static const char * const comment_names[3] = {
    XHS_TXT_COMMENT_0_NAME, XHS_TXT_COMMENT_1_NAME, XHS_TXT_COMMENT_2_NAME,
};
static const char * const comment_texts[3] = {
    XHS_TXT_COMMENT_0_TEXT, XHS_TXT_COMMENT_1_TEXT, XHS_TXT_COMMENT_2_TEXT,
};
static const char * const comment_initials[3] = { "m", "阿", "小" };
static const uint32_t comment_colors[3] = { 0x8FB3D9, 0xE7A6A0, 0xA9C58F };

static lv_obj_t * home_page;
static lv_obj_t * feed;
static lv_obj_t * category_bar;
static lv_obj_t * tab_labels[3];
static lv_obj_t * tab_underline;
static lv_obj_t * category_labels[6];
static lv_obj_t * category_panel;
static lv_obj_t * category_panel_labels[XHS_CATEGORY_COUNT];
static lv_obj_t * category_chevron;
static int visible_categories[6] = { 0, 1, 2, 3, 4, 5 };
static lv_obj_t * search_overlay;
static lv_obj_t * search_textarea;
static lv_obj_t * search_keyboard;
static lv_obj_t * search_letter_labels[26];
static bool search_shift;
static lv_obj_t * search_suggest_box;
static lv_obj_t * search_results;
static lv_obj_t * note_overlay;

static void xhs_search_open(void);

static lv_obj_t * detail_like_icon;
static lv_obj_t * detail_like_label;
static lv_obj_t * detail_collect_icon;
static lv_obj_t * detail_collect_label;

static int active_tab = 1;
static int active_category = 0;


static void xhs_reset_note_widgets(void)
{
    for(int i = 0; i < XHS_NOTE_COUNT; i++) {
        xhs_notes[i].like_icon = NULL;
        xhs_notes[i].like_label = NULL;
    }
}

static void xhs_note_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    xhs_note_open((int)(intptr_t)lv_event_get_user_data(event));
}

static void xhs_like_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    xhs_note_t * note = &xhs_notes[index];
    note->liked = !note->liked;
    note->likes += note->liked ? 1 : -1;
    lv_image_set_src(note->like_icon,
                     note->liked ? xhs_icon(XHS_ICON_HEART_FILLED)
                                 : xhs_icon(XHS_ICON_HEART_OUTLINE));
    char buffer[12];
    snprintf(buffer, sizeof(buffer), "%d", note->likes);
    lv_label_set_text(note->like_label, buffer);
    printf("[xhs] like note=%d liked=%d count=%d\n",
           index, note->liked ? 1 : 0, note->likes);
}

static void xhs_follow_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    xhs_note_t * note = &xhs_notes[index];
    note->following = !note->following;

    lv_obj_t * chip = lv_event_get_target_obj(event);
    lv_obj_set_style_bg_color(chip, lv_color_hex(note->following ? XHS_SOFT
                                                                : XHS_RED), 0);
    lv_obj_t * label = lv_obj_get_child(chip, 0);
    if(label != NULL) {
        lv_label_set_text(label, note->following ? XHS_TXT_FOLLOWED
                                                 : XHS_TXT_FOLLOW);
        lv_obj_set_style_text_color(label,
                                    lv_color_hex(note->following ? XHS_MUTED
                                                                 : XHS_WHITE), 0);
    }
    printf("[xhs] follow note=%d following=%d\n", index,
           note->following ? 1 : 0);
}

static void xhs_follow_chip(lv_obj_t * parent, xhs_note_t * note, int index,
                            int x, int y)
{
    lv_obj_t * chip = xhs_pill(parent, x, y, 38, 18,
                               note->following ? XHS_SOFT : XHS_RED,
                               note->following ? XHS_TXT_FOLLOWED
                                               : XHS_TXT_FOLLOW,
                               XHS_FT_11,
                               note->following ? XHS_MUTED : XHS_WHITE, 9);
    xhs_clickable(chip, NULL);
    lv_obj_add_event_cb(chip, xhs_follow_event_cb, LV_EVENT_CLICKED,
                        (void *)(intptr_t)index);
}

static int xhs_card_create(xhs_note_t * note, int index, int x, int y)
{
    const int cover_h = xhs_cover_height(note->cover_index);

    lv_obj_t * card = xhs_box(feed, x, y, XHS_COVER_W, 20);
    xhs_clickable(card, index == 0 ? "note_0" : index == 1 ? "note_1" :
                         index == 2 ? "note_2" : index == 3 ? "note_3" :
                         index == 4 ? "note_4" : "note_5");
    lv_obj_add_event_cb(card, xhs_note_event_cb, LV_EVENT_CLICKED,
                        (void *)(intptr_t)index);

    lv_obj_t * cover = xhs_box(card, 0, 0, XHS_COVER_W, cover_h);
    lv_obj_set_style_radius(cover, 8, 0);
    lv_obj_set_style_clip_corner(cover, true, 0);
    lv_obj_set_style_bg_color(cover, lv_color_hex(0xECECEE), 0);
    lv_obj_set_style_bg_opa(cover, LV_OPA_COVER, 0);
    xhs_cover_thumb(cover, note->cover_index, 0, 0, XHS_COVER_W, cover_h, 0);

    if(index == 4) {
        xhs_image(cover, XHS_ICON_PLAY, XHS_COVER_W - 28, 6);
    }

    lv_obj_t * title = xhs_label(card, note->title, XHS_FT_13, XHS_TITLE);
    lv_obj_set_pos(title, 0, cover_h + 6);
    lv_obj_set_width(title, XHS_COVER_W);
    lv_label_set_long_mode(title, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_style_text_line_space(title, 1, 0);

    lv_point_t title_size;
    lv_text_get_size(&title_size, note->title, xhs_font(XHS_FT_13), 0, 1,
                     XHS_COVER_W, LV_TEXT_FLAG_NONE);
    lv_obj_set_height(title, title_size.y + 2);

    const int meta_y = cover_h + 6 + title_size.y + 5;

    xhs_avatar(card, 0, meta_y, 16, note->avatar_color, note->avatar,
               XHS_FT_11);

    lv_obj_t * author = xhs_label(card, note->author, XHS_FT_11, XHS_AUTHOR);
    lv_obj_set_pos(author, 20, meta_y + 2);
    lv_obj_set_size(author, 72, 14);
    lv_label_set_long_mode(author, LV_LABEL_LONG_MODE_DOTS);

    lv_obj_t * like = xhs_box(card, 95, meta_y, 43, 18);
    xhs_clickable(like, index == 0 ? "like_0" : index == 1 ? "like_1" :
                       index == 2 ? "like_2" : index == 3 ? "like_3" :
                       index == 4 ? "like_4" : "like_5");
    lv_obj_set_ext_click_area(like, 3);
    lv_obj_add_event_cb(like, xhs_like_event_cb, LV_EVENT_CLICKED,
                        (void *)(intptr_t)index);
    note->like_icon = xhs_image(like,
                                note->liked ? XHS_ICON_HEART_FILLED
                                            : XHS_ICON_HEART_OUTLINE, 0, 1);
    note->like_label = xhs_label(like, "", XHS_FT_11, XHS_META);
    lv_obj_set_pos(note->like_label, 17, 1);
    lv_obj_set_size(note->like_label, 26, 16);
    lv_obj_set_style_text_align(note->like_label, LV_TEXT_ALIGN_RIGHT, 0);
    char likes[12];
    snprintf(likes, sizeof(likes), "%d", note->likes);
    lv_label_set_text(note->like_label, likes);

    const int card_h = meta_y + 20;
    lv_obj_set_height(card, card_h);
    printf("[xhs] note %d cover_h=%d title_h=%d card_h=%d\n",
           index, cover_h, (int)title_size.y, card_h);
    return card_h;
}

static int xhs_feed_row(xhs_note_t * note, int index, int y, bool nearby)
{
    lv_obj_t * row = xhs_box(feed, 6, y, 292, 104);
    xhs_clickable(row, index == 0 ? "note_0" : index == 1 ? "note_1" :
                       index == 2 ? "note_2" : index == 3 ? "note_3" :
                       index == 4 ? "note_4" : "note_5");
    lv_obj_add_event_cb(row, xhs_note_event_cb, LV_EVENT_CLICKED,
                        (void *)(intptr_t)index);

    xhs_cover_thumb(row, note->cover_index, 4, 4, 96, 96, 8);

    lv_obj_t * title = xhs_label_at(row, note->title, XHS_FT_13, XHS_TITLE,
                                    110, 8, 132, 36);
    lv_label_set_long_mode(title, LV_LABEL_LONG_MODE_DOTS);

    xhs_follow_chip(row, note, index, 246, 8);

    xhs_avatar(row, 110, 54, 18, note->avatar_color, note->avatar,
               XHS_FT_11);
    lv_obj_t * author = xhs_label_at(row, note->author, XHS_FT_11,
                                     XHS_AUTHOR, 134, 55, 92, 16);
    lv_label_set_long_mode(author, LV_LABEL_LONG_MODE_DOTS);

    char meta[96];
    if(nearby) {
        snprintf(meta, sizeof(meta), "%s · %s", note->location, note->distance);
    }
    else {
        snprintf(meta, sizeof(meta), "%s", XHS_TXT_JUST_NOW);
    }
    lv_obj_t * meta_label = xhs_label_at(row, meta, XHS_FT_11, XHS_MUTED,
                                         110, 78, 132, 16);
    lv_label_set_long_mode(meta_label, LV_LABEL_LONG_MODE_DOTS);

    xhs_image(row, XHS_ICON_HEART_OUTLINE, 246, 80);
    char likes[12];
    snprintf(likes, sizeof(likes), "%d", note->likes);
    lv_obj_t * like_label = xhs_label_at(row, likes, XHS_FT_11, XHS_META,
                                         262, 78, 30, 16);
    lv_obj_set_style_text_align(like_label, LV_TEXT_ALIGN_RIGHT, 0);
    note->like_label = like_label;

    lv_obj_t * divider = xhs_box(row, 0, 103, 292, 1);
    lv_obj_set_style_bg_color(divider, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);

    return 112;
}

static bool xhs_category_match(int note, int category)
{
    switch(category) {
        case 1:
            return note == 0 || note == 4;
        case 2:
            return note == 1 || note == 2;
        case 3:
            return note == 0 || note == 5;
        case 4:
            return note == 1 || note == 3;
        case 5:
            return note == 1 || note == 5;
        default:
            return true;
    }
}

static void xhs_build_for_you(void)
{
    int column_x[2] = { 10, 156 };
    int column_y[2] = { 0, 0 };
    int slot = 0;
    for(int i = 0; i < XHS_NOTE_COUNT; i++) {
        if(!xhs_category_match(i, active_category)) continue;
        int column = slot % 2;
        int card_h = xhs_card_create(&xhs_notes[i], i,
                                     column_x[column], column_y[column]);
        column_y[column] += card_h + 12;
        slot++;
    }
    int bottom = column_y[0] > column_y[1] ? column_y[0] : column_y[1];
    xhs_box(feed, 0, bottom, 1, 1);
}

static void xhs_build_follow(void)
{
    static const int order[5] = { 0, 2, 3, 5, 4 };
    int y = 0;
    for(int i = 0; i < 5; i++) {
        y += xhs_feed_row(&xhs_notes[order[i]], order[i], y, false);
    }
    xhs_box(feed, 0, y, 1, 1);
}

static void xhs_build_nearby(void)
{
    static const int order[6] = { 3, 2, 0, 5, 4, 1 };
    int y = 0;
    for(int i = 0; i < 6; i++) {
        y += xhs_feed_row(&xhs_notes[order[i]], order[i], y, true);
    }
    xhs_box(feed, 0, y, 1, 1);
}

static void xhs_build_feed(void)
{
    xhs_reset_note_widgets();
    lv_obj_clean(feed);
    lv_obj_scroll_to_y(feed, 0, LV_ANIM_OFF);
    if(active_tab == 0) {
        xhs_build_follow();
    }
    else if(active_tab == 2) {
        xhs_build_nearby();
    }
    else {
        xhs_build_for_you();
    }
}


static void xhs_tab_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    active_tab = index;
    for(int i = 0; i < 3; i++) {
        lv_obj_set_style_text_font(tab_labels[i],
                                   xhs_font(i == index ? XHS_FT_14B
                                                       : XHS_FT_14), 0);
        lv_obj_set_style_text_color(tab_labels[i],
                                    lv_color_hex(i == index ? XHS_TEXT
                                                            : XHS_MUTED), 0);
    }
    lv_obj_align_to(tab_underline, tab_labels[index], LV_ALIGN_OUT_BOTTOM_MID,
                    0, 2);
    xhs_set_hidden(category_bar, index != 1);
    if(category_panel != NULL) xhs_set_hidden(category_panel, true);
    if(category_chevron != NULL) lv_image_set_rotation(category_chevron, 0);
    lv_obj_set_pos(feed, 0, index == 1 ? 76 : 49);
    lv_obj_set_height(feed, index == 1 ? 418 : 445);
    xhs_build_feed();
    printf("[xhs] tab=%s\n", tab_texts[index]);
}

static void xhs_category_refresh(void)
{
    for(int i = 0; i < 6; i++) {
        int index = visible_categories[i];
        lv_label_set_text(category_labels[i], xhs_category_name(index));
        lv_obj_set_style_text_font(category_labels[i],
                                   xhs_font(index == active_category
                                                ? XHS_FT_12B
                                                : XHS_FT_12), 0);
        lv_obj_set_style_text_color(category_labels[i],
                                    lv_color_hex(index == active_category
                                                     ? XHS_TEXT : XHS_MUTED), 0);
    }
    for(int i = 0; i < XHS_CATEGORY_COUNT; i++) {
        if(category_panel_labels[i] == NULL) continue;
        lv_obj_set_style_text_font(category_panel_labels[i],
                                   xhs_font(i == active_category
                                                ? XHS_FT_12B
                                                : XHS_FT_12), 0);
        lv_obj_set_style_text_color(category_panel_labels[i],
                                    lv_color_hex(i == active_category
                                                     ? XHS_RED : XHS_TEXT), 0);
    }
}

static void xhs_category_apply(int index)
{
    if(index < 0 || index >= XHS_CATEGORY_COUNT) return;
    active_category = index;
    if(index >= 6) {
        for(int i = 0; i < 5; i++) visible_categories[i] = i;
        visible_categories[5] = index;
    }
    else {
        for(int i = 0; i < 6; i++) visible_categories[i] = i;
    }
    xhs_category_refresh();
    if(category_panel != NULL) xhs_set_hidden(category_panel, true);
    if(category_chevron != NULL) lv_image_set_rotation(category_chevron, 0);
    if(active_tab == 1) {
        xhs_build_feed();
    }
    printf("[xhs] category=%s\n", xhs_category_name(active_category));
}

static void xhs_category_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int slot = (int)(intptr_t)lv_event_get_user_data(event);
    xhs_category_apply(visible_categories[slot]);
}

static void xhs_category_more_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    xhs_category_apply((int)(intptr_t)lv_event_get_user_data(event));
}

static void xhs_search_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    xhs_search_open();
}

static void xhs_more_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    if(category_panel == NULL) return;
    bool show = lv_obj_is_hidden(category_panel);
    xhs_set_hidden(category_panel, !show);
    if(category_chevron != NULL) {
        lv_image_set_rotation(category_chevron, show ? 1800 : 0);
    }
    printf("[xhs] categories more clicked\n");
}


typedef struct {
    const char * word;
    int results[3];
    int count;
} xhs_search_term_t;

static const xhs_search_term_t search_terms[] = {
    { XHS_TXT_SEARCH_HISTORY_0, { 5, 0 }, 2 },
    { XHS_TXT_SEARCH_HISTORY_1, { 2, 4 }, 2 },
    { XHS_TXT_SEARCH_HISTORY_2, { 3, 0 }, 2 },
    { XHS_TXT_SEARCH_SUGGEST_0, { 2, 1 }, 2 },
    { XHS_TXT_SEARCH_SUGGEST_1, { 0, 3 }, 2 },
    { XHS_TXT_SEARCH_SUGGEST_2, { 0 }, 1 },
};

static void xhs_search_relabel(void);

static void xhs_search_reset(void)
{
    if(search_textarea != NULL) {
        lv_textarea_set_text(search_textarea, "");
    }
    search_shift = false;
    xhs_search_relabel();
    if(search_keyboard != NULL) {
        xhs_set_hidden(search_keyboard, true);
    }
    if(search_results != NULL) {
        lv_obj_clean(search_results);
        xhs_set_hidden(search_results, true);
    }
    if(search_suggest_box != NULL) {
        xhs_set_hidden(search_suggest_box, false);
    }
}

static void xhs_search_field_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    if(search_keyboard == NULL) return;
    xhs_set_hidden(search_keyboard, false);
    printf("[xhs] search field tapped\n");
}

static void xhs_search_note_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    xhs_note_open((int)(intptr_t)lv_event_get_user_data(event));
}

static int xhs_search_row(int index, int y)
{
    xhs_note_t * note = &xhs_notes[index];
    lv_obj_t * row = xhs_box(search_results, 0, y, XHS_SCREEN_W, 92);
    xhs_clickable(row, NULL);
    lv_obj_add_event_cb(row, xhs_search_note_cb, LV_EVENT_CLICKED,
                        (void *)(intptr_t)index);

    xhs_cover_thumb(row, note->cover_index, 16, 10, 72, 72, 8);
    lv_obj_t * title = xhs_label_at(row, note->title, XHS_FT_13, XHS_TITLE,
                                    100, 12, 188, 36);
    lv_label_set_long_mode(title, LV_LABEL_LONG_MODE_DOTS);

    xhs_avatar(row, 100, 52, 16, note->avatar_color, note->avatar,
               XHS_FT_11);
    lv_obj_t * author = xhs_label_at(row, note->author, XHS_FT_11,
                                     XHS_AUTHOR, 120, 53, 100, 16);
    lv_label_set_long_mode(author, LV_LABEL_LONG_MODE_DOTS);

    xhs_image(row, XHS_ICON_HEART_OUTLINE, 246, 54);
    char likes[12];
    snprintf(likes, sizeof(likes), "%d", note->likes);
    lv_obj_t * like_label = xhs_label_at(row, likes, XHS_FT_11, XHS_META,
                                         262, 52, 30, 16);
    lv_obj_set_style_text_align(like_label, LV_TEXT_ALIGN_RIGHT, 0);

    lv_obj_t * divider = xhs_box(row, 16, 91, 272, 1);
    lv_obj_set_style_bg_color(divider, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);
    return 92;
}

static bool xhs_search_text_matches(const char * text, const char * word)
{
    if(text == NULL || word == NULL || word[0] == '\0') return false;
    size_t word_len = strlen(word);
    for(const char * start = text; *start != '\0'; start++) {
        size_t i = 0;
        while(i < word_len && start[i] != '\0') {
            char a = start[i];
            char b = word[i];
            if(a >= 'A' && a <= 'Z') a = (char)(a - 'A' + 'a');
            if(b >= 'A' && b <= 'Z') b = (char)(b - 'A' + 'a');
            if(a != b) break;
            i++;
        }
        if(i == word_len) return true;
    }
    return false;
}

static void xhs_search_show_results(const char * word)
{
    if(search_results == NULL || word == NULL) return;
    lv_obj_clean(search_results);

    int ids[6] = { 0, 1, 2, 3, 4, 5 };
    int count = 0;
    bool matched = false;
    size_t term_count = sizeof(search_terms) / sizeof(search_terms[0]);
    for(size_t i = 0; i < term_count; i++) {
        if(strcmp(search_terms[i].word, word) != 0) continue;
        count = search_terms[i].count;
        for(int j = 0; j < count; j++) ids[j] = search_terms[i].results[j];
        matched = true;
        break;
    }
    if(!matched) {
        for(int i = 0; i < XHS_NOTE_COUNT; i++) {
            xhs_note_t * note = &xhs_notes[i];
            if(xhs_search_text_matches(note->title, word) ||
               xhs_search_text_matches(note->body, word) ||
               xhs_search_text_matches(note->tag, word) ||
               xhs_search_text_matches(note->author, word)) {
                ids[count++] = i;
            }
        }
        if(count == 0) {
            ids[0] = 0;
            ids[1] = 1;
            ids[2] = 2;
            count = 3;
        }
    }

    int y = 0;
    for(int i = 0; i < count; i++) {
        y += xhs_search_row(ids[i], y);
    }
    lv_obj_scroll_to_y(search_results, 0, LV_ANIM_OFF);
    xhs_set_hidden(search_suggest_box, true);
    xhs_set_hidden(search_results, false);
}

static void xhs_search_pick_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    const char * text = (const char *)lv_event_get_user_data(event);
    if(text == NULL) return;
    if(search_textarea != NULL) {
        lv_textarea_set_text(search_textarea, text);
    }
    if(search_keyboard != NULL) xhs_set_hidden(search_keyboard, true);
    xhs_search_show_results(text);
    printf("[xhs] search pick %s\n", text);
}


static void xhs_search_relabel(void)
{
    for(int i = 0; i < 26; i++) {
        if(search_letter_labels[i] == NULL) continue;
        char text[2] = { (char)(search_shift ? 'A' + i : 'a' + i), '\0' };
        lv_label_set_text(search_letter_labels[i], text);
    }
}

static void xhs_search_submit(void)
{
    if(search_textarea == NULL) return;
    const char * text = lv_textarea_get_text(search_textarea);
    if(search_keyboard != NULL) xhs_set_hidden(search_keyboard, true);
    if(text == NULL || text[0] == '\0') {
        xhs_search_reset();
        return;
    }
    xhs_search_show_results(text);
    printf("[xhs] search submit %s\n", text);
}

static void xhs_search_key_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    const char * value = (const char *)lv_event_get_user_data(event);
    if(value == NULL || search_textarea == NULL) return;
    if(strcmp(value, "bs") == 0) {
        lv_textarea_delete_char(search_textarea);
    }
    else if(strcmp(value, "shift") == 0) {
        search_shift = !search_shift;
        xhs_search_relabel();
    }
    else if(strcmp(value, "space") == 0) {
        lv_textarea_add_char(search_textarea, ' ');
    }
    else if(strcmp(value, "submit") == 0) {
        xhs_search_submit();
    }
    else if(strcmp(value, "clear") == 0) {
        lv_textarea_set_text(search_textarea, "");
    }
    else {
        char ch = value[0];
        if(search_shift) {
            ch = (char)toupper((unsigned char)ch);
            search_shift = false;
            xhs_search_relabel();
        }
        lv_textarea_add_char(search_textarea, ch);
    }
}

static lv_obj_t * xhs_search_key(lv_obj_t * parent, const char * label,
                                 const char * value, int x, int y, int w, int h,
                                 uint32_t bg, uint32_t fg)
{
    lv_obj_t * key = xhs_box(parent, x, y, w, h);
    lv_obj_set_style_radius(key, 6, 0);
    lv_obj_set_style_bg_color(key, lv_color_hex(bg), 0);
    lv_obj_set_style_bg_opa(key, LV_OPA_COVER, 0);
    lv_obj_set_style_shadow_color(key, lv_color_hex(0x000000), 0);
    lv_obj_set_style_shadow_width(key, 2, 0);
    lv_obj_set_style_shadow_opa(key, 14, 0);
    xhs_clickable(key, NULL);
    lv_obj_add_event_cb(key, xhs_search_key_cb, LV_EVENT_CLICKED,
                        (void *)value);
    lv_obj_t * text = xhs_label(key, label, XHS_FT_12, fg);
    lv_obj_center(text);
    return key;
}

static void xhs_search_keyboard_build(lv_obj_t * page)
{
    search_keyboard = xhs_box(page, 0, 380, XHS_SCREEN_W, 160);
    lv_obj_set_style_radius(search_keyboard, 12, 0);
    lv_obj_set_style_bg_color(search_keyboard, lv_color_hex(XHS_SOFT), 0);
    lv_obj_set_style_bg_opa(search_keyboard, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(search_keyboard, 1, 0);
    lv_obj_set_style_border_color(search_keyboard, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_shadow_color(search_keyboard, lv_color_hex(0x000000), 0);
    lv_obj_set_style_shadow_width(search_keyboard, 16, 0);
    lv_obj_set_style_shadow_opa(search_keyboard, 12, 0);
    lv_obj_set_style_shadow_ofs_y(search_keyboard, -4, 0);

    static const char * const rows[3] = {
        "qwertyuiop", "asdfghjkl", "zxcvbnm",
    };
    for(int row = 0; row < 3; row++) {
        const char * letters = rows[row];
        int count = (int)strlen(letters);
        int x = row == 1 ? 18 : (row == 2 ? 48 : 4);
        int y = 8 + row * 38;
        for(int i = 0; i < count; i++) {
            char lower[2] = { letters[i], '\0' };
            lv_obj_t * key = xhs_search_key(search_keyboard, lower,
                                            letters + i, x + i * 29, y, 27, 32,
                                            XHS_WHITE, XHS_TEXT);
            search_letter_labels[letters[i] - 'a'] =
                lv_obj_get_child(key, 0);
        }
    }

    xhs_search_key(search_keyboard, "Aa", "shift", 4, 84, 40, 32,
                   XHS_SOFT, XHS_TEXT);
    xhs_search_key(search_keyboard, "DEL", "bs", 253, 84, 47, 32,
                   XHS_SOFT, XHS_TEXT);
    xhs_search_key(search_keyboard, "CLR", "clear", 4, 122, 56, 32,
                   XHS_SOFT, XHS_TEXT);
    xhs_search_key(search_keyboard, "space", "space", 64, 122, 156, 32,
                   XHS_WHITE, XHS_TEXT);
    xhs_search_key(search_keyboard, XHS_TXT_SEARCH_ACTION, "submit",
                   224, 122, 76, 32, XHS_RED, XHS_WHITE);
    xhs_set_hidden(search_keyboard, true);
}

static void xhs_search_build(lv_obj_t * page)
{
    lv_obj_clean(page);

    lv_obj_t * back = xhs_image(page, XHS_ICON_BACK, 12, 13);
    xhs_clickable(back, "search_back");
    lv_obj_set_ext_click_area(back, 8);
    lv_obj_add_event_cb(back, xhs_back_event_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * field = xhs_box(page, 42, 9, 196, 30);
    lv_obj_set_style_radius(field, 15, 0);
    lv_obj_set_style_bg_color(field, lv_color_hex(XHS_SOFT), 0);
    lv_obj_set_style_bg_opa(field, LV_OPA_COVER, 0);
    xhs_clickable(field, "search_field");
    lv_obj_add_event_cb(field, xhs_search_field_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t * field_icon = xhs_image(field, XHS_ICON_SEARCH, 0, 0);
    lv_obj_align(field_icon, LV_ALIGN_LEFT_MID, 9, 0);
    search_textarea = lv_textarea_create(field);
    lv_obj_set_pos(search_textarea, 34, 0);
    lv_obj_set_size(search_textarea, 154, 30);
    lv_textarea_set_one_line(search_textarea, true);
    lv_textarea_set_placeholder_text(search_textarea,
                                     XHS_TXT_SEARCH_PLACEHOLDER);
    lv_obj_set_clickable(search_textarea, false);
    lv_obj_set_style_bg_opa(search_textarea, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(search_textarea, 0, 0);
    lv_obj_set_style_pad_all(search_textarea, 0, 0);
    lv_obj_set_style_pad_top(search_textarea, 7, 0);
    lv_obj_set_style_text_font(search_textarea, xhs_font(XHS_FT_12), 0);
    lv_obj_set_style_text_color(search_textarea, lv_color_hex(XHS_TEXT), 0);
    lv_obj_set_style_text_color(search_textarea, lv_color_hex(XHS_MUTED),
                                LV_PART_TEXTAREA_PLACEHOLDER);

    lv_obj_t * cancel = xhs_label_at(page, XHS_TXT_SEARCH_CANCEL,
                                     XHS_FT_12, XHS_TEXT, 246, 15, 46, 18);
    lv_obj_set_style_text_align(cancel, LV_TEXT_ALIGN_RIGHT, 0);
    xhs_clickable(cancel, "search_cancel");
    lv_obj_add_event_cb(cancel, xhs_back_event_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * line = xhs_box(page, 0, 48, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);

    search_suggest_box = xhs_box(page, 0, 49, XHS_SCREEN_W,
                                 XHS_OVERLAY_H - 49);
    xhs_label_at(search_suggest_box, XHS_TXT_SEARCH_HISTORY,
                 XHS_FT_12B, XHS_TEXT, 16, 13, 160, 18);

    static const char * const history_texts[3] = {
        XHS_TXT_SEARCH_HISTORY_0, XHS_TXT_SEARCH_HISTORY_1,
        XHS_TXT_SEARCH_HISTORY_2,
    };
    static const int history_x[3] = { 16, 94, 160 };
    static const int history_w[3] = { 70, 58, 44 };
    for(int i = 0; i < 3; i++) {
        lv_obj_t * pill = xhs_pill(search_suggest_box, history_x[i], 39,
                                   history_w[i], 28, XHS_SOFT,
                                   history_texts[i], XHS_FT_12, XHS_TEXT, 14);
        xhs_clickable(pill, NULL);
        lv_obj_add_event_cb(pill, xhs_search_pick_cb, LV_EVENT_CLICKED,
                            (void *)history_texts[i]);
    }

    xhs_label_at(search_suggest_box, XHS_TXT_SEARCH_SUGGEST,
                 XHS_FT_12B, XHS_TEXT, 16, 83, 160, 18);

    static const char * const suggest_texts[3] = {
        XHS_TXT_SEARCH_SUGGEST_0, XHS_TXT_SEARCH_SUGGEST_1,
        XHS_TXT_SEARCH_SUGGEST_2,
    };
    for(int i = 0; i < 3; i++) {
        int y = 113 + i * 44;
        lv_obj_t * row = xhs_box(search_suggest_box, 0, y, XHS_SCREEN_W, 44);
        xhs_clickable(row, NULL);
        lv_obj_add_event_cb(row, xhs_search_pick_cb, LV_EVENT_CLICKED,
                            (void *)suggest_texts[i]);
        xhs_image(row, XHS_ICON_SEARCH, 16, 13);
        lv_obj_t * text = xhs_label_at(row, suggest_texts[i], XHS_FT_13,
                                       XHS_TEXT, 40, 11, 230, 20);
        lv_label_set_long_mode(text, LV_LABEL_LONG_MODE_DOTS);
        lv_obj_t * sep = xhs_box(row, 16, 43, 272, 1);
        lv_obj_set_style_bg_color(sep, lv_color_hex(XHS_LINE), 0);
        lv_obj_set_style_bg_opa(sep, LV_OPA_COVER, 0);
    }

    search_results = xhs_scroll(page, 0, 52, XHS_SCREEN_W,
                                XHS_OVERLAY_H - 52);
    xhs_set_hidden(search_results, true);
    xhs_search_keyboard_build(page);
}

static void xhs_search_open(void)
{
    if(search_overlay == NULL) {
        search_overlay = xhs_page(xhs_overlay_host());
        xhs_search_build(search_overlay);
    }
    xhs_search_reset();
    xhs_open_overlay(search_overlay);
    printf("[xhs] search open\n");
}

static void xhs_top_nav(lv_obj_t * page)
{
    lv_obj_t * logo = xhs_box(page, 12, 5, 34, 34);
    lv_obj_set_style_radius(logo, 11, 0);
    lv_obj_set_style_bg_color(logo, lv_color_hex(XHS_RED), 0);
    lv_obj_set_style_bg_opa(logo, LV_OPA_COVER, 0);
    lv_obj_set_style_shadow_color(logo, lv_color_hex(XHS_RED), 0);
    lv_obj_set_style_shadow_width(logo, 6, 0);
    lv_obj_set_style_shadow_opa(logo, 45, 0);
    lv_obj_t * logo_text = xhs_label(logo, XHS_TXT_LOGO, XHS_FT_11, XHS_WHITE);
    lv_obj_set_style_text_letter_space(logo_text, -1, 0);
    lv_obj_center(logo_text);

    for(int i = 0; i < 3; i++) {
        lv_obj_t * tab = xhs_label(page, tab_texts[i], XHS_FT_14, XHS_MUTED);
        lv_obj_set_pos(tab, 86 + i * 44, 10);
        lv_obj_set_size(tab, 44, 18);
        lv_obj_set_style_text_align(tab, LV_TEXT_ALIGN_CENTER, 0);
        xhs_clickable(tab, NULL);
        lv_obj_add_event_cb(tab, xhs_tab_event_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        tab_labels[i] = tab;
    }

    tab_underline = xhs_box(page, 0, 0, 16, 3);
    lv_obj_set_style_radius(tab_underline, 2, 0);
    lv_obj_set_style_bg_color(tab_underline, lv_color_hex(XHS_RED), 0);
    lv_obj_set_style_bg_opa(tab_underline, LV_OPA_COVER, 0);

    lv_obj_t * search = xhs_image(page, XHS_ICON_SEARCH, 272, 11);
    xhs_clickable(search, "search_button");
    lv_obj_set_ext_click_area(search, 6);
    lv_obj_add_event_cb(search, xhs_search_event_cb, LV_EVENT_CLICKED, NULL);
}

static void xhs_category_bar(lv_obj_t * page)
{
    category_bar = xhs_box(page, 0, 49, XHS_SCREEN_W, 51);
    for(int i = 0; i < 6; i++) {
        lv_obj_t * chip = xhs_label(category_bar, category_texts[i],
                                    XHS_FT_12, XHS_MUTED);
        lv_obj_set_pos(chip, 10 + i * 40, 0);
        lv_obj_set_size(chip, 30, 18);
        lv_obj_set_style_text_align(chip, LV_TEXT_ALIGN_CENTER, 0);
        xhs_clickable(chip, NULL);
        lv_obj_add_event_cb(chip, xhs_category_event_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        category_labels[i] = chip;
    }
    category_chevron = xhs_image(category_bar, XHS_ICON_CHEVRON, 277, 4);
    xhs_clickable(category_chevron, NULL);
    lv_obj_set_ext_click_area(category_chevron, 6);
    lv_obj_add_event_cb(category_chevron, xhs_more_event_cb, LV_EVENT_CLICKED,
                        NULL);

    lv_obj_t * divider = xhs_box(category_bar, 0, 26, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(divider, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);
}

static void xhs_category_panel_create(lv_obj_t * page)
{
    category_panel = xhs_box(page, 8, 76, XHS_SCREEN_W - 16, 140);
    lv_obj_set_style_radius(category_panel, 12, 0);
    lv_obj_set_style_bg_color(category_panel, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(category_panel, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(category_panel, 1, 0);
    lv_obj_set_style_border_color(category_panel, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_shadow_color(category_panel, lv_color_hex(0x000000), 0);
    lv_obj_set_style_shadow_width(category_panel, 18, 0);
    lv_obj_set_style_shadow_opa(category_panel, 18, 0);
    lv_obj_set_style_shadow_ofs_y(category_panel, 6, 0);

    for(int i = 0; i < XHS_CATEGORY_COUNT; i++) {
        int col = i % 3;
        int row = i / 3;
        lv_obj_t * cell = xhs_label_at(category_panel, xhs_category_name(i),
                                       XHS_FT_12, XHS_TEXT,
                                       8 + col * 92, 10 + row * 30, 84, 22);
        lv_obj_set_style_text_align(cell, LV_TEXT_ALIGN_CENTER, 0);
        xhs_clickable(cell, NULL);
        lv_obj_add_event_cb(cell, xhs_category_more_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        category_panel_labels[i] = cell;
    }
    xhs_set_hidden(category_panel, true);
    xhs_category_refresh();
}

lv_obj_t * xhs_home_create(lv_obj_t * parent)
{
    home_page = xhs_root_page(parent);
    xhs_top_nav(home_page);
    xhs_category_bar(home_page);

    feed = lv_obj_create(home_page);
    lv_obj_set_pos(feed, 0, 76);
    lv_obj_set_size(feed, XHS_SCREEN_W, 418);
    lv_obj_set_style_bg_color(feed, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(feed, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(feed, 0, 0);
    lv_obj_set_style_radius(feed, 0, 0);
    lv_obj_set_style_pad_all(feed, 0, 0);
    lv_obj_set_scroll_dir(feed, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(feed, LV_SCROLLBAR_MODE_OFF);
    lv_obj_set_scroll_snap_y(feed, LV_SCROLL_SNAP_NONE);
    lv_obj_set_name(feed, "feed");

    xhs_category_panel_create(home_page);

    lv_obj_update_layout(home_page);
    lv_obj_align_to(tab_underline, tab_labels[active_tab],
                    LV_ALIGN_OUT_BOTTOM_MID, 0, 2);
    xhs_build_feed();
    return home_page;
}


static void xhs_detail_like_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    xhs_note_t * note = &xhs_notes[index];
    note->liked = !note->liked;
    note->likes += note->liked ? 1 : -1;
    if(detail_like_icon != NULL) {
        lv_image_set_src(detail_like_icon,
                         note->liked ? xhs_icon(XHS_ICON_HEART_FILLED)
                                     : xhs_icon(XHS_ICON_HEART_OUTLINE));
    }
    if(detail_like_label != NULL) {
        char buffer[12];
        snprintf(buffer, sizeof(buffer), "%d", note->likes);
        lv_label_set_text(detail_like_label, buffer);
    }
    xhs_home_sync_likes();
    printf("[xhs] like note=%d liked=%d count=%d\n",
           index, note->liked ? 1 : 0, note->likes);
}

static void xhs_detail_collect_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    xhs_note_t * note = &xhs_notes[index];
    note->collected = !note->collected;
    note->collects += note->collected ? 1 : -1;
    if(detail_collect_icon != NULL) {
        lv_image_set_src(detail_collect_icon,
                         note->collected ? xhs_icon(XHS_ICON_STAR_FILLED)
                                         : xhs_icon(XHS_ICON_STAR));
    }
    if(detail_collect_label != NULL) {
        char buffer[12];
        snprintf(buffer, sizeof(buffer), "%d", note->collects);
        lv_label_set_text(detail_collect_label, buffer);
    }
    printf("[xhs] collect note=%d collected=%d count=%d\n",
           index, note->collected ? 1 : 0, note->collects);
}

static void xhs_detail_more_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] detail more clicked\n");
    }
}

static void xhs_detail_input_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] detail comment input clicked\n");
    }
}

static void xhs_detail_comment_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] detail comment icon clicked\n");
    }
}

static void xhs_detail_build(lv_obj_t * page, int index)
{
    lv_obj_clean(page);
    xhs_note_t * note = &xhs_notes[index];

    lv_obj_t * back = xhs_image(page, XHS_ICON_BACK, 12, 13);
    xhs_clickable(back, "detail_back");
    lv_obj_set_ext_click_area(back, 8);
    lv_obj_add_event_cb(back, xhs_back_event_cb, LV_EVENT_CLICKED, NULL);

    xhs_avatar(page, 42, 10, 24, note->avatar_color, note->avatar,
               XHS_FT_11);
    lv_obj_t * author = xhs_label_at(page, note->author, XHS_FT_12B,
                                     XHS_TEXT, 72, 13, 128, 18);
    lv_label_set_long_mode(author, LV_LABEL_LONG_MODE_DOTS);
    xhs_follow_chip(page, note, index, 208, 12);

    lv_obj_t * more = xhs_image(page, XHS_ICON_MORE, 272, 18);
    xhs_clickable(more, "detail_more");
    lv_obj_set_ext_click_area(more, 8);
    lv_obj_add_event_cb(more, xhs_detail_more_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * top_line = xhs_box(page, 0, 43, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(top_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(top_line, LV_OPA_COVER, 0);

    lv_obj_t * content = xhs_scroll(page, 0, 44, XHS_SCREEN_W, 452);
    lv_obj_set_name(content, "detail_content");

    int cover_h = xhs_cover_height(note->cover_index);
    xhs_cover_scaled(content, note->cover_index, 200, 152, 10);
    int cover_bottom = 10 + cover_h * 2;

    lv_point_t title_size;
    lv_text_get_size(&title_size, note->title, xhs_font(XHS_FT_14B),
                     0, 2, 272, LV_TEXT_FLAG_NONE);
    lv_obj_t * title = xhs_label(content, note->title, XHS_FT_14B, XHS_TITLE);
    lv_obj_set_pos(title, 16, cover_bottom + 12);
    lv_obj_set_width(title, 272);
    lv_label_set_long_mode(title, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_style_text_line_space(title, 2, 0);

    lv_point_t body_size;
    lv_text_get_size(&body_size, note->body, xhs_font(XHS_FT_13),
                     0, 2, 272, LV_TEXT_FLAG_NONE);
    int body_y = cover_bottom + 12 + title_size.y + 10;
    lv_obj_t * body = xhs_label(content, note->body, XHS_FT_13, XHS_TEXT);
    lv_obj_set_pos(body, 16, body_y);
    lv_obj_set_width(body, 272);
    lv_label_set_long_mode(body, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_style_text_line_space(body, 2, 0);

    int tag_y = body_y + body_size.y + 8;
    lv_obj_t * tag = xhs_label(content, note->tag, XHS_FT_12, 0x3C7DF2);
    lv_obj_set_pos(tag, 16, tag_y);

    int meta_y = tag_y + 22;
    xhs_image(content, XHS_ICON_LOCATION, 16, meta_y);
    char meta[128];
    snprintf(meta, sizeof(meta), "%s · %s", note->location,
             XHS_TXT_DETAIL_EDITED);
    lv_obj_t * meta_label = xhs_label_at(content, meta, XHS_FT_11, XHS_MUTED,
                                         32, meta_y + 1, 256, 16);
    lv_label_set_long_mode(meta_label, LV_LABEL_LONG_MODE_DOTS);

    int divider_y = meta_y + 28;
    lv_obj_t * divider = xhs_box(content, 16, divider_y, 272, 1);
    lv_obj_set_style_bg_color(divider, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);

    int comments = 32 + index * 7;
    char header[32];
    snprintf(header, sizeof(header), XHS_TXT_DETAIL_COMMENTS, comments);
    lv_obj_t * comments_title = xhs_label_at(content, header, XHS_FT_12B,
                                             XHS_TEXT, 16, divider_y + 14,
                                             200, 18);

    int row_y = divider_y + 40;
    for(int i = 0; i < 3; i++) {
        xhs_avatar(content, 16, row_y, 28, comment_colors[i],
                   comment_initials[i], XHS_FT_11);
        lv_obj_t * name = xhs_label_at(content, comment_names[i],
                                       XHS_FT_11, XHS_MUTED,
                                       52, row_y + 1, 160, 16);
        (void)name;
        lv_obj_t * text = xhs_label_at(content, comment_texts[i],
                                       XHS_FT_12, XHS_TEXT,
                                       52, row_y + 19, 220, 18);
        lv_label_set_long_mode(text, LV_LABEL_LONG_MODE_DOTS);
        xhs_image(content, XHS_ICON_HEART_OUTLINE, 270, row_y + 4);
        row_y += 54;
    }
    (void)comments_title;

    xhs_box(content, 0, row_y + 8, 1, 1);

    lv_obj_t * bar = xhs_box(page, 0, 496, XHS_SCREEN_W, 44);
    lv_obj_set_style_bg_color(bar, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_t * bar_line = xhs_box(bar, 0, 0, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(bar_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(bar_line, LV_OPA_COVER, 0);

    lv_obj_t * input = xhs_pill(bar, 12, 8, 156, 28, XHS_SOFT,
                                XHS_TXT_DETAIL_INPUT, XHS_FT_11, XHS_MUTED,
                                14);
    xhs_clickable(input, "detail_input");
    lv_obj_add_event_cb(input, xhs_detail_input_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * like = xhs_box(bar, 176, 6, 44, 32);
    xhs_clickable(like, "detail_like");
    lv_obj_add_event_cb(like, xhs_detail_like_cb, LV_EVENT_CLICKED,
                        (void *)(intptr_t)index);
    detail_like_icon = xhs_image(like,
                                 note->liked ? XHS_ICON_HEART_FILLED
                                             : XHS_ICON_HEART_OUTLINE,
                                 0, 9);
    detail_like_label = xhs_label_at(like, "", XHS_FT_11, XHS_META,
                                     17, 9, 26, 16);
    char likes[12];
    snprintf(likes, sizeof(likes), "%d", note->likes);
    lv_label_set_text(detail_like_label, likes);

    lv_obj_t * collect = xhs_box(bar, 222, 6, 40, 32);
    xhs_clickable(collect, "detail_collect");
    lv_obj_add_event_cb(collect, xhs_detail_collect_cb, LV_EVENT_CLICKED,
                        (void *)(intptr_t)index);
    detail_collect_icon = xhs_image(collect,
                                    note->collected ? XHS_ICON_STAR_FILLED
                                                    : XHS_ICON_STAR, 0, 9);
    detail_collect_label = xhs_label_at(collect, "", XHS_FT_11, XHS_META,
                                        17, 9, 20, 16);
    char collects[12];
    snprintf(collects, sizeof(collects), "%d", note->collects);
    lv_label_set_text(detail_collect_label, collects);

    lv_obj_t * comment = xhs_box(bar, 266, 6, 34, 32);
    xhs_clickable(comment, "detail_comment");
    lv_obj_add_event_cb(comment, xhs_detail_comment_cb, LV_EVENT_CLICKED, NULL);
    xhs_image(comment, XHS_ICON_COMMENT, 2, 9);
}

void xhs_note_open(int index)
{
    if(index < 0 || index >= XHS_NOTE_COUNT) return;
    if(note_overlay == NULL) {
        note_overlay = xhs_page(xhs_overlay_host());
    }
    xhs_detail_build(note_overlay, index);
    xhs_open_overlay(note_overlay);
    printf("[xhs] note open index=%d\n", index);
}

#endif
