#include "intro.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "intro_ui.h"

void intro_create(void)
{
    idx_ui_create();
}

#endif /* LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4 */
