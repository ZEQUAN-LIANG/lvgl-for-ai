/**
 * @file adapter_internal.h
 * Internal seam between adapter_common.c and the LVGL 8.x / 9.x adapters.
 *
 * adapter_common.c owns everything that does not depend on the LVGL version:
 * the pointer/keypad/encoder state machines, hit reply buffers, framebuffer
 * to RGBA conversion, file IO, tick/timer forwarding, adapter_info and the
 * adapter lifecycle. Each adapter_<family>.c defines ``struct adapter`` with
 * ``adapter_common_t common`` as its first member and implements the
 * ``adapter_prim_*`` primitives below. The common file treats the opaque
 * adapter_t as that first member, so every version family must keep the
 * layout and enforce it with ``_Static_assert(offsetof(struct adapter,
 * common) == 0, ...)``.
 *
 * This header deliberately stays free of LVGL and lodepng headers: the
 * version boundary is still "only adapter_9x.c / adapter_8x.c include the
 * framework".
 */

#ifndef ADAPTER_INTERNAL_H
#define ADAPTER_INTERNAL_H

#include "adapter.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    adapter_info_t info;
    uint8_t * framebuffer;
    uint32_t width;
    uint32_t height;
    /** The display flush callback ran during the latest adapter_refresh(). */
    bool refresh_painted;

    /** Which standard indevs the version primitive created. */
    bool has_pointer;
    bool has_keypad;
    bool has_encoder;
    bool has_real_pointer;
    bool has_real_keypad;

    bool pointer_pressed;
    int32_t pointer_x;
    int32_t pointer_y;
    pointer_reply_t pointer_reply;
    char hit_name[128];
    char hit_class[64];

    bool keypad_pressed;
    uint32_t keypad_key;
    unsigned keypad_reads;

    int32_t encoder_diff;
    unsigned encoder_reads;

    bool real_pointer_pressed;
    int32_t real_pointer_x;
    int32_t real_pointer_y;
    pointer_reply_t real_pointer_reply;
    char real_hit_name[128];
    char real_hit_class[64];

    bool real_keypad_pressed;
    uint32_t real_keypad_key;
    unsigned real_keypad_reads;
} adapter_common_t;

typedef enum {
    ADAPTER_INDEV_POINTER = 0,
    ADAPTER_INDEV_KEYPAD,
    ADAPTER_INDEV_ENCODER,
    ADAPTER_INDEV_REAL_POINTER,
    ADAPTER_INDEV_REAL_KEYPAD,
} adapter_indev_kind_t;

size_t adapter_prim_state_size(void);

/**
 * Create LVGL, the display and the standard virtual pointer, keypad and
 * encoder indevs (plus the real OS indevs when ``real_input`` is true). Sets
 * the adapter info strings and the ``has_*`` flags. Returns 0 on success;
 * on failure the caller runs adapter_prim_deinit().
 */
int adapter_prim_init(adapter_t * adapter,
                      uint32_t width,
                      uint32_t height,
                      bool real_input);

/**
 * Delete the display and indevs and shut LVGL down. It tolerates a partial
 * adapter_prim_init() failure.
 */
void adapter_prim_deinit(adapter_t * adapter);

void adapter_prim_read(adapter_t * adapter, adapter_indev_kind_t kind);

/**
 * Hit-test the point and copy the object name and class name into the
 * caller's buffers (empty strings when nothing was hit). 9.2+ has object
 * names; 8.x maps built-in class pointers to names.
 */
void adapter_prim_hit(adapter_t * adapter,
                      int32_t x,
                      int32_t y,
                      char * hit_name,
                      size_t hit_name_size,
                      char * hit_class,
                      size_t hit_class_size);

void adapter_prim_refresh(adapter_t * adapter);

void adapter_prim_tick_inc(uint32_t ms);

void adapter_prim_timer_handler(void);

/**
 * Decode PNG bytes into packed B, G, R, X pixels (framebuffer layout)
 * allocated with malloc. Logs decode failures against ``path``. Returns 0 on
 * success; the caller releases ``*pixels`` with free().
 */
int adapter_prim_png_decode(const unsigned char * data,
                            size_t size,
                            const char * path,
                            unsigned char ** pixels,
                            uint32_t * width,
                            uint32_t * height);

#endif
