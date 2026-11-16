#include "lvgl.h"

#include "demo_feedback.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

static int click_count;

static void on_click(lv_event_t * event)
{
    lv_obj_t * title = lv_event_get_user_data(event);
    click_count++;
    lv_label_set_text_fmt(title, "Clicked %d", click_count);
}

void demo_feedback_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_scroll_to(screen, 0, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101820), 0);

    lv_obj_t * title = lv_label_create(screen);
    lv_label_set_text(title, "Feedback demo");
    lv_obj_set_style_text_color(title, lv_color_hex(0xffffff), 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 24);

    lv_obj_t * button = lv_button_create(screen);
    lv_obj_set_size(button, 180, 48);
    lv_obj_set_pos(button, 70, 120);
    lv_obj_set_style_bg_color(button, lv_color_hex(0x2f80ed), 0);
    lv_obj_add_event_cb(button, on_click, LV_EVENT_CLICKED, title);

    lv_obj_t * label = lv_label_create(button);
    lv_label_set_text(label, "Click me");
    lv_obj_center(label);
}

#else

void demo_feedback_create(void)
{
}

#endif
