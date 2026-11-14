/**
 * @file app.c
 * Release-package entry point: only the intro app is registered.
 *
 * The development tree keeps the full ``apps[]`` table and the hidden demo
 * harness in ``user/app/app.c``. ``release.py`` copies this file instead so
 * the distributable skill stays intro-only and can run on LVGL 9.4+ without
 * shipping the other app variants.
 */

#include "lvgl.h"
#include "intro/intro.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4
typedef void (* app_create_fn)(void);

typedef struct {
    const char * name;
    app_create_fn create;
} app_entry_t;

static const app_entry_t apps[] = {
    {"intro", intro_create},
};

#define APP_COUNT (sizeof(apps) / sizeof(apps[0]))

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

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4
    const char * requested = getenv("LVGL_AI_DEMO");
    const char * name = (requested == NULL || requested[0] == '\0')
                        ? apps[0].name
                        : requested;
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
    printf("[app] app=harness (LVGL < 9.4)\n");
#endif
}
