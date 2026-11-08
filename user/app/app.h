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
static inline void app_set_name(lv_obj_t * obj, const char * name)
{
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 2
    lv_obj_set_name(obj, name);
#else
    (void)obj;
    (void)name;
#endif
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

/* Internal to user/app: app.c builds the screen and delegates the panel. */
lv_obj_t * app_panel_create(lv_obj_t * parent);

/* The original demo tree is kept because the tool's integration tests use its
 * named button at (32,300,160,48) as a stable hit target. On 9.6 the page is
 * hidden underneath the Xiaohongshu screen; older targets show it. */
void demo_harness_create(bool visible);

#endif /* APP_H */
