/**
 * @file app.c
 * The user entry point: lvgl_engine calls exactly this function.
 *
 * LVGL 9.6 starts the AURELIA C9 coffee machine by default. LVGL_AI_DEMO selects
 * the app variant: coffee (default), xiaohongshu (alias xhs), spectrum or
 * hspi_watch. The CLI and
 * web set it from a scenario's "app" field, so the same value is recorded in
 * the session manifest. The original demo tree is always created but hidden,
 * because the tool's integration tests target its named button; older LVGL
 * targets show that demo as-is.
 *
 * Every app exposes the same ``void create(lv_obj_t * screen)`` entry. Adding
 * an app means one row in ``apps`` plus its implementation; the tool layer
 * never learns app names.
 */

#include "lvgl.h"

#include "app.h"
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
#include "coffee/coffee_ui.h"
#include "xiaohongshu/xhs_page.h"
#include "spectrum/spectrum.h"
#include "hspi_watch/hspi_watch.h"
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
typedef void (* app_create_fn)(lv_obj_t * screen);

typedef struct {
    const char * name;
    app_create_fn create;
} app_entry_t;

static const app_entry_t apps[] = {
    {"coffee", coffee_create},
    {"xiaohongshu", xhs_page_create},
    {"spectrum", spectrum_create},
    {"hspi_watch", hspi_watch_create},
};

#define APP_COUNT (sizeof(apps) / sizeof(apps[0]))

static const char * app_canonical(const char * name)
{
    return strcmp(name, "xhs") == 0 ? "xiaohongshu" : name;
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
    const char * requested = getenv("LVGL_AI_DEMO");
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

    /* The original demo tree stays transparent behind every app because the
     * tool's integration tests target its named button. */
    demo_harness_create(false);
    printf("[app] app=%s\n", app->name);
    app->create(lv_screen_active());
#else
    printf("[app] app=harness (LVGL < 9.6)\n");
    demo_harness_create(true);
#endif

    printf("[demo_asset] font=demo_asset_font_8 image=demo_asset_logo\n");
}
