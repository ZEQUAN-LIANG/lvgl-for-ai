/**
 * @file adapter_9x.c
 * LVGL 9.x adapter primitives: display/indev creation, one indev read, hit
 * testing, refresh/tick/timer forwarding and lodepng encode/decode.
 *
 * This is the 9.x engine source that includes LVGL headers; its 8.x peer is
 * adapter_8x.c. Everything version-independent (state machines, hit reply
 * buffers, RGBA conversion, file IO, lifecycle) lives in adapter_common.c.
 * The narrow interface consumed by the engine is adapter.h.
 */

#include "adapter.h"
#include "adapter_internal.h"

#include "lvgl.h"
#include "lodepng.h"
/* 9.4 moved lv_obj_class_t (and its name field) into the private header.
 * 9.1 keeps the struct public in core/lv_obj_class.h. */
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4
    #include "src/core/lv_obj_class_private.h"
#endif

#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef LVGL_SRC_PATH
    #define LVGL_SRC_PATH ""
#endif

#define STRINGIFY_INNER(value) #value
#define STRINGIFY(value) STRINGIFY_INNER(value)
#define LVGL_VERSION_STRING \
    STRINGIFY(LVGL_VERSION_MAJOR) "." \
    STRINGIFY(LVGL_VERSION_MINOR) "." \
    STRINGIFY(LVGL_VERSION_PATCH)

struct adapter {
    adapter_common_t common;
    bool lvgl_initialized;
    lv_display_t * display;
    lv_indev_t * pointer;
    lv_indev_t * keypad;
    lv_indev_t * encoder;
    /* OS input uses its own standard indevs, created before app_create()
     * so user/app's focus-group loop sees the real keypad. */
    lv_indev_t * real_pointer;
    lv_indev_t * real_keypad;
};

_Static_assert(offsetof(struct adapter, common) == 0,
               "adapter_common_t must be the first member of struct adapter");

static void pointer_read_cb(lv_indev_t * indev, lv_indev_data_t * data)
{
    adapter_t * adapter = (adapter_t *)lv_indev_get_user_data(indev);
    if(adapter == NULL) return;
    data->point.x = adapter->common.pointer_x;
    data->point.y = adapter->common.pointer_y;
    data->state = adapter->common.pointer_pressed ? LV_INDEV_STATE_PRESSED
                                                  : LV_INDEV_STATE_RELEASED;
    data->continue_reading = false;
}

static void keypad_read_cb(lv_indev_t * indev, lv_indev_data_t * data)
{
    adapter_t * adapter = (adapter_t *)lv_indev_get_user_data(indev);
    if(adapter == NULL) return;
    data->key = adapter->common.keypad_key;
    data->state = adapter->common.keypad_pressed ? LV_INDEV_STATE_PRESSED
                                                 : LV_INDEV_STATE_RELEASED;
    adapter->common.keypad_reads++;
    data->continue_reading = false;
}

static void encoder_read_cb(lv_indev_t * indev, lv_indev_data_t * data)
{
    adapter_t * adapter = (adapter_t *)lv_indev_get_user_data(indev);
    if(adapter == NULL) return;
    data->enc_diff = (int16_t)adapter->common.encoder_diff;
    data->state = LV_INDEV_STATE_RELEASED;
    /* An encoder diff is a delta: consume it so timer reads do not repeat it. */
    adapter->common.encoder_diff = 0;
    adapter->common.encoder_reads++;
    data->continue_reading = false;
}

static void real_pointer_read_cb(lv_indev_t * indev, lv_indev_data_t * data)
{
    adapter_t * adapter = (adapter_t *)lv_indev_get_user_data(indev);
    if(adapter == NULL) return;
    data->point.x = adapter->common.real_pointer_x;
    data->point.y = adapter->common.real_pointer_y;
    data->state = adapter->common.real_pointer_pressed
                      ? LV_INDEV_STATE_PRESSED
                      : LV_INDEV_STATE_RELEASED;
    data->continue_reading = false;
}

static void real_keypad_read_cb(lv_indev_t * indev, lv_indev_data_t * data)
{
    adapter_t * adapter = (adapter_t *)lv_indev_get_user_data(indev);
    if(adapter == NULL) return;
    data->key = adapter->common.real_keypad_key;
    data->state = adapter->common.real_keypad_pressed
                      ? LV_INDEV_STATE_PRESSED
                      : LV_INDEV_STATE_RELEASED;
    adapter->common.real_keypad_reads++;
    data->continue_reading = false;
}

static lv_obj_t * hit_test(adapter_t * adapter, int32_t x, int32_t y)
{
    lv_point_t point = {x, y};
    lv_display_t * display = adapter->display;
    lv_obj_t * found = lv_indev_search_obj(lv_display_get_layer_sys(display),
                                           &point);
    if(found != NULL) return found;
    found = lv_indev_search_obj(lv_display_get_layer_top(display), &point);
    if(found != NULL) return found;
    found = lv_indev_search_obj(lv_display_get_screen_active(display), &point);
    if(found != NULL) return found;
    return lv_indev_search_obj(lv_display_get_layer_bottom(display), &point);
}

static void flush_cb(lv_display_t * display, const lv_area_t * area,
                         uint8_t * px_map)
{
    adapter_t * adapter = (adapter_t *)lv_display_get_user_data(display);
    if(adapter != NULL && px_map != adapter->common.framebuffer) {
        uint32_t width = (uint32_t)lv_area_get_width(area);
        uint32_t height = (uint32_t)lv_area_get_height(area);
        for(uint32_t y = 0; y < height; y++) {
            size_t dst = ((size_t)(area->y1 + (int32_t)y)
                          * adapter->common.width + (size_t)area->x1) * 4u;
            memcpy(adapter->common.framebuffer + dst,
                   px_map + (size_t)y * width * 4u, (size_t)width * 4u);
        }
    }
    lv_display_flush_ready(display);
}

size_t adapter_prim_state_size(void)
{
    return sizeof(struct adapter);
}

int adapter_prim_init(adapter_t * adapter, uint32_t width, uint32_t height,
                      bool real_input)
{
    adapter_common_t * common = &adapter->common;
    common->info.lvgl_version = LVGL_VERSION_STRING;
    common->info.lvgl_src = LVGL_SRC_PATH;
    common->info.adapter_name = "9x";

    lv_init();
    adapter->lvgl_initialized = true;

    lv_display_t * display = lv_display_create((int32_t)width, (int32_t)height);
    if(display == NULL) return -1;
    lv_display_set_user_data(display, adapter);
    lv_display_set_color_format(display, LV_COLOR_FORMAT_XRGB8888);
    lv_display_set_buffers(display, common->framebuffer, NULL,
                           (uint32_t)((size_t)width * height * 4u),
                           LV_DISPLAY_RENDER_MODE_FULL);
    lv_display_set_flush_cb(display, flush_cb);
    adapter->display = display;

    lv_indev_t * pointer = lv_indev_create();
    if(pointer == NULL) return -1;
    lv_indev_set_type(pointer, LV_INDEV_TYPE_POINTER);
    lv_indev_set_display(pointer, display);
    lv_indev_set_read_cb(pointer, pointer_read_cb);
    lv_indev_set_user_data(pointer, adapter);
    adapter->pointer = pointer;
    common->has_pointer = true;

    /* Standard keypad and encoder indevs. They are not attached to any focus
     * group: the tool stays small, and user/app owns its group if it needs
     * focus navigation. */
    lv_indev_t * keypad = lv_indev_create();
    if(keypad == NULL) return -1;
    lv_indev_set_type(keypad, LV_INDEV_TYPE_KEYPAD);
    lv_indev_set_display(keypad, display);
    lv_indev_set_read_cb(keypad, keypad_read_cb);
    lv_indev_set_user_data(keypad, adapter);
    adapter->keypad = keypad;
    common->has_keypad = true;

    lv_indev_t * encoder = lv_indev_create();
    if(encoder == NULL) return -1;
    lv_indev_set_type(encoder, LV_INDEV_TYPE_ENCODER);
    lv_indev_set_display(encoder, display);
    lv_indev_set_read_cb(encoder, encoder_read_cb);
    lv_indev_set_user_data(encoder, adapter);
    adapter->encoder = encoder;
    common->has_encoder = true;

    if(real_input) {
        lv_indev_t * real_pointer = lv_indev_create();
        if(real_pointer == NULL) return -1;
        lv_indev_set_type(real_pointer, LV_INDEV_TYPE_POINTER);
        lv_indev_set_display(real_pointer, display);
        lv_indev_set_read_cb(real_pointer, real_pointer_read_cb);
        lv_indev_set_user_data(real_pointer, adapter);
        adapter->real_pointer = real_pointer;
        common->has_real_pointer = true;

        lv_indev_t * real_keypad = lv_indev_create();
        if(real_keypad == NULL) return -1;
        lv_indev_set_type(real_keypad, LV_INDEV_TYPE_KEYPAD);
        lv_indev_set_display(real_keypad, display);
        lv_indev_set_read_cb(real_keypad, real_keypad_read_cb);
        lv_indev_set_user_data(real_keypad, adapter);
        adapter->real_keypad = real_keypad;
        common->has_real_keypad = true;
    }

    return 0;
}

void adapter_prim_deinit(adapter_t * adapter)
{
    if(adapter->real_keypad != NULL) {
        lv_indev_delete(adapter->real_keypad);
        adapter->real_keypad = NULL;
    }
    if(adapter->real_pointer != NULL) {
        lv_indev_delete(adapter->real_pointer);
        adapter->real_pointer = NULL;
    }
    if(adapter->encoder != NULL) {
        lv_indev_delete(adapter->encoder);
        adapter->encoder = NULL;
    }
    if(adapter->keypad != NULL) {
        lv_indev_delete(adapter->keypad);
        adapter->keypad = NULL;
    }
    if(adapter->pointer != NULL) {
        lv_indev_delete(adapter->pointer);
        adapter->pointer = NULL;
    }
    if(adapter->display != NULL) {
        lv_display_delete(adapter->display);
        adapter->display = NULL;
    }
    if(adapter->lvgl_initialized) {
        lv_deinit();
        adapter->lvgl_initialized = false;
    }
}

void adapter_prim_read(adapter_t * adapter, adapter_indev_kind_t kind)
{
    lv_indev_t * indev = NULL;
    switch(kind) {
        case ADAPTER_INDEV_POINTER:
            indev = adapter->pointer;
            break;
        case ADAPTER_INDEV_KEYPAD:
            indev = adapter->keypad;
            break;
        case ADAPTER_INDEV_ENCODER:
            indev = adapter->encoder;
            break;
        case ADAPTER_INDEV_REAL_POINTER:
            indev = adapter->real_pointer;
            break;
        case ADAPTER_INDEV_REAL_KEYPAD:
            indev = adapter->real_keypad;
            break;
    }
    if(indev != NULL) lv_indev_read(indev);
}

void adapter_prim_hit(adapter_t * adapter,
                      int32_t x,
                      int32_t y,
                      char * hit_name,
                      size_t hit_name_size,
                      char * hit_class,
                      size_t hit_class_size)
{
    if(hit_name_size > 0) hit_name[0] = '\0';
    if(hit_class_size > 0) hit_class[0] = '\0';
    lv_obj_t * obj = hit_test(adapter, x, y);
    if(obj == NULL) return;

    /* Object names were added in 9.2. LVGL 9.1 has no name API and no
     * LV_USE_OBJ_NAME switch, so hit stays empty there; hit_class still works. */
#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 2
    const char * name = lv_obj_get_name(obj);
    if(name != NULL) {
        snprintf(hit_name, hit_name_size, "%s", name);
    }
#endif

    const lv_obj_class_t * class_p = lv_obj_get_class(obj);
    if(class_p != NULL && class_p->name != NULL) {
        snprintf(hit_class, hit_class_size, "%s", class_p->name);
    }
}

void adapter_prim_refresh(adapter_t * adapter)
{
    if(adapter->display == NULL) return;
    lv_refr_now(adapter->display);
}

void adapter_prim_tick_inc(uint32_t ms)
{
    lv_tick_inc(ms);
}

void adapter_prim_timer_handler(void)
{
    lv_timer_handler();
}

int adapter_prim_png_encode(const unsigned char * rgba,
                            uint32_t width,
                            uint32_t height,
                            unsigned char ** png,
                            size_t * png_size)
{
    *png = NULL;
    *png_size = 0;

    unsigned char * encoded = NULL;
    size_t encoded_size = 0;
    LodePNGState state;
    lodepng_state_init(&state);
    state.info_raw.colortype = LCT_RGBA;
    state.info_raw.bitdepth = 8;
    state.info_png.color.colortype = LCT_RGB;
    state.info_png.color.bitdepth = 8;
    state.encoder.auto_convert = 0;
    state.encoder.filter_strategy = LFS_ZERO;
    unsigned error = lodepng_encode(&encoded, &encoded_size, rgba, width,
                                    height, &state);
    lodepng_state_cleanup(&state);
    if(error != 0) {
        fprintf(stderr, "[engine] lodepng error %u: %s\n", error,
                lodepng_error_text(error));
        if(encoded != NULL) lv_free(encoded);
        return -1;
    }

    *png = encoded;
    *png_size = encoded_size;
    return 0;
}

void adapter_prim_png_free(unsigned char * png)
{
    lv_free(png);
}

int adapter_prim_png_decode(const unsigned char * data,
                            size_t size,
                            const char * path,
                            unsigned char ** pixels,
                            uint32_t * width,
                            uint32_t * height)
{
    *pixels = NULL;
    *width = 0;
    *height = 0;

    unsigned char * decoded_ptr = NULL;
    unsigned png_width = 0;
    unsigned png_height = 0;
    unsigned error = lodepng_decode32(&decoded_ptr, &png_width, &png_height,
                                      data, size);
    if(error != 0 || decoded_ptr == NULL) {
        fprintf(stderr, "[engine] cannot decode reference %s: %s\n", path,
                lodepng_error_text(error));
        if(decoded_ptr != NULL) {
            lv_draw_buf_destroy((lv_draw_buf_t *)decoded_ptr);
        }
        return -1;
    }

    /* All supported 9.x lodepng builds return a draw buffer, even though the
     * public signature still says unsigned char *. */
    lv_draw_buf_t * decoded = (lv_draw_buf_t *)decoded_ptr;
    size_t pixel_count = (size_t)png_width * png_height;
    uint8_t * packed = (uint8_t *)malloc(pixel_count * 4u);
    if(packed == NULL || decoded->data == NULL ||
       decoded->header.stride < (uint32_t)png_width * 4u) {
        free(packed);
        lv_draw_buf_destroy(decoded);
        return -1;
    }
    /* lodepng_decode32 asks for LCT_RGBA, so the draw buffer data is R, G, B, A
     * even though LVGL creates it with an ARGB8888 header. Repack into the
     * framebuffer layout B, G, R, X. */
    for(unsigned y = 0; y < png_height; y++) {
        const uint8_t * row = decoded->data + (size_t)y * decoded->header.stride;
        for(unsigned x = 0; x < png_width; x++) {
            size_t out = ((size_t)y * png_width + x) * 4u;
            packed[out + 0u] = row[x * 4u + 2u];
            packed[out + 1u] = row[x * 4u + 1u];
            packed[out + 2u] = row[x * 4u + 0u];
            packed[out + 3u] = 0u;
        }
    }
    lv_draw_buf_destroy(decoded);
    *pixels = packed;
    *width = png_width;
    *height = png_height;
    return 0;
}
