/**
 * @file lvgl_compat.h
 * Minimal 8.x shims so shared user code can keep the 9.x spelling.
 *
 * Version differences stay inside user/app; the engine and the tool never see
 * this header. app.c includes it through app.h.
 */

#ifndef LVGL_COMPAT_H
#define LVGL_COMPAT_H

#include "lvgl.h"

#if LVGL_VERSION_MAJOR < 9

/* 9.x renamed lv_scr_act() to lv_screen_active(). */
static inline lv_obj_t * lv_screen_active(void)
{
    return lv_scr_act();
}

/* 9.x renamed the lv_img_* constructor and setter to lv_image_*. */
static inline lv_obj_t * lv_image_create(lv_obj_t * parent)
{
    return lv_img_create(parent);
}

static inline void lv_image_set_src(lv_obj_t * obj, const void * src)
{
    lv_img_set_src(obj, src);
}

#endif /* LVGL_VERSION_MAJOR < 9 */

#endif /* LVGL_COMPAT_H */
