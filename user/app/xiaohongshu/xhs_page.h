#ifndef XHS_PAGE_H
#define XHS_PAGE_H

#include "lvgl.h"

/* Xiaohongshu replica shell, drawn inside a phone frame on the 800x600 engine
 * screen. Page modules live in xhs_*.c; only LVGL 9.6 implements it, and
 * app.c guards the call. */
void xhs_page_create(lv_obj_t * screen);

#endif /* XHS_PAGE_H */
