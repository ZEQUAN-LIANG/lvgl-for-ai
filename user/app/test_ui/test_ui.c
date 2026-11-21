#include "test_ui.h"

#include <stdio.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "app.h"
#include "test_ui_assets.h"

static lv_obj_t * panel_obj;

void app_panel_create(void)
{
    printf("[app] panel_create\n");

    lv_obj_t * panel = lv_obj_create(lv_screen_active());
    panel_obj = panel;
    app_obj_set_name(panel, "panel");
    lv_obj_set_size(panel, 360, 160);
    lv_obj_set_pos(panel, 32, 96);
    lv_obj_set_style_bg_color(panel, lv_color_hex(0x1E293B), 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(panel, 0, 0);
    lv_obj_set_style_radius(panel, 12, 0);
    lv_obj_set_style_pad_all(panel, 16, 0);

    lv_obj_t * label = lv_label_create(panel);
    app_obj_set_name(label, "panel_label");
    lv_label_set_text(label, "lvgl_engine");
    lv_obj_set_style_text_color(label, lv_color_hex(0xE2E8F0), 0);
    lv_obj_set_style_text_font(label, &lv_font_montserrat_16, 0);
}

lv_obj_t * app_panel_get(void)
{
    return panel_obj;
}

static void button_event(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[app] test_ui_button clicked\n");
    }
}

static void focus_event(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_FOCUSED) return;
#if LVGL_VERSION_MAJOR >= 9
    lv_obj_t * obj = lv_event_get_target_obj(event);
#else
    lv_obj_t * obj = lv_event_get_target(event);
#endif
    const char * name = obj == NULL ? NULL : app_get_name(obj);
    printf("[app] %s focused\n", name != NULL ? name : "object");
}

static lv_obj_t * button_create(lv_obj_t * parent)
{
#if LVGL_VERSION_MAJOR >= 9
    lv_obj_t * button = lv_button_create(parent);
#else
    lv_obj_t * button = lv_btn_create(parent);
#endif
    app_obj_set_name(button, "test_ui_button");
    lv_obj_set_pos(button, 32, 300);
    lv_obj_set_size(button, 160, 48);
    lv_obj_add_event_cb(button, button_event, LV_EVENT_CLICKED, NULL);

    lv_obj_t * label = lv_label_create(button);
    lv_label_set_text(label, "Click");
    lv_obj_center(label);
    app_obj_set_clickable(label, false);
    return button;
}

static void group_create(lv_obj_t * panel, lv_obj_t * button, lv_obj_t * title)
{
    lv_group_t * group = lv_group_create();
    if(group == NULL) {
        printf("[app] focus group unavailable\n");
        return;
    }

    lv_group_add_obj(group, panel);
    lv_group_add_obj(group, button);
    lv_group_add_obj(group, title);
    lv_group_focus_obj(button);

    for(lv_indev_t * indev = lv_indev_get_next(NULL); indev != NULL;
        indev = lv_indev_get_next(indev)) {
        lv_indev_type_t type = lv_indev_get_type(indev);
        if(type == LV_INDEV_TYPE_KEYPAD || type == LV_INDEV_TYPE_ENCODER) {
            lv_indev_set_group(indev, group);
        }
    }
    printf("[app] focus group created\n");
}

void test_ui_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x0F172A), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    app_set_name("test_ui");

    test_ui_asset_prepare();
    lv_obj_t * logo = lv_image_create(screen);
    app_obj_set_name(logo, "logo");
    lv_image_set_src(logo, &test_ui_asset_logo);
    lv_obj_set_pos(logo, 32, 28);

    lv_obj_t * title = lv_label_create(screen);
    app_obj_set_name(title, "title");
    lv_label_set_text(title, "LAT");
    lv_obj_set_style_text_font(title, &test_ui_asset_font_8, 0);
    lv_obj_set_style_text_color(title, lv_color_hex(0x38BDF8), 0);
    lv_obj_set_pos(title, 68, 32);

    app_panel_create();
    lv_obj_t * panel = app_panel_get();
    lv_obj_t * button = button_create(screen);
    lv_obj_add_event_cb(panel, focus_event, LV_EVENT_FOCUSED, NULL);
    lv_obj_add_event_cb(button, focus_event, LV_EVENT_FOCUSED, NULL);
    lv_obj_add_event_cb(title, focus_event, LV_EVENT_FOCUSED, NULL);
    group_create(panel, button, title);
}

#else

void test_ui_create(void)
{
    printf("[app] test_ui needs LVGL 9.4+\n");
}

#endif
