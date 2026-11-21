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
    const char * lvgl_version;
    const char * lvgl_src;
    const char * adapter_name;
} adapter_info_t;

typedef enum {
    POINTER_DOWN = 0,
    POINTER_MOVE = 1,
    POINTER_UP = 2,
} pointer_action_t;

typedef struct {
    int32_t x;
    int32_t y;
    const char * hit;
    const char * hit_class;
} pointer_reply_t;

typedef enum {
    KEY_PRESS = 0,
    KEY_RELEASE = 1,
} key_action_t;

adapter_t * adapter_create(uint32_t width, uint32_t height, bool real_input);

void adapter_destroy(adapter_t * adapter);

const adapter_info_t * adapter_info(const adapter_t * adapter);

void adapter_refresh(adapter_t * adapter);

bool adapter_last_refresh_painted(const adapter_t * adapter);

int adapter_pointer(adapter_t * adapter, pointer_action_t action, int32_t x,
                    int32_t y);

const pointer_reply_t * adapter_last_pointer(const adapter_t * adapter);

int adapter_real_pointer(adapter_t * adapter, pointer_action_t action,
                         int32_t x, int32_t y);

const pointer_reply_t * adapter_last_real_pointer(const adapter_t * adapter);

int adapter_real_key(adapter_t * adapter, key_action_t action, uint32_t key);

int adapter_key(adapter_t * adapter, key_action_t action, uint32_t key);

int adapter_encoder(adapter_t * adapter, int32_t diff);

void adapter_tick_inc(adapter_t * adapter, uint32_t ms);

void adapter_timer_handler(adapter_t * adapter);

const uint8_t * adapter_framebuffer(const adapter_t * adapter);

int adapter_save_png(const adapter_t * adapter, const char * path);

int adapter_save_rgba(const adapter_t * adapter, const char * path);

int adapter_load_png(const char * path, uint8_t ** pixels, uint32_t * width,
                     uint32_t * height);

void adapter_free_pixels(uint8_t * pixels);

#ifdef __cplusplus
}
#endif

#endif
