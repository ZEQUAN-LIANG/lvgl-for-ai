#ifndef APP_H
#define APP_H

#include <stdbool.h>

#include "lvgl.h"

static inline void app_obj_set_name(lv_obj_t * obj, const char * name)
{
    (void)obj;
    (void)name;
}

static inline void app_obj_set_scrollable(lv_obj_t * obj, bool en)
{
    lv_obj_set_scrollable(obj, en);
}

#endif
