#include "adapter.h"
#include "adapter_internal.h"
#include "png_writer.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static adapter_common_t * common_of(adapter_t * adapter)
{
    return (adapter_common_t *)adapter;
}

static const adapter_common_t * common_of_const(const adapter_t * adapter)
{
    return (const adapter_common_t *)adapter;
}

static void reset_reply_pointers(adapter_common_t * common)
{
    common->pointer_reply.hit = common->hit_name;
    common->pointer_reply.hit_class = common->hit_class;
    common->real_pointer_reply.hit = common->real_hit_name;
    common->real_pointer_reply.hit_class = common->real_hit_class;
}

static void store_hit(adapter_t * adapter, int32_t x, int32_t y, bool real)
{
    adapter_common_t * common = common_of(adapter);
    char * hit_name = real ? common->real_hit_name : common->hit_name;
    char * hit_class = real ? common->real_hit_class : common->hit_class;
    size_t hit_name_size =
        real ? sizeof(common->real_hit_name) : sizeof(common->hit_name);
    size_t hit_class_size =
        real ? sizeof(common->real_hit_class) : sizeof(common->hit_class);
    pointer_reply_t * reply =
        real ? &common->real_pointer_reply : &common->pointer_reply;

    adapter_prim_hit(adapter, x, y, hit_name, hit_name_size, hit_class,
                     hit_class_size);
    reply->hit = hit_name;
    reply->hit_class = hit_class;
}

adapter_t * adapter_create(uint32_t width, uint32_t height, bool real_input)
{
    if(width == 0 || height == 0) return NULL;

    adapter_t * adapter = (adapter_t *)calloc(1, adapter_prim_state_size());
    if(adapter == NULL) return NULL;

    adapter_common_t * common = common_of(adapter);
    size_t buffer_size = (size_t)width * height * 4u;
    common->framebuffer = (uint8_t *)malloc(buffer_size);
    if(common->framebuffer == NULL) {
        free(adapter);
        return NULL;
    }
    common->width = width;
    common->height = height;
    common->info.width = width;
    common->info.height = height;
    reset_reply_pointers(common);

    if(adapter_prim_init(adapter, width, height, real_input) != 0) {
        adapter_prim_deinit(adapter);
        free(common->framebuffer);
        free(adapter);
        return NULL;
    }
    return adapter;
}

void adapter_destroy(adapter_t * adapter)
{
    if(adapter == NULL) return;
    adapter_common_t * common = common_of(adapter);
    adapter_prim_deinit(adapter);
    free(common->framebuffer);
    free(adapter);
}

const adapter_info_t * adapter_info(const adapter_t * adapter)
{
    return adapter == NULL ? NULL : &common_of_const(adapter)->info;
}

void adapter_refresh(adapter_t * adapter)
{
    if(adapter == NULL) return;
    common_of(adapter)->refresh_painted = false;
    adapter_prim_refresh(adapter);
}

bool adapter_last_refresh_painted(const adapter_t * adapter)
{
    return adapter != NULL && common_of_const(adapter)->refresh_painted;
}

const uint8_t * adapter_framebuffer(const adapter_t * adapter)
{
    return adapter == NULL ? NULL : common_of_const(adapter)->framebuffer;
}

int adapter_pointer(adapter_t * adapter, pointer_action_t action, int32_t x,
                    int32_t y)
{
    if(adapter == NULL) return -1;
    adapter_common_t * common = common_of(adapter);
    if(!common->has_pointer) return -1;

    store_hit(adapter, x, y, false);
    common->pointer_reply.x = x;
    common->pointer_reply.y = y;
    common->pointer_pressed = action != POINTER_UP;
    common->pointer_x = x;
    common->pointer_y = y;
    adapter_prim_read(adapter, ADAPTER_INDEV_POINTER);
    return 0;
}

const pointer_reply_t * adapter_last_pointer(const adapter_t * adapter)
{
    return adapter == NULL ? NULL : &common_of_const(adapter)->pointer_reply;
}

int adapter_real_pointer(adapter_t * adapter, pointer_action_t action,
                         int32_t x, int32_t y)
{
    if(adapter == NULL) return -1;
    adapter_common_t * common = common_of(adapter);
    if(!common->has_real_pointer) return -1;

    store_hit(adapter, x, y, true);
    common->real_pointer_reply.x = x;
    common->real_pointer_reply.y = y;

    if(action == POINTER_DOWN) {
        common->real_pointer_pressed = false;
        common->real_pointer_x = x;
        common->real_pointer_y = y;
        adapter_prim_read(adapter, ADAPTER_INDEV_REAL_POINTER);
    }

    common->real_pointer_pressed = action != POINTER_UP;
    common->real_pointer_x = x;
    common->real_pointer_y = y;
    adapter_prim_read(adapter, ADAPTER_INDEV_REAL_POINTER);
    return 0;
}

const pointer_reply_t * adapter_last_real_pointer(const adapter_t * adapter)
{
    return adapter == NULL ? NULL
                           : &common_of_const(adapter)->real_pointer_reply;
}

int adapter_real_key(adapter_t * adapter, key_action_t action, uint32_t key)
{
    if(adapter == NULL) return -1;
    adapter_common_t * common = common_of(adapter);
    if(!common->has_real_keypad) return -1;

    unsigned reads_before = common->real_keypad_reads;
    common->real_keypad_key = key;
    common->real_keypad_pressed = action == KEY_PRESS;
    adapter_prim_read(adapter, ADAPTER_INDEV_REAL_KEYPAD);
    return common->real_keypad_reads != reads_before ? 0 : -1;
}

int adapter_key(adapter_t * adapter, key_action_t action, uint32_t key)
{
    if(adapter == NULL) return -1;
    adapter_common_t * common = common_of(adapter);
    if(!common->has_keypad) return -1;

    unsigned reads_before = common->keypad_reads;
    bool pressed_before = common->keypad_pressed;
    uint32_t key_before = common->keypad_key;
    common->keypad_key = key;
    common->keypad_pressed = action == KEY_PRESS;
    adapter_prim_read(adapter, ADAPTER_INDEV_KEYPAD);
    if(common->keypad_reads == reads_before) {
        common->keypad_pressed = pressed_before;
        common->keypad_key = key_before;
        return -1;
    }
    return 0;
}

int adapter_encoder(adapter_t * adapter, int32_t diff)
{
    if(adapter == NULL) return -1;
    adapter_common_t * common = common_of(adapter);
    if(!common->has_encoder) return -1;

    unsigned reads_before = common->encoder_reads;
    common->encoder_diff = diff;
    adapter_prim_read(adapter, ADAPTER_INDEV_ENCODER);
    if(common->encoder_reads == reads_before) {
        common->encoder_diff = 0;
        return -1;
    }
    return 0;
}

void adapter_tick_inc(adapter_t * adapter, uint32_t ms)
{
    (void)adapter;
    adapter_prim_tick_inc(ms);
}

void adapter_timer_handler(adapter_t * adapter)
{
    (void)adapter;
    adapter_prim_timer_handler();
}

static unsigned char * framebuffer_to_rgba(const adapter_common_t * common)
{
    if(common == NULL) return NULL;

    size_t pixel_count = (size_t)common->width * common->height;
    unsigned char * rgba = (unsigned char *)malloc(pixel_count * 4u);
    if(rgba == NULL) return NULL;

    for(size_t i = 0; i < pixel_count; i++) {
        uint32_t pixel;
        memcpy(&pixel, common->framebuffer + i * 4u, sizeof(pixel));
        rgba[i * 4u + 0u] = (unsigned char)((pixel >> 16) & 0xFFu);
        rgba[i * 4u + 1u] = (unsigned char)((pixel >> 8) & 0xFFu);
        rgba[i * 4u + 2u] = (unsigned char)(pixel & 0xFFu);
        rgba[i * 4u + 3u] = 0xFFu;
    }
    return rgba;
}

int adapter_save_rgba(const adapter_t * adapter, const char * path)
{
    if(adapter == NULL || path == NULL) return -1;
    const adapter_common_t * common = common_of_const(adapter);

    size_t byte_count = (size_t)common->width * common->height * 4u;
    unsigned char * rgba = framebuffer_to_rgba(common);
    if(rgba == NULL) return -1;

    FILE * file = fopen(path, "wb");
    if(file == NULL) {
        fprintf(stderr, "[engine] cannot write %s\n", path);
        free(rgba);
        return -1;
    }
    size_t written = fwrite(rgba, 1, byte_count, file);
    fclose(file);
    free(rgba);
    if(written != byte_count) {
        fprintf(stderr, "[engine] short write to %s\n", path);
        return -1;
    }
    return 0;
}

int adapter_save_png(const adapter_t * adapter, const char * path)
{
    if(adapter == NULL || path == NULL) return -1;
    const adapter_common_t * common = common_of_const(adapter);
    return png_writer_write_xrgb(common->framebuffer, common->width,
                                 common->height, path);
}

int adapter_load_png(const char * path, uint8_t ** pixels, uint32_t * width,
                     uint32_t * height)
{
    if(path == NULL || pixels == NULL || width == NULL || height == NULL) {
        return -1;
    }
    *pixels = NULL;
    *width = 0;
    *height = 0;

    FILE * file = fopen(path, "rb");
    if(file == NULL) {
        fprintf(stderr, "[engine] cannot open reference %s\n", path);
        return -1;
    }
    if(fseek(file, 0, SEEK_END) != 0) {
        fclose(file);
        return -1;
    }
    long file_size = ftell(file);
    if(file_size <= 0 || fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        return -1;
    }
    unsigned char * png = (unsigned char *)malloc((size_t)file_size);
    if(png == NULL) {
        fclose(file);
        return -1;
    }
    size_t png_size = fread(png, 1, (size_t)file_size, file);
    fclose(file);
    if(png_size != (size_t)file_size) {
        fprintf(stderr, "[engine] short read from %s\n", path);
        free(png);
        return -1;
    }

    unsigned char * decoded = NULL;
    uint32_t decoded_width = 0;
    uint32_t decoded_height = 0;
    int error = adapter_prim_png_decode(png, png_size, path, &decoded,
                                        &decoded_width, &decoded_height);
    free(png);
    if(error != 0) return -1;

    *pixels = decoded;
    *width = decoded_width;
    *height = decoded_height;
    return 0;
}

void adapter_free_pixels(uint8_t * pixels)
{
    free(pixels);
}
