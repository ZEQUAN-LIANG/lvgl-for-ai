#ifndef TEST_UI_H
#define TEST_UI_H

#include "lvgl.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4
void test_ui_create(void);
#endif

#endif
