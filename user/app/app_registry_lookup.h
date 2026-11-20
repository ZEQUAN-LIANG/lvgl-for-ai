/* Registry lookup shared by user/app/app.c and scripts/release_app.c so the two
 * entrypoints stay in sync. The build writes ``app_registry.inc`` from the app
 * directories under ``user/app/``; include this inside the caller's version
 * gate, since the .inc only exists after the build generated it. */

#ifndef LVGL_VERIFY_LOOP_APP_REGISTRY_LOOKUP_H
#define LVGL_VERIFY_LOOP_APP_REGISTRY_LOOKUP_H

#include <stdio.h>
#include <string.h>

typedef void (*app_create_fn)(void);

typedef struct {
    const char * name;
    app_create_fn create;
} app_entry_t;

#include "app_registry.inc"

#define APP_COUNT (sizeof(apps) / sizeof(apps[0]))

static inline const app_entry_t * app_find(const char * name)
{
    size_t index;
    for(index = 0; index < APP_COUNT; index++) {
        if(strcmp(name, apps[index].name) == 0) {
            return &apps[index];
        }
    }
    return NULL;
}

static inline void app_print_apps(void)
{
    size_t index;
    printf("[app] apps=");
    for(index = 0; index < APP_COUNT; index++) {
        printf("%s%s", index == 0 ? "" : ",", apps[index].name);
    }
    printf("\n");
}

#endif /* LVGL_VERIFY_LOOP_APP_REGISTRY_LOOKUP_H */
