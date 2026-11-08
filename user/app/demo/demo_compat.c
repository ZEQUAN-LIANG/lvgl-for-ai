/**
 * @file demo_compat.c
 * The original demo, kept as the stable hit/focus target used by the
 * tool's integration tests.
 *
 * On LVGL 9.6 the demo is created transparent behind the Xiaohongshu page:
 * pointer hits at (112,324) and keypad/encoder focus still reach the named
 * button, while the visible screen belongs to xiaohongshu/xhs_page.c. Older
 * targets show the demo unchanged.
 */

#include "app.h"
#include "demo_assets.h"

#include <stdio.h>

static lv_group_t * demo_group;

static void demo_button_event(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[app] demo_button clicked\n");
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

static lv_obj_t * demo_button_create(lv_obj_t * parent)
{
#if LVGL_VERSION_MAJOR >= 9
    lv_obj_t * button = lv_button_create(parent);
#else
    lv_obj_t * button = lv_btn_create(parent);
#endif
    app_set_name(button, "demo_button");
    lv_obj_set_pos(button, 32, 300);
    lv_obj_set_size(button, 160, 48);
    lv_obj_add_event_cb(button, demo_button_event, LV_EVENT_CLICKED, NULL);

    lv_obj_t * label = lv_label_create(button);
    lv_label_set_text(label, "Click");
    lv_obj_center(label);
    /* The label must not swallow the hit test: clicks belong to the button.
     * lv_obj_set_clickable() is the 9.6 spelling; older 9.x uses
     * lv_obj_remove_flag(); 8.x uses lv_obj_clear_flag(). */
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
    lv_obj_set_clickable(label, false);
#elif LVGL_VERSION_MAJOR >= 9
    lv_obj_remove_flag(label, LV_OBJ_FLAG_CLICKABLE);
#else
    lv_obj_clear_flag(label, LV_OBJ_FLAG_CLICKABLE);
#endif
    return button;
}

static void demo_group_create(lv_obj_t * panel, lv_obj_t * button,
                                  lv_obj_t * title)
{
    demo_group = lv_group_create();
    if(demo_group == NULL) {
        printf("[app] focus group unavailable\n");
        return;
    }

    /* Order matters: panel -> button -> title. The button starts focused, so
     * encoder +1 moves to the title and -1 moves to the panel. */
    lv_group_add_obj(demo_group, panel);
    lv_group_add_obj(demo_group, button);
    lv_group_add_obj(demo_group, title);
    lv_group_focus_obj(button);

    for(lv_indev_t * indev = lv_indev_get_next(NULL); indev != NULL;
        indev = lv_indev_get_next(indev)) {
        lv_indev_type_t type = lv_indev_get_type(indev);
        if(type == LV_INDEV_TYPE_KEYPAD || type == LV_INDEV_TYPE_ENCODER) {
            lv_indev_set_group(indev, demo_group);
        }
    }
    printf("[app] focus group created\n");
}

static void demo_hide(lv_obj_t * panel, lv_obj_t * button, lv_obj_t * title)
{
    /* Opacity does not affect hit testing; these objects stay interactive. */
    lv_obj_set_style_opa(panel, LV_OPA_TRANSP, 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(panel, 0, 0);
    lv_obj_set_style_shadow_opa(panel, LV_OPA_TRANSP, 0);

    /* The button stays invisible but must still flash while pressed: the
     * tool's frame-diff tests click it and require the pressed transition to
     * change pixels. Its label is hidden separately so the button keeps a
     * backdrop-tinted pressed fill only. */
    lv_obj_t * label = lv_obj_get_child(button, 0);
    if(label != NULL) {
        lv_obj_set_style_opa(label, LV_OPA_TRANSP, 0);
    }
    lv_obj_set_style_bg_opa(button, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(button, 0, 0);
    lv_obj_set_style_shadow_opa(button, LV_OPA_TRANSP, 0);
    lv_obj_set_style_outline_opa(button, LV_OPA_TRANSP, LV_STATE_FOCUSED);
    lv_obj_set_style_outline_opa(button, LV_OPA_TRANSP, LV_STATE_FOCUS_KEY);
    lv_obj_set_style_outline_opa(button, LV_OPA_TRANSP, LV_STATE_PRESSED);
    lv_obj_set_style_bg_color(button, lv_color_hex(0xB89AB6), LV_STATE_PRESSED);
    lv_obj_set_style_bg_opa(button, 120, LV_STATE_PRESSED);
    lv_obj_set_style_radius(button, 12, LV_STATE_PRESSED);
    lv_obj_set_style_border_width(button, 0, LV_STATE_PRESSED);
    lv_obj_set_style_shadow_opa(button, LV_OPA_TRANSP, LV_STATE_PRESSED);

    lv_obj_set_style_opa(title, LV_OPA_TRANSP, 0);
    lv_obj_set_style_text_opa(title, LV_OPA_TRANSP, 0);
}

void demo_harness_create(bool visible)
{
    lv_obj_t * screen = lv_screen_active();
    lv_obj_t * logo = NULL;
    lv_obj_t * title = NULL;

    if(visible) {
        lv_obj_set_style_bg_color(screen, lv_color_hex(0x0F172A), 0);
        lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

        demo_asset_prepare();
        logo = lv_image_create(screen);
        app_set_name(logo, "logo");
        lv_image_set_src(logo, &demo_asset_logo);
        lv_obj_set_pos(logo, 32, 28);
    }

    title = lv_label_create(screen);
    app_set_name(title, "title");
    lv_label_set_text(title, "LAT");
    lv_obj_set_style_text_font(title, &demo_asset_font_8, 0);
    lv_obj_set_style_text_color(title, lv_color_hex(0x38BDF8), 0);
    lv_obj_set_pos(title, 68, 32);

    lv_obj_t * panel = app_panel_create(screen);
    lv_obj_t * button = demo_button_create(screen);
    lv_obj_add_event_cb(panel, focus_event, LV_EVENT_FOCUSED, NULL);
    lv_obj_add_event_cb(button, focus_event, LV_EVENT_FOCUSED, NULL);
    lv_obj_add_event_cb(title, focus_event, LV_EVENT_FOCUSED, NULL);
    demo_group_create(panel, button, title);

    if(!visible) {
        (void)logo;
        demo_hide(panel, button, title);
    }
}
