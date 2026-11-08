/**
 * @file adapter_8x.c
 * LVGL 8.x adapter primitives: legacy display/indev driver creation, one
 * indev read, hit testing, refresh/tick/timer forwarding and lodepng
 * encode/decode.
 *
 * This is the only 8.x engine source that includes LVGL headers. Everything
 * version-independent (state machines, hit reply buffers, RGBA conversion,
 * file IO, lifecycle) lives in adapter_common.c. The narrow interface
 * consumed by the engine is adapter.h.
 */

#include "adapter.h"
#include "adapter_internal.h"

#include "lvgl.h"
#include "lodepng.h"

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
    lv_disp_t * display;
    lv_disp_drv_t display_drv;
    lv_disp_draw_buf_t draw_buf;
    lv_color_t * draw_buffer;

    lv_indev_t * pointer;
    lv_indev_drv_t pointer_drv;

    lv_indev_t * keypad;
    lv_indev_drv_t keypad_drv;

    lv_indev_t * encoder;
    lv_indev_drv_t encoder_drv;

    /* OS input uses its own standard indevs, created before app_create()
     * so user/app's focus-group loop sees the real keypad. */
    lv_indev_t * real_pointer;
    lv_indev_drv_t real_pointer_drv;

    lv_indev_t * real_keypad;
    lv_indev_drv_t real_keypad_drv;
};

_Static_assert(offsetof(struct adapter, common) == 0,
               "adapter_common_t must be the first member of struct adapter");

static void pointer_read_cb(lv_indev_drv_t * drv, lv_indev_data_t * data)
{
    adapter_t * adapter = (adapter_t *)drv->user_data;
    if(adapter == NULL) return;
    data->point.x = adapter->common.pointer_x;
    data->point.y = adapter->common.pointer_y;
    data->state = adapter->common.pointer_pressed ? LV_INDEV_STATE_PRESSED
                                                  : LV_INDEV_STATE_RELEASED;
    data->continue_reading = false;
}

static void keypad_read_cb(lv_indev_drv_t * drv, lv_indev_data_t * data)
{
    adapter_t * adapter = (adapter_t *)drv->user_data;
    if(adapter == NULL) return;
    data->key = adapter->common.keypad_key;
    data->state = adapter->common.keypad_pressed ? LV_INDEV_STATE_PRESSED
                                                 : LV_INDEV_STATE_RELEASED;
    adapter->common.keypad_reads++;
    data->continue_reading = false;
}

static void encoder_read_cb(lv_indev_drv_t * drv, lv_indev_data_t * data)
{
    adapter_t * adapter = (adapter_t *)drv->user_data;
    if(adapter == NULL) return;
    data->enc_diff = (int16_t)adapter->common.encoder_diff;
    data->state = LV_INDEV_STATE_RELEASED;
    /* An encoder diff is a delta: consume it so timer reads do not repeat it. */
    adapter->common.encoder_diff = 0;
    adapter->common.encoder_reads++;
    data->continue_reading = false;
}

static void real_pointer_read_cb(lv_indev_drv_t * drv,
                                     lv_indev_data_t * data)
{
    adapter_t * adapter = (adapter_t *)drv->user_data;
    if(adapter == NULL) return;
    data->point.x = adapter->common.real_pointer_x;
    data->point.y = adapter->common.real_pointer_y;
    data->state = adapter->common.real_pointer_pressed
                      ? LV_INDEV_STATE_PRESSED
                      : LV_INDEV_STATE_RELEASED;
    data->continue_reading = false;
}

static void real_keypad_read_cb(lv_indev_drv_t * drv,
                                    lv_indev_data_t * data)
{
    adapter_t * adapter = (adapter_t *)drv->user_data;
    if(adapter == NULL) return;
    data->key = adapter->common.real_keypad_key;
    data->state = adapter->common.real_keypad_pressed
                      ? LV_INDEV_STATE_PRESSED
                      : LV_INDEV_STATE_RELEASED;
    adapter->common.real_keypad_reads++;
    data->continue_reading = false;
}

/**
 * LVGL 8.x has no object-name API and its lv_obj_class_t carries no name
 * string (that was added in 9.x). Map the built-in class pointers enabled in
 * lv_conf.h to their canonical 8.x class names; custom classes fall back to
 * the nearest known base class. Object names are never invented: hit stays "".
 */
static const char * class_name(const lv_obj_class_t * class_p)
{
    while(class_p != NULL) {
#if LV_USE_BTN
        if(class_p == &lv_btn_class) return "lv_btn";
#endif
#if LV_USE_LABEL
        if(class_p == &lv_label_class) return "lv_label";
#endif
#if LV_USE_IMG
        if(class_p == &lv_img_class) return "lv_img";
#endif
        if(class_p == &lv_obj_class) return "lv_obj";
        class_p = class_p->base_class;
    }
    return "";
}

static lv_obj_t * hit_test(adapter_t * adapter, int32_t x, int32_t y)
{
    lv_point_t point = {x, y};
    lv_disp_t * display = adapter->display;
    lv_obj_t * found = lv_indev_search_obj(lv_disp_get_layer_sys(display),
                                           &point);
    if(found != NULL) return found;
    found = lv_indev_search_obj(lv_disp_get_layer_top(display), &point);
    if(found != NULL) return found;
    /* 8.x has no bottom layer: the active screen is the bottom-most surface. */
    return lv_indev_search_obj(lv_disp_get_scr_act(display), &point);
}

static void flush_cb(lv_disp_drv_t * disp_drv, const lv_area_t * area,
                         lv_color_t * color_p)
{
    adapter_t * adapter = (adapter_t *)disp_drv->user_data;
    if(adapter != NULL && color_p != NULL) {
        uint32_t width = (uint32_t)lv_area_get_width(area);
        uint32_t height = (uint32_t)lv_area_get_height(area);
        const uint8_t * src = (const uint8_t *)color_p;
        for(uint32_t y = 0; y < height; y++) {
            size_t dst = ((size_t)(area->y1 + (int32_t)y)
                          * adapter->common.width + (size_t)area->x1) * 4u;
            memcpy(adapter->common.framebuffer + dst,
                   src + (size_t)y * width * 4u, (size_t)width * 4u);
        }
    }
    lv_disp_flush_ready(disp_drv);
}

/**
 * LVGL 8.x exposes no lv_indev_read(); the registered read timer callback is
 * the public entry that reads and processes one input event synchronously.
 */
static void indev_process(const lv_indev_drv_t * drv)
{
    if(drv != NULL && drv->read_timer != NULL) {
        lv_indev_read_timer_cb(drv->read_timer);
    }
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
    common->info.adapter_name = "8x";

    adapter->draw_buffer = (lv_color_t *)malloc((size_t)width * height
                                                * sizeof(lv_color_t));
    if(adapter->draw_buffer == NULL) return -1;

    lv_init();
    adapter->lvgl_initialized = true;

    lv_disp_draw_buf_init(&adapter->draw_buf, adapter->draw_buffer, NULL,
                          width * height);
    lv_disp_drv_init(&adapter->display_drv);
    adapter->display_drv.hor_res = (lv_coord_t)width;
    adapter->display_drv.ver_res = (lv_coord_t)height;
    adapter->display_drv.flush_cb = flush_cb;
    adapter->display_drv.draw_buf = &adapter->draw_buf;
    adapter->display_drv.user_data = adapter;
    /* Always render the whole screen, matching the 9.x adapter's
     * LV_DISPLAY_RENDER_MODE_FULL. */
    adapter->display_drv.full_refresh = 1;
    adapter->display = lv_disp_drv_register(&adapter->display_drv);
    if(adapter->display == NULL) return -1;

    lv_indev_drv_init(&adapter->pointer_drv);
    adapter->pointer_drv.type = LV_INDEV_TYPE_POINTER;
    adapter->pointer_drv.read_cb = pointer_read_cb;
    adapter->pointer_drv.user_data = adapter;
    adapter->pointer = lv_indev_drv_register(&adapter->pointer_drv);
    if(adapter->pointer == NULL) return -1;
    common->has_pointer = true;

    /* Standard keypad and encoder indevs. They are not attached to any focus
     * group: the tool stays small, and user/app owns its group if it needs
     * focus navigation. */
    lv_indev_drv_init(&adapter->keypad_drv);
    adapter->keypad_drv.type = LV_INDEV_TYPE_KEYPAD;
    adapter->keypad_drv.read_cb = keypad_read_cb;
    adapter->keypad_drv.user_data = adapter;
    adapter->keypad = lv_indev_drv_register(&adapter->keypad_drv);
    if(adapter->keypad == NULL) return -1;
    common->has_keypad = true;

    lv_indev_drv_init(&adapter->encoder_drv);
    adapter->encoder_drv.type = LV_INDEV_TYPE_ENCODER;
    adapter->encoder_drv.read_cb = encoder_read_cb;
    adapter->encoder_drv.user_data = adapter;
    adapter->encoder = lv_indev_drv_register(&adapter->encoder_drv);
    if(adapter->encoder == NULL) return -1;
    common->has_encoder = true;

    if(real_input) {
        lv_indev_drv_init(&adapter->real_pointer_drv);
        adapter->real_pointer_drv.type = LV_INDEV_TYPE_POINTER;
        adapter->real_pointer_drv.read_cb = real_pointer_read_cb;
        adapter->real_pointer_drv.user_data = adapter;
        adapter->real_pointer =
            lv_indev_drv_register(&adapter->real_pointer_drv);
        if(adapter->real_pointer == NULL) return -1;
        common->has_real_pointer = true;

        lv_indev_drv_init(&adapter->real_keypad_drv);
        adapter->real_keypad_drv.type = LV_INDEV_TYPE_KEYPAD;
        adapter->real_keypad_drv.read_cb = real_keypad_read_cb;
        adapter->real_keypad_drv.user_data = adapter;
        adapter->real_keypad =
            lv_indev_drv_register(&adapter->real_keypad_drv);
        if(adapter->real_keypad == NULL) return -1;
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
        lv_disp_remove(adapter->display);
        adapter->display = NULL;
    }
    if(adapter->lvgl_initialized) {
        lv_deinit();
        adapter->lvgl_initialized = false;
    }
    free(adapter->draw_buffer);
    adapter->draw_buffer = NULL;
}

void adapter_prim_read(adapter_t * adapter, adapter_indev_kind_t kind)
{
    switch(kind) {
        case ADAPTER_INDEV_POINTER:
            indev_process(&adapter->pointer_drv);
            break;
        case ADAPTER_INDEV_KEYPAD:
            indev_process(&adapter->keypad_drv);
            break;
        case ADAPTER_INDEV_ENCODER:
            indev_process(&adapter->encoder_drv);
            break;
        case ADAPTER_INDEV_REAL_POINTER:
            indev_process(&adapter->real_pointer_drv);
            break;
        case ADAPTER_INDEV_REAL_KEYPAD:
            indev_process(&adapter->real_keypad_drv);
            break;
    }
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

    /* 8.x has no object-name API and no class-name metadata. */
    const lv_obj_class_t * class_p = lv_obj_get_class(obj);
    snprintf(hit_class, hit_class_size, "%s", class_name(class_p));
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
        if(encoded != NULL) lv_mem_free(encoded);
        return -1;
    }

    *png = encoded;
    *png_size = encoded_size;
    return 0;
}

void adapter_prim_png_free(unsigned char * png)
{
    lv_mem_free(png);
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

    unsigned char * decoded = NULL;
    unsigned png_width = 0;
    unsigned png_height = 0;
    unsigned error = lodepng_decode32(&decoded, &png_width, &png_height,
                                      data, size);
    if(error != 0 || decoded == NULL) {
        fprintf(stderr, "[engine] cannot decode reference %s: %s\n", path,
                lodepng_error_text(error));
        if(decoded != NULL) {
            lv_mem_free(decoded);
        }
        return -1;
    }

    size_t pixel_count = (size_t)png_width * png_height;
    uint8_t * packed = (uint8_t *)malloc(pixel_count * 4u);
    if(packed == NULL) {
        lv_mem_free(decoded);
        return -1;
    }
    /* The 8.x lodepng allocator is lv_mem_alloc, and decode32 asks for RGBA.
     * Repack into the framebuffer layout B, G, R, X. */
    for(unsigned y = 0; y < png_height; y++) {
        const uint8_t * row = decoded + (size_t)y * png_width * 4u;
        for(unsigned x = 0; x < png_width; x++) {
            size_t out = ((size_t)y * png_width + x) * 4u;
            packed[out + 0u] = row[x * 4u + 2u];
            packed[out + 1u] = row[x * 4u + 1u];
            packed[out + 2u] = row[x * 4u + 0u];
            packed[out + 3u] = 0u;
        }
    }
    lv_mem_free(decoded);
    *pixels = packed;
    *width = png_width;
    *height = png_height;
    return 0;
}
