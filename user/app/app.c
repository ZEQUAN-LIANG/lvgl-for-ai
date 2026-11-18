
#include "lvgl.h"

#include "app.h"
#include "asset_probe/asset_probe.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
typedef void (*app_create_fn)(void);

typedef struct {
    const char * name;
    app_create_fn create;
} app_entry_t;

typedef struct {
    const char * alias;
    const char * name;
} app_alias_t;

/* The build writes app_registry.inc from user/app/<name>/app.json. */
#include "app_registry.inc"

#define APP_COUNT (sizeof(apps) / sizeof(apps[0]))

static const char * app_canonical(const char * name)
{
#if APP_ALIAS_COUNT > 0
    size_t index;
    for(index = 0; index < APP_ALIAS_COUNT; index++) {
        if(strcmp(name, app_aliases[index].alias) == 0) {
            return app_aliases[index].name;
        }
    }
#endif
    return name;
}

static const app_entry_t * app_find(const char * name)
{
    size_t index;
    for(index = 0; index < APP_COUNT; index++) {
        if(strcmp(name, apps[index].name) == 0) {
            return &apps[index];
        }
    }
    return NULL;
}

static void app_print_apps(void)
{
    size_t index;
    printf("[app] apps=");
    for(index = 0; index < APP_COUNT; index++) {
        printf("%s%s", index == 0 ? "" : ",", apps[index].name);
    }
    printf("\n");
}
#endif

void app_create(void)
{
    printf("[app] app_create\n");

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
    const char * requested = getenv("LVGL_VERIFY_LOOP_DEMO");
    const char * name = (requested == NULL || requested[0] == '\0')
                            ? apps[0].name
                            : app_canonical(requested);
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
