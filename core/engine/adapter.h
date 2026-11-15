#ifndef ADAPTER_H
#define ADAPTER_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct adapter adapter_t;

typedef struct {
    uint32_t width;
    uint32_t height;
    const char * lvgl_version; /**< e.g. "9.6.0" */
    const char * lvgl_src; /**< exact source tree this adapter was built from */
    const char * adapter_name; /**< e.g. "9x" */
} adapter_info_t;

typedef enum {
    POINTER_DOWN = 0,
    POINTER_MOVE = 1,
    POINTER_UP = 2,
} pointer_action_t;

typedef struct {
    int32_t x;
    int32_t y;
    const char * hit;       /**< Object name, "" when unnamed or no hit. */
    const char * hit_class; /**< e.g. "lv_button", "" when no hit. */
} pointer_reply_t;

typedef enum {
    KEY_PRESS = 0,
    KEY_RELEASE = 1,
} key_action_t;

/**
 * Create LVGL, the display and the standard virtual pointer, keypad and
 * encoder indevs. When ``real_input`` is true, standard pointer and keypad
 * indevs for OS input are created too, so real and virtual input never share
 * device state. No focus group is created: groups belong to user/app.
 */
adapter_t * adapter_create(uint32_t width, uint32_t height, bool real_input);

void adapter_destroy(adapter_t * adapter);

const adapter_info_t * adapter_info(const adapter_t * adapter);

void adapter_refresh(adapter_t * adapter);

bool adapter_last_refresh_painted(const adapter_t * adapter);

/**
 * Inject one pointer action into the standard virtual pointer indev and let
 * LVGL process it. The hit test runs before delivery, so the reply names the
 * object under the point even if the event handler deletes it.
 */
int adapter_pointer(adapter_t * adapter, pointer_action_t action, int32_t x,
                    int32_t y);

const pointer_reply_t * adapter_last_pointer(const adapter_t * adapter);

/**
 * Feed one real (OS) pointer action into the real pointer indev and process
 * it immediately. Kept separate from the virtual pointer so AI input and a
 * human mouse never overwrite each other. Returns 0 when the real indev
 * exists.
 */
int adapter_real_pointer(adapter_t * adapter, pointer_action_t action,
                         int32_t x, int32_t y);

const pointer_reply_t * adapter_last_real_pointer(const adapter_t * adapter);

/**
 * Deliver one real (OS) key press/release to the real keypad indev. The state
 * is kept even when LVGL blocks the read so the next timer read can deliver
 * it. Returns 0 when LVGL read the indev, -1 otherwise.
 */
int adapter_real_key(adapter_t * adapter, key_action_t action, uint32_t key);

/**
 * Inject one key press/release into the standard virtual keypad indev and let
 * LVGL process it. Returns 0 only when LVGL actually read the indev; a
 * blocked or missing indev returns -1. The caller records ``delivered`` from
 * this return value, never from the intent to send.
 */
int adapter_key(adapter_t * adapter, key_action_t action, uint32_t key);

/**
 * Turn the standard virtual encoder indev by ``diff`` steps. Positive values
 * are LVGL's ``enc_diff > 0`` direction (focus forward). The diff is consumed
 * by one read; returns 0 only when LVGL actually read the indev.
 */
int adapter_encoder(adapter_t * adapter, int32_t diff);

void adapter_tick_inc(adapter_t * adapter, uint32_t ms);

void adapter_timer_handler(adapter_t * adapter);

/** Full framebuffer, XRGB8888, row-major, width * height * 4 bytes. */
const uint8_t * adapter_framebuffer(const adapter_t * adapter);

int adapter_save_png(const adapter_t * adapter, const char * path);

/**
 * Write the framebuffer as raw RGBA8888 bytes (R, G, B, A) for the live
 * preview stream. The file is width * height * 4 bytes with no header.
 * Returns 0 on success.
 */
int adapter_save_rgba(const adapter_t * adapter, const char * path);

/**
 * Decode a PNG into XRGB8888 pixels (same byte layout as the framebuffer).
 * On success the caller owns ``*pixels`` and releases it with
 * adapter_free_pixels(). Returns 0 on success.
 */
int adapter_load_png(const char * path, uint8_t ** pixels, uint32_t * width,
                     uint32_t * height);

void adapter_free_pixels(uint8_t * pixels);

#ifdef __cplusplus
}
#endif

#endif
