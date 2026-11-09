#include "lvgl.h"
#include "hspi_watch.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "assets.h"

#if defined(LVGL_AI_SDK_H)
#define WATCH_FPS() lv_get_fps()
#else
#define WATCH_FPS() 0.0f
#endif

#define WATCH_FACE_W 390
#define WATCH_FACE_H 450

static lv_obj_t * ring_obj;
static lv_obj_t * hour_obj;
static lv_obj_t * minute_obj;
static lv_obj_t * second_obj;
static lv_obj_t * time_label;
static lv_obj_t * fps_label;
static int32_t last_hour = -1;
static int32_t last_minute = -1;
static int32_t last_second = -1;
static int32_t ring_angle;

static void make_transparent(lv_obj_t * obj)
{
    lv_obj_set_style_bg_opa(obj, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(obj, 0, 0);
    lv_obj_set_style_pad_all(obj, 0, 0);
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
}

static lv_obj_t * make_label(lv_obj_t * parent, const char * text,
                             const lv_font_t * font, lv_color_t color)
{
    lv_obj_t * label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, color, 0);
    return label;
}

static void update_hand(lv_obj_t * obj, int32_t angle, int32_t * last)
{
    if (angle != *last)
    {
        lv_image_set_rotation(obj, angle);
        *last = angle;
    }
}

static lv_obj_t * make_hand(lv_obj_t * parent, const lv_image_dsc_t * src,
                            int32_t width, int32_t height)
{
    lv_obj_t * hand = lv_image_create(parent);
    lv_image_set_src(hand, src);
    lv_image_set_pivot(hand, width / 2, height);
    lv_obj_align(hand, LV_ALIGN_CENTER, 0, -height / 2);
    return hand;
}

static void clock_timer_cb(lv_timer_t * timer)
{
    (void)timer;
    uint32_t total = lv_tick_get() / 1000U;
    uint32_t hour = (total / 3600U) % 12U;
    uint32_t minute = (total / 60U) % 60U;
    uint32_t second = total % 60U;

    update_hand(hour_obj, (int32_t)(hour * 300U + minute * 5U), &last_hour);
    update_hand(minute_obj, (int32_t)(minute * 60U + second), &last_minute);
    update_hand(second_obj, (int32_t)(second * 60U), &last_second);
    lv_label_set_text_fmt(time_label, "%02u:%02u:%02u",
                          (unsigned)hour, (unsigned)minute, (unsigned)second);
}

static void ring_timer_cb(lv_timer_t * timer)
{
    (void)timer;
    ring_angle = (ring_angle + 30) % 3600;
    lv_image_set_rotation(ring_obj, ring_angle);
}

static void fps_timer_cb(lv_timer_t * timer)
{
    (void)timer;
    int fps10 = (int)(WATCH_FPS() * 10.0f);
    lv_label_set_text_fmt(fps_label, "FPS %d.%d", fps10 / 10, fps10 % 10);
}

void hspi_watch_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    lv_obj_t * face = lv_obj_create(screen);
    lv_obj_set_size(face, WATCH_FACE_W, WATCH_FACE_H);
    lv_obj_center(face);
    make_transparent(face);

    lv_obj_t * background = lv_image_create(face);
    lv_image_set_src(background, &watch_bg);
    lv_obj_center(background);

    ring_obj = lv_image_create(face);
    lv_image_set_src(ring_obj, &watch_ring);
    lv_image_set_pivot(ring_obj, WATCH_RING_W / 2, WATCH_RING_H / 2);
    lv_obj_center(ring_obj);

    hour_obj = make_hand(face, &watch_hour, WATCH_HOUR_W, WATCH_HOUR_H);
    minute_obj = make_hand(face, &watch_minute, WATCH_MINUTE_W, WATCH_MINUTE_H);
    second_obj = make_hand(face, &watch_second, WATCH_SECOND_W, WATCH_SECOND_H);

    lv_obj_t * title = make_label(face, "HUANGSHAN Pi",
                                  &lv_font_montserrat_16,
                                  lv_color_hex(0xC8A464));
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 16);

    time_label = make_label(face, "00:00:00",
                            &lv_font_montserrat_16,
                            lv_color_hex(0xF3EBDD));
    lv_obj_align(time_label, LV_ALIGN_TOP_MID, 0, 40);

    lv_obj_t * status = make_label(face, "390x450 | LVGL 9.4",
                                   &lv_font_montserrat_14,
                                   lv_color_hex(0x9A8E7D));
    lv_obj_align(status, LV_ALIGN_BOTTOM_MID, 0, -42);

    fps_label = make_label(face, "FPS 0.0",
                           &lv_font_montserrat_14,
                           lv_color_hex(0x9A8E7D));
    lv_obj_align(fps_label, LV_ALIGN_BOTTOM_MID, 0, -18);

    lv_timer_create(clock_timer_cb, 1000, NULL);
    lv_timer_create(ring_timer_cb, 50, NULL);
    lv_timer_create(fps_timer_cb, 500, NULL);
    clock_timer_cb(NULL);
}

#endif
