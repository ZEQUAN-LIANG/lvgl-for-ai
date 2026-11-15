#ifndef APP_H
#define APP_H

#include <stdbool.h>

#include "lvgl.h"
#include "lvgl_compat.h"

/* Version differences stay inside user/app. Names exist from LVGL 9.2; 9.1
 * and 8.x have neither the API nor LV_USE_OBJ_NAME, so the tool reports
 * hit_class only. Branches on LVGL_VERSION_MAJOR / LVGL_VERSION_MINOR keep
 * this file compiling against every target version without a tool-side
 * registry. */
static inline void app_obj_set_name(lv_obj_t * obj, const char * name)
{
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 2
    lv_obj_set_name(obj, name);
#else
    (void)obj;
    (void)name;
#endif
}

static inline void app_set_name(const char * name)
{
    app_obj_set_name(lv_screen_active(), name);
}

static inline const char * app_get_name(const lv_obj_t * obj)
{
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 2
    return lv_obj_get_name(obj);
#else
    (void)obj;
    return NULL;
#endif
}

/* 9.6 introduced dedicated flag setters; 9.4/9.5 and 8.x keep add/clear. */
static inline void app_obj_set_scrollable(lv_obj_t * obj, bool en)
{
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
    lv_obj_set_scrollable(obj, en);
#elif LVGL_VERSION_MAJOR >= 9
    if(en) {
        lv_obj_add_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
    }
    else {
        lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
    }
#else
    if(en) {
        lv_obj_add_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
    }
    else {
        lv_obj_clear_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
    }
#endif
}

static inline void app_obj_set_clickable(lv_obj_t * obj, bool en)
{
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
    lv_obj_set_clickable(obj, en);
#elif LVGL_VERSION_MAJOR >= 9
    if(en) {
        lv_obj_add_flag(obj, LV_OBJ_FLAG_CLICKABLE);
    }
    else {
        lv_obj_remove_flag(obj, LV_OBJ_FLAG_CLICKABLE);
    }
#else
    if(en) {
        lv_obj_add_flag(obj, LV_OBJ_FLAG_CLICKABLE);
    }
    else {
        lv_obj_clear_flag(obj, LV_OBJ_FLAG_CLICKABLE);
    }
#endif
}

static inline void app_obj_set_hidden(lv_obj_t * obj, bool en)
{
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
    lv_obj_set_hidden(obj, en);
#elif LVGL_VERSION_MAJOR >= 9
    if(en) {
        lv_obj_add_flag(obj, LV_OBJ_FLAG_HIDDEN);
    }
    else {
        lv_obj_remove_flag(obj, LV_OBJ_FLAG_HIDDEN);
    }
#else
    if(en) {
        lv_obj_add_flag(obj, LV_OBJ_FLAG_HIDDEN);
    }
    else {
        lv_obj_clear_flag(obj, LV_OBJ_FLAG_HIDDEN);
    }
#endif
}

void app_panel_create(void);
lv_obj_t * app_panel_get(void);

void demo_harness_create(bool visible);

#endif
