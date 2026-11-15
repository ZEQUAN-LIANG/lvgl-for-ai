/**
 * @file window.h
 * Platform window layer for the engine.
 *
 * Only the engine's main thread pumps the window and calls into this layer.
 * The Win32 implementation (window.c) owns the GDI window, forwards real
 * mouse/keyboard input as events and paints the complete LVGL framebuffer.
 * Other platforms compile the same interface as a stub; window_create()
 * then returns NULL and the caller stays headless.
 */

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
    /** Pointer events: client coordinates, already clamped to the display. */
    int32_t x;
    int32_t y;
    /** Pointer events: down, move or up. */
    window_pointer_action_t action;
    /** Pointer events: left button held after the event. */
    bool pressed;
    /** Key events: LVGL key code and canonical name (e.g. "ENTER"). */
    uint32_t key;
    const char * key_name;
} window_event_t;

typedef void (*window_input_cb)(void * user, const window_event_t * event);

typedef struct window window_t;

bool window_available(void);

/**
 * Create and show a fixed-size window with an ``width`` x ``height`` client
 * area. ``title`` is UTF-8. ``callback`` runs on the pumping thread for every
 * real input event. Returns NULL when the platform has no window support or
 * creation fails.
 */
window_t * window_create(uint32_t width, uint32_t height, const char * title,
                         window_input_cb callback, void * user);

void window_destroy(window_t * window);

/**
 * Process all pending window messages without blocking.
 * Returns false once WM_CLOSE has been received.
 */
bool window_pump(window_t * window);

/**
 * Paint ``framebuffer`` (XRGB8888, row-major, top-down) into the client area
 * immediately.
 */
void window_present(window_t * window, const uint8_t * framebuffer);

/**
 * Install the console Ctrl+C handler used by the window main loop. The
 * handler only sets a flag; window_console_interrupted() reports it.
 * No-op on platforms without a console handler.
 */
void window_install_ctrl_handler(void);

bool window_console_interrupted(void);

#ifdef __cplusplus
}
#endif

#endif
