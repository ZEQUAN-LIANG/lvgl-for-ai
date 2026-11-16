#include "intro.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "intro_ui.h"

void intro_create(void)
{
    intro_ui_create();
}

#endif
