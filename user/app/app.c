
#include "lvgl.h"

#include "app.h"
#include "asset_probe/asset_probe.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
#include "app_registry_lookup.h"
#endif

void app_create(void)
{
    printf("[app] app_create\n");

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
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

    demo_harness_create(false);
    printf("[app] app=%s\n", app->name);
    app->create();
#else
    const char * requested = getenv("LVGL_VERIFY_LOOP_DEMO");
    if(requested != NULL && strcmp(requested, "asset_probe") == 0) {
        demo_harness_create(false);
        printf("[app] app=asset_probe (LVGL < 9.6)\n");
        asset_probe_create();
    }
    else {
        printf("[app] app=harness (LVGL < 9.6)\n");
        demo_harness_create(true);
    }
#endif

    printf("[demo_asset] font=demo_asset_font_8 image=demo_asset_logo\n");
}
