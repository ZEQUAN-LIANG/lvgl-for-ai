#ifndef C6_DEMO_H
#define C6_DEMO_H

#include <stdbool.h>
#include <stddef.h>

#include "lvgl.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

void c6_demo_create(void);

/* Page control for the serial host.  Call these from the LVGL task, or wrap
 * them in lvgl_port_lock()/lvgl_port_unlock() on the target. */
bool c6_demo_page_show(const char * name);
bool c6_demo_page_next(void);
bool c6_demo_page_prev(void);
const char * c6_demo_page_current(void);
size_t c6_demo_page_count(void);
const char * c6_demo_page_name(size_t index);

#endif

#endif
