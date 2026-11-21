#include "lvgl.h"

#include "app.h"

#include <stdio.h>
#include <stdlib.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4
#include "app_registry_lookup.h"
#endif

void app_create(void)
{
    printf("[app] app_create\n");

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4
    const char * requested = getenv("LVGL_VERIFY_LOOP_DEMO");
    const char * name =
        (requested == NULL || requested[0] == '\0') ? apps[0].name : requested;
    const app_entry_t * app = app_find(name);

    app_print_apps();
    if(app == NULL) {
        printf("[app] unknown app=%s\n", requested);
        fflush(stdout);
        exit(1);
    }

    printf("[app] app=%s\n", app->name);
    app->create();
#else
    printf("[app] app=none (LVGL < 9.4)\n");
#endif
}
