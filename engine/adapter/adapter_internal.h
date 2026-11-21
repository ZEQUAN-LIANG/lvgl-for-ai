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
    bool refresh_painted;

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

int adapter_prim_init(adapter_t * adapter, uint32_t width, uint32_t height,
                      bool real_input);

void adapter_prim_deinit(adapter_t * adapter);

void adapter_prim_read(adapter_t * adapter, adapter_indev_kind_t kind);

void adapter_prim_hit(adapter_t * adapter, int32_t x, int32_t y,
                      char * hit_name, size_t hit_name_size, char * hit_class,
                      size_t hit_class_size);

void adapter_prim_refresh(adapter_t * adapter);

void adapter_prim_tick_inc(uint32_t ms);

void adapter_prim_timer_handler(void);

int adapter_prim_png_decode(const unsigned char * data, size_t size,
                            const char * path, unsigned char ** pixels,
                            uint32_t * width, uint32_t * height);

#endif
