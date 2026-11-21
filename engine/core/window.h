#ifndef WINDOW_H
#define WINDOW_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    WINDOW_EVENT_POINTER = 0,
    WINDOW_EVENT_KEY = 1,
} window_event_kind_t;

typedef enum {
    WINDOW_POINTER_DOWN = 0,
    WINDOW_POINTER_MOVE = 1,
    WINDOW_POINTER_UP = 2,
} window_pointer_action_t;

typedef struct {
    window_event_kind_t kind;
    int32_t x;
    int32_t y;
    window_pointer_action_t action;
    bool pressed;
    uint32_t key;
    const char * key_name;
} window_event_t;

typedef void (*window_input_cb)(void * user, const window_event_t * event);

typedef struct window window_t;

bool window_available(void);

window_t * window_create(uint32_t width, uint32_t height, const char * title,
                         window_input_cb callback, void * user);

void window_destroy(window_t * window);

bool window_pump(window_t * window);

void window_present(window_t * window, const uint8_t * framebuffer);

void window_install_ctrl_handler(void);

bool window_console_interrupted(void);

#ifdef __cplusplus
}
#endif

#endif
