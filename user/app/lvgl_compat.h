#ifndef LVGL_COMPAT_H
#define LVGL_COMPAT_H

#include "lvgl.h"

#if LVGL_VERSION_MAJOR < 9

static inline lv_obj_t * lv_screen_active(void)
{
    return lv_scr_act();
}

static inline lv_obj_t * lv_image_create(lv_obj_t * parent)
{
    return lv_img_create(parent);
}

static inline void lv_image_set_src(lv_obj_t * obj, const void * src)
{
    lv_img_set_src(obj, src);
}

static inline lv_obj_t * lv_button_create(lv_obj_t * parent)
{
    return lv_btn_create(parent);
}

#endif

static inline void app_image_set_recolor(lv_obj_t * obj, lv_color_t color,
                                         lv_opa_t opa)
{
#if LVGL_VERSION_MAJOR >= 9
    lv_obj_set_style_image_recolor(obj, color, 0);
    lv_obj_set_style_image_recolor_opa(obj, opa, 0);
#else
    lv_obj_set_style_img_recolor(obj, color, 0);
    lv_obj_set_style_img_recolor_opa(obj, opa, 0);
#endif
}

#endif
