#include "zombie_cannon.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include "app.h"
#include "sift_watch/game/zc_game.h"

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

static uint16_t * s_fb;
static uint16_t * s_bg;
static lv_obj_t * s_canvas;
static lv_timer_t * s_timer;
static lv_group_t * s_group;
static uint32_t s_last_tick;
static int s_w;
static int s_h;
static bool s_pressed;
static bool s_ready;

static bool canvas_point(lv_event_t * event, int * x, int * y)
{
    (void)event;
    lv_indev_t * indev = lv_indev_active();
    if(indev == NULL || s_canvas == NULL) return false;
    lv_point_t point;
    lv_indev_get_point(indev, &point);
    lv_area_t area;
    lv_obj_get_coords(s_canvas, &area);
    *x = point.x - area.x1;
    *y = point.y - area.y1;
    return *x >= 0 && *x < s_w && *y >= 0 && *y < s_h;
}

static void zc_timer_cb(lv_timer_t * timer)
{
    (void)timer;
    if(!s_ready) return;
    uint32_t now = lv_tick_get();
    uint32_t elapsed = now - s_last_tick;
    s_last_tick = now;
    zc_tick(now, elapsed);
    zc_render();
    if(s_canvas != NULL) lv_obj_invalidate(s_canvas);
}

static void zc_event_cb(lv_event_t * event)
{
    lv_event_code_t code = lv_event_get_code(event);
    if(code == LV_EVENT_KEY) {
        zc_key(lv_event_get_key(event));
        return;
    }
    if(code == LV_EVENT_DELETE) {
        if(s_timer != NULL) {
            lv_timer_delete(s_timer);
            s_timer = NULL;
        }
        zc_destroy();
        if(s_fb != NULL) {
            lv_free(s_fb);
            s_fb = NULL;
        }
        if(s_bg != NULL) {
            lv_free(s_bg);
            s_bg = NULL;
        }
        s_ready = false;
        return;
    }
    if(code == LV_EVENT_PRESSED) {
        int x;
        int y;
        if(!canvas_point(event, &x, &y)) return;
        s_pressed = true;
        zc_pointer(ZC_POINTER_DOWN, x, y);
        return;
    }
    if(code == LV_EVENT_PRESSING) {
        if(!s_pressed) return;
        int x;
        int y;
        if(canvas_point(event, &x, &y)) zc_pointer(ZC_POINTER_MOVE, x, y);
        return;
    }
    if(code == LV_EVENT_RELEASED) {
        int x = 0;
        int y = 0;
        bool has = canvas_point(event, &x, &y);
        s_pressed = false;
        zc_pointer(has ? ZC_POINTER_UP : ZC_POINTER_CANCEL, x, y);
        return;
    }
    if(code == LV_EVENT_PRESS_LOST) {
        s_pressed = false;
        zc_pointer(ZC_POINTER_CANCEL, 0, 0);
    }
}

void zombie_cannon_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    lv_display_t * display = lv_display_get_default();
    int32_t screen_w =
        display != NULL ? lv_display_get_horizontal_resolution(display) : 390;
    int32_t screen_h =
        display != NULL ? lv_display_get_vertical_resolution(display) : 460;
    s_w = screen_w < 390 ? (int)screen_w : 390;
    s_h = screen_h < 460 ? (int)screen_h : 460;

    app_set_name("zombie_cannon");
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x080B07), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);

    s_fb = (uint16_t *)lv_malloc((size_t)s_w * (size_t)s_h * sizeof(uint16_t));
    s_bg = (uint16_t *)lv_malloc((size_t)s_w * (size_t)s_h * sizeof(uint16_t));
    if(s_fb == NULL || s_bg == NULL) {
        lv_obj_t * error = lv_label_create(screen);
        lv_label_set_text(error, "zombie_cannon framebuffer allocation failed");
        lv_obj_center(error);
        printf("[zombie_cannon] framebuffer allocation failed\n");
        if(s_fb != NULL) lv_free(s_fb);
        if(s_bg != NULL) lv_free(s_bg);
        s_fb = NULL;
        s_bg = NULL;
        return;
    }
    memset(s_fb, 0, (size_t)s_w * (size_t)s_h * sizeof(uint16_t));
    memset(s_bg, 0, (size_t)s_w * (size_t)s_h * sizeof(uint16_t));

    s_canvas = lv_canvas_create(screen);
    if(s_canvas == NULL) {
        lv_free(s_fb);
        lv_free(s_bg);
        s_fb = NULL;
        s_bg = NULL;
        printf("[zombie_cannon] canvas creation failed\n");
        return;
    }
    app_obj_set_name(s_canvas, "zombie_cannon_canvas");
    lv_obj_set_size(s_canvas, s_w, s_h);
    lv_obj_set_pos(s_canvas, (screen_w - s_w) / 2, (screen_h - s_h) / 2);
    lv_obj_set_style_pad_all(s_canvas, 0, 0);
    lv_obj_set_style_border_width(s_canvas, 0, 0);
    lv_obj_set_style_bg_opa(s_canvas, LV_OPA_TRANSP, 0);
    lv_obj_set_style_radius(s_canvas, 0, 0);
    lv_obj_remove_flag(s_canvas, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(s_canvas, LV_OBJ_FLAG_CLICKABLE);
    lv_canvas_set_buffer(s_canvas, s_fb, s_w, s_h, LV_COLOR_FORMAT_RGB565);
    lv_obj_add_event_cb(s_canvas, zc_event_cb, LV_EVENT_ALL, NULL);

    s_group = lv_group_create();
    lv_group_add_obj(s_group, s_canvas);
    lv_group_focus_obj(s_canvas);
    lv_indev_t * indev = NULL;
    while((indev = lv_indev_get_next(indev)) != NULL) {
        lv_indev_type_t type = lv_indev_get_type(indev);
        if(type == LV_INDEV_TYPE_KEYPAD || type == LV_INDEV_TYPE_ENCODER) {
            lv_indev_set_group(indev, s_group);
        }
    }

    zc_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.width = s_w;
    cfg.height = s_h;
    cfg.safe_inset = 0;
    cfg.embedded = false;
    cfg.show_scanlines = true;
    cfg.hooks = NULL;
    if(!zc_create(s_fb, s_bg, &cfg)) {
        printf("[zombie_cannon] zc_create failed\n");
        return;
    }
    zc_enter();
    s_ready = true;
    s_last_tick = lv_tick_get();
    zc_render();
    lv_obj_invalidate(s_canvas);

    s_timer = lv_timer_create(zc_timer_cb, 33, NULL);
    printf("[zombie_cannon] created display=%ldx%ld game=%dx%d\n",
           (long)screen_w, (long)screen_h, s_w, s_h);
}

#endif
