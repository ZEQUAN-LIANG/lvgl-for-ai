#include "sift_watch.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "app.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#if defined(LVGL_AI_EZIP_ASSETS) && (defined(ACC_USING_LSM6DSL) || defined(CONFIG_ACC_USING_LSM6DSL))
#define SIFT_HAS_IMU 1
#include "rtthread.h"
#include "st_lsm6dsl_sensor_v1.h"
#include "bf0_hal.h"
#include "drv_io.h"
#else
#define SIFT_HAS_IMU 0
#endif

/* Physical keys and the vibration motor only exist on the SiFli SDK build.
 * The exporter prepends lvgl_ai_sdk.h, which defines LVGL_AI_EZIP_ASSETS and
 * pulls in rtthread.h; headless builds get empty stubs. */
#if defined(LVGL_AI_EZIP_ASSETS)
#define SIFT_HAS_KEY 1
#include "rtdevice.h"
#  if defined(BSP_KEY1_PIN)
#    define SIFT_KEY1_PIN BSP_KEY1_PIN
#  else
#    define SIFT_KEY1_PIN 34
#  endif
#  if defined(BSP_KEY2_PIN)
#    define SIFT_KEY2_PIN BSP_KEY2_PIN
#  else
#    define SIFT_KEY2_PIN 43
#  endif
#  define SIFT_VIBE_PIN 20
#else
#define SIFT_HAS_KEY 0
#endif

#if defined(__has_include)
#  if __has_include("app_mem.h")
#    include "app_mem.h"
#    define SIFT_HAS_APP_CANVAS_ALLOC 1
#  endif
#endif

#define SIFT_W 390
#define SIFT_H 450
#define SIFT_PANEL_RADIUS 44
#define SIFT_CELL 3
#define SIFT_COLS 60
#define SIFT_ROWS 80
#define SIFT_GRID_X0 105
#define SIFT_GRID_Y0 106
#define SIFT_NECK_ROW 40
#define SIFT_NECK_Y 226
#define SIFT_HG_TOP 106
#define SIFT_HG_BOTTOM 346
#define SIFT_SIM_STEP_MS 66U
#define SIFT_RENDER_MS 40U
#define SIFT_SWIPE_MIN 42
#define SIFT_SWIPE_LONG 90
/* This board's accelerometer z axis points into the screen: face-up is
 * negative, face-down is positive. */
#define SIFT_IMU_FACE_DOWN_MG (550)
#define SIFT_IMU_FACE_UP_MG (-250)
#define SIFT_IMU_FLIP_COOLDOWN_MS 1200U
#define SIFT_TIMER_ALERT_MS 6000U
#define SIFT_IDLE_DIM_MS 42000U

#define RGB565(r, g, b) ((uint16_t)((((r) & 0xF8U) << 8) | (((g) & 0xFCU) << 3) | ((b) >> 3)))

static const uint16_t COL_INK = RGB565(4, 11, 8);
static const uint16_t COL_INK2 = RGB565(7, 19, 14);
static const uint16_t COL_GLASS = RGB565(9, 25, 20);
static const uint16_t COL_LINE = RGB565(29, 51, 41);
static const uint16_t COL_LINE2 = RGB565(43, 71, 56);
static const uint16_t COL_PAPER = RGB565(226, 238, 221);
static const uint16_t COL_MUTED = RGB565(120, 148, 132);
static const uint16_t COL_DIM = RGB565(64, 87, 75);
static const uint16_t COL_MINT = RGB565(114, 223, 186);
static const uint16_t COL_MINT_HI = RGB565(193, 255, 232);
static const uint16_t COL_MINT_DIM = RGB565(44, 109, 89);
static const uint16_t COL_SAND = RGB565(243, 183, 79);
static const uint16_t COL_SAND_HI = RGB565(255, 213, 125);
static const uint16_t COL_SAND_DIM = RGB565(168, 103, 44);
static const uint16_t COL_SAND_PALE = RGB565(255, 227, 160);
static const uint16_t COL_WOOD = RGB565(157, 93, 47);
static const uint16_t COL_WOOD_DARK = RGB565(72, 40, 21);
static const uint16_t COL_WOOD_HI = RGB565(215, 150, 80);
static const uint16_t COL_CORAL = RGB565(255, 121, 89);
static const uint16_t COL_SKY = RGB565(143, 203, 214);
static const uint16_t COL_RAIN = RGB565(95, 144, 155);
static const uint16_t COL_CLOUD = RGB565(168, 186, 178);

/* 5x7 font. '~' is the degree symbol. */
static const char font_chars[] = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:.-+%/?~";
static const uint8_t font_rows[][7] = {
    {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, /* space */
    {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}, /* A */
    {0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E}, /* B */
    {0x0F, 0x10, 0x10, 0x10, 0x10, 0x10, 0x0F}, /* C */
    {0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E}, /* D */
    {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F}, /* E */
    {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10}, /* F */
    {0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0E}, /* G */
    {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}, /* H */
    {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x1F}, /* I */
    {0x07, 0x02, 0x02, 0x02, 0x12, 0x12, 0x0C}, /* J */
    {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11}, /* K */
    {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F}, /* L */
    {0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11}, /* M */
    {0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11}, /* N */
    {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E}, /* O */
    {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10}, /* P */
    {0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D}, /* Q */
    {0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11}, /* R */
    {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E}, /* S */
    {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04}, /* T */
    {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E}, /* U */
    {0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04}, /* V */
    {0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11}, /* W */
    {0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11}, /* X */
    {0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04}, /* Y */
    {0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F}, /* Z */
    {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E}, /* 0 */
    {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E}, /* 1 */
    {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F}, /* 2 */
    {0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E}, /* 3 */
    {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02}, /* 4 */
    {0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E}, /* 5 */
    {0x0E, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x0E}, /* 6 */
    {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08}, /* 7 */
    {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E}, /* 8 */
    {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x01, 0x0E}, /* 9 */
    {0x00, 0x04, 0x04, 0x00, 0x04, 0x04, 0x00}, /* : */
    {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C}, /* . */
    {0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00}, /* - */
    {0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00}, /* + */
    {0x19, 0x1B, 0x04, 0x04, 0x08, 0x1B, 0x13}, /* % */
    {0x01, 0x02, 0x02, 0x04, 0x08, 0x08, 0x10}, /* / */
    {0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04}, /* ? */
    {0x0E, 0x0A, 0x0E, 0x00, 0x00, 0x00, 0x00}, /* ~ degree */
};

/* Interior half widths for the top chamber, sampled every 3 px. */
static const uint8_t hg_half_widths[40] = {
    75, 75, 75, 74, 74, 74, 73, 73, 72, 71,
    71, 70, 69, 68, 66, 65, 64, 63, 61, 60,
    58, 56, 55, 53, 51, 49, 47, 45, 43, 40,
    38, 35, 33, 30, 27, 25, 21, 18, 14, 10,
};

static const int16_t sw_ring_x[60] = {
    195, 205, 216, 226, 235, 244, 253, 261, 269, 275, 281, 285, 289, 292, 293,
    294, 293, 292, 289, 285, 281, 275, 269, 261, 253, 244, 235, 226, 216, 205,
    195, 185, 174, 164, 155, 145, 137, 129, 121, 115, 109, 105, 101, 98, 97,
    96, 97, 98, 101, 105, 109, 115, 121, 129, 137, 145, 155, 164, 174, 185,
};
static const int16_t sw_ring_y[60] = {
    89, 90, 91, 94, 98, 102, 108, 114, 122, 130, 138, 148, 157, 167, 178,
    188, 198, 209, 219, 228, 238, 246, 254, 262, 268, 274, 278, 282, 285, 286,
    287, 286, 285, 282, 278, 274, 268, 262, 254, 246, 238, 228, 219, 209, 198,
    188, 178, 167, 157, 148, 138, 130, 122, 114, 108, 102, 98, 94, 91, 90,
};

typedef enum {
    VIEW_WATCH = 0,
    VIEW_APPS,
    VIEW_TIMER,
    VIEW_STOPWATCH,
    VIEW_WEATHER,
    VIEW_SETTINGS
} sift_view_t;

typedef struct {
    int hour;
    int minute;
    int second;
    int day;
    int month;
    int mday;
    bool valid;
} sift_clock_t;

typedef struct {
    uint16_t total;
    uint16_t top;
    uint16_t bottom;
    uint16_t flow;
} sift_stats_t;

typedef struct {
    sift_view_t view;
    uint8_t app_index;
    uint8_t settings_index;
    bool auto_drift;
    bool h24;
    bool dim_on;
    bool sensor_live;
    bool auto_now;
    bool manual;
    uint32_t manual_until;
    uint32_t last_input;
    int32_t target_roll;
    int32_t target_pitch;
    int32_t smooth_roll;
    int32_t smooth_pitch;
    int32_t sensor_roll;
    int32_t sensor_pitch;
    uint32_t last_tick;
    uint32_t sim_accum;
    uint8_t *sand;
    uint8_t *sand_next;
    uint8_t step_phase;
    sift_stats_t stats;
    uint32_t empty_since;
    uint32_t notice_until;
    char notice[24];
    int flips;
    uint32_t timer_duration;
    uint32_t timer_remaining;
    uint32_t timer_end_at;
    uint32_t timer_done_at;
    uint32_t timer_alert_until;
    uint8_t timer_selected;
    bool timer_running;
    bool sw_running;
    uint32_t sw_start_at;
    uint32_t sw_elapsed;
    uint32_t sw_laps[8];
    uint8_t sw_lap_count;
    char weather_unit;
    uint32_t clock_epoch;
    uint32_t clock_base_tick;
    uint32_t clock_last_second;
    sift_clock_t clock;
    bool dimmed;
    uint32_t dim_start;
    bool touch_active;
    bool touch_moved;
    bool touch_swiping;
    bool touch_suppress;
    int touch_start_x;
    int touch_start_y;
    int touch_start_roll;
    int touch_start_pitch;
    uint32_t touch_at;
} sift_state_t;

static sift_state_t s;
static uint16_t *s_fb;
static lv_obj_t *s_canvas;
static lv_group_t *s_group;
static lv_timer_t *s_render_timer;
static uint8_t s_sand_a[SIFT_COLS * SIFT_ROWS];
static uint8_t s_sand_b[SIFT_COLS * SIFT_ROWS];
static uint8_t s_inside[SIFT_COLS * SIFT_ROWS];
static uint32_t s_rand_state = 0x51F7A11DU;

static void sift_render(void);
static void sift_tick_cb(lv_timer_t *timer);
static void sift_canvas_event_cb(lv_event_t *event);
static void sift_handle_tap(int x, int y);
static void sift_handle_key(uint32_t key);
static void sift_handle_swipe(int32_t dx, int32_t dy);
static void sift_flip(void);
static void weather_values(int *temp_c, int *high_c, int *low_c, int *humidity,
                           int *wind, bool *night, int *condition);
static int weather_temp(int celsius);
static void sift_imu_zero(void);
static void vibe_pulse(void);

static int32_t clamp_i32(int32_t value, int32_t low, int32_t high)
{
    if(value < low) return low;
    if(value > high) return high;
    return value;
}

static uint32_t sift_rand(void)
{
    s_rand_state ^= s_rand_state << 13;
    s_rand_state ^= s_rand_state >> 17;
    s_rand_state ^= s_rand_state << 5;
    return s_rand_state;
}

static uint32_t sift_hash(int32_t x, int32_t y)
{
    uint32_t h = (uint32_t)x * 374761393U + (uint32_t)y * 668265263U;
    h = (h ^ (h >> 13)) * 1274126177U;
    return h ^ (h >> 16);
}

static void put_px(int32_t x, int32_t y, uint16_t color)
{
    if(x < 0 || x >= SIFT_W || y < 0 || y >= SIFT_H) return;
    s_fb[y * SIFT_W + x] = color;
}

static void fill_rect(int32_t x, int32_t y, int32_t w, int32_t h, uint16_t color)
{
    int32_t x0 = x < 0 ? 0 : x;
    int32_t y0 = y < 0 ? 0 : y;
    int32_t x1 = x + w > SIFT_W ? SIFT_W : x + w;
    int32_t y1 = y + h > SIFT_H ? SIFT_H : y + h;
    for(int32_t yy = y0; yy < y1; yy++) {
        uint16_t *row = s_fb + yy * SIFT_W;
        for(int32_t xx = x0; xx < x1; xx++) row[xx] = color;
    }
}

static void hline(int32_t x, int32_t y, int32_t w, uint16_t color)
{
    fill_rect(x, y, w, 1, color);
}

static void vline(int32_t x, int32_t y, int32_t h, uint16_t color)
{
    fill_rect(x, y, 1, h, color);
}

static void stroke_rect(int32_t x, int32_t y, int32_t w, int32_t h, uint16_t color, int32_t thickness)
{
    fill_rect(x, y, w, thickness, color);
    fill_rect(x, y + h - thickness, w, thickness, color);
    fill_rect(x, y, thickness, h, color);
    fill_rect(x + w - thickness, y, thickness, h, color);
}

static void fill_disc(int32_t cx, int32_t cy, int32_t radius, uint16_t color)
{
    for(int32_t dy = -radius; dy <= radius; dy += 3) {
        int32_t rem = radius * radius - dy * dy;
        if(rem < 0) rem = 0;
        int32_t half = 0;
        while((half + 1) * (half + 1) <= rem) half++;
        fill_rect(cx - half, cy + dy, half * 2, 3, color);
    }
}

static void draw_line(int32_t x1, int32_t y1, int32_t x2, int32_t y2, uint16_t color, int32_t size)
{
    int32_t dx = x2 - x1;
    int32_t dy = y2 - y1;
    int32_t steps = dx > 0 ? dx : -dx;
    int32_t ay = dy > 0 ? dy : -dy;
    if(ay > steps) steps = ay;
    if(steps <= 0) {
        fill_rect(x1, y1, size, size, color);
        return;
    }
    for(int32_t i = 0; i <= steps; i += size) {
        int32_t x = x1 + (int64_t)dx * i / steps;
        int32_t y = y1 + (int64_t)dy * i / steps;
        fill_rect(x, y, size, size, color);
    }
}

static const uint8_t *font_for(char ch)
{
    if(ch >= 'a' && ch <= 'z') ch = (char)(ch - 'a' + 'A');
    if(ch == ' ' ) return font_rows[0];
    const char *found = strchr(font_chars, ch);
    if(found == NULL || found == font_chars) return font_rows[0];
    size_t index = (size_t)(found - font_chars);
    if(index >= sizeof(font_rows) / sizeof(font_rows[0])) return font_rows[0];
    return font_rows[index];
}

static int32_t text_width(const char *text, int32_t scale)
{
    size_t len = strlen(text);
    if(len == 0) return 0;
    return (int32_t)(len * 6 * (size_t)scale - (size_t)scale);
}

static void draw_glyph(const uint8_t *glyph, int32_t x, int32_t y, int32_t scale, uint16_t color)
{
    for(int32_t row = 0; row < 7; row++) {
        uint8_t bits = glyph[row];
        int32_t start = -1;
        for(int32_t col = 0; col <= 5; col++) {
            bool on = col < 5 && (bits & (1U << (4 - col))) != 0U;
            if(on && start < 0) start = col;
            if(!on && start >= 0) {
                fill_rect(x + start * scale, y + row * scale, (col - start) * scale, scale, color);
                start = -1;
            }
        }
    }
}

static void draw_text(const char *text, int32_t x, int32_t y, int32_t scale, uint16_t color, int align)
{
    int32_t width = text_width(text, scale);
    if(align == 1) x -= width / 2;
    else if(align == 2) x -= width;
    size_t len = strlen(text);
    for(size_t i = 0; i < len; i++) {
        const uint8_t *glyph = font_for(text[i]);
        draw_glyph(glyph, x, y, scale, color);
        x += 6 * scale;
    }
}

static uint16_t dim_color(uint16_t color, int32_t percent)
{
    int32_t r = (color >> 11) & 0x1F;
    int32_t g = (color >> 5) & 0x3F;
    int32_t b = color & 0x1F;
    r = r * (100 - percent) / 100;
    g = g * (100 - percent) / 100;
    b = b * (100 - percent) / 100;
    return (uint16_t)((r << 11) | (g << 5) | b);
}

static const char *month_name(int month)
{
    static const char *names[] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};
    return (month >= 0 && month < 12) ? names[month] : "JAN";
}

static const char *day_name(int day)
{
    static const char *names[] = {"SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"};
    return (day >= 0 && day < 7) ? names[day] : "THU";
}

static void clock_update(void)
{
    uint32_t elapsed = (lv_tick_get() - s.clock_base_tick) / 1000U;
    uint32_t second = (s.clock_epoch + elapsed) & 0x3FFFFFFFU;
    if(second == s.clock_last_second && s.clock.valid) return;
    s.clock_last_second = second;

    time_t raw = (time_t)(s.clock_epoch + elapsed);
    struct tm *tm = localtime(&raw);
    if(tm != NULL) {
        s.clock.hour = tm->tm_hour;
        s.clock.minute = tm->tm_min;
        s.clock.second = tm->tm_sec;
        s.clock.day = tm->tm_wday;
        s.clock.month = tm->tm_mon;
        s.clock.mday = tm->tm_mday;
        s.clock.valid = true;
    }
    else {
        uint32_t uptime = lv_tick_get() / 1000U;
        s.clock.hour = (int)((uptime / 3600U) % 24U);
        s.clock.minute = (int)((uptime / 60U) % 60U);
        s.clock.second = (int)(uptime % 60U);
        s.clock.day = 4;
        s.clock.month = 10;
        s.clock.mday = 12;
        s.clock.valid = false;
    }
}

static int clock_hour(void)
{
    if(s.h24) return s.clock.hour;
    int hour = s.clock.hour % 12;
    return hour == 0 ? 12 : hour;
}

static const char *clock_ampm(void)
{
    return s.clock.hour >= 12 ? "PM" : "AM";
}

static uint32_t sw_current_elapsed(uint32_t now)
{
    return s.sw_elapsed + (s.sw_running ? now - s.sw_start_at : 0U);
}

static void sw_toggle(uint32_t now)
{
    if(s.sw_running) {
        s.sw_elapsed = sw_current_elapsed(now);
        s.sw_running = false;
    }
    else {
        s.sw_start_at = now;
        s.sw_running = true;
    }
    s.last_input = now;
    printf("[sift_watch] stopwatch=%s\n", s.sw_running ? "run" : "stop");
}

static void sw_lap(uint32_t now)
{
    if(!s.sw_running) return;
    if(s.sw_lap_count < 8) {
        s.sw_laps[s.sw_lap_count++] = sw_current_elapsed(now);
    }
    s.last_input = now;
    printf("[sift_watch] lap=%u\n", (unsigned)s.sw_lap_count);
}

static void sw_reset(void)
{
    s.sw_running = false;
    s.sw_elapsed = 0;
    s.sw_lap_count = 0;
    s.last_input = lv_tick_get();
}

static void timer_reset(void)
{
    s.timer_running = false;
    s.timer_remaining = s.timer_duration;
    s.timer_end_at = 0;
    s.timer_done_at = 0;
    s.timer_alert_until = 0;
    s.last_input = lv_tick_get();
}

static void timer_select(uint8_t index)
{
    static const uint32_t presets[] = {60000U, 180000U, 300000U, 600000U};
    if(index > 3) index = 0;
    s.timer_selected = index;
    s.timer_duration = presets[index];
    timer_reset();
}

static void timer_toggle(uint32_t now)
{
    if(s.timer_running) {
        s.timer_remaining = s.timer_end_at > now ? s.timer_end_at - now : 0U;
        s.timer_running = false;
        s.last_input = now;
        return;
    }
    if(s.timer_remaining == 0U) s.timer_remaining = s.timer_duration;
    s.timer_end_at = now + s.timer_remaining;
    s.timer_running = true;
    s.timer_done_at = 0;
    s.timer_alert_until = 0;
    s.last_input = now;
    printf("[sift_watch] timer start remaining=%u\n", (unsigned)s.timer_remaining);
}

static void timer_update(uint32_t now)
{
    if(!s.timer_running) return;
    if((int32_t)(s.timer_end_at - now) > 0) {
        s.timer_remaining = s.timer_end_at - now;
        return;
    }
    s.timer_running = false;
    s.timer_remaining = 0;
    s.timer_done_at = now;
    s.timer_alert_until = now + SIFT_TIMER_ALERT_MS;
    printf("[sift_watch] timer done\n");
}

static void sand_recount(void)
{
    uint16_t top = 0;
    uint16_t bottom = 0;
    for(int32_t y = 0; y < SIFT_ROWS; y++) {
        for(int32_t x = 0; x < SIFT_COLS; x++) {
            if(s.sand[y * SIFT_COLS + x] == 0) continue;
            if(y < SIFT_NECK_ROW) top++;
            else bottom++;
        }
    }
    s.stats.top = top;
    s.stats.bottom = bottom;
    s.stats.total = top + bottom;
}

static void sand_init(void)
{
    memset(s_sand_a, 0, sizeof(s_sand_a));
    memset(s_sand_b, 0, sizeof(s_sand_b));
    s.sand = s_sand_a;
    s.sand_next = s_sand_b;
    s.step_phase = 0;
    s.flips = 0;
    s.empty_since = 0;

    for(int32_t y = 0; y < SIFT_ROWS; y++) {
        int32_t cell_y = SIFT_GRID_Y0 + y * SIFT_CELL + 1;
        if(cell_y >= SIFT_NECK_Y) continue;
        for(int32_t x = 0; x < SIFT_COLS; x++) {
            int32_t index = y * SIFT_COLS + x;
            if(!s_inside[index]) continue;
            if(y * SIFT_CELL < 20) continue;
            uint8_t value = (uint8_t)(1 + (sift_rand() % 4));
            s.sand[index] = value;
        }
    }
    sand_recount();
}

static void sand_mirror(void)
{
    memset(s.sand_next, 0, sizeof(s_sand_b));
    for(int32_t y = 0; y < SIFT_ROWS; y++) {
        for(int32_t x = 0; x < SIFT_COLS; x++) {
            uint8_t value = s.sand[y * SIFT_COLS + x];
            if(value != 0) {
                s.sand_next[(SIFT_ROWS - 1 - y) * SIFT_COLS + x] = value;
            }
        }
    }
    uint8_t *tmp = s.sand;
    s.sand = s.sand_next;
    s.sand_next = tmp;
    s.empty_since = 0;
    sand_recount();
}

static void sift_flip(void)
{
    sand_mirror();
    s.flips++;
    s.last_input = lv_tick_get();
    snprintf(s.notice, sizeof(s.notice), "FLIP %02d", s.flips);
    s.notice_until = lv_tick_get() + 1200U;
    vibe_pulse();
    printf("[sift_watch] flip=%d source=sensor\n", s.flips);
}

static void sand_step(void)
{
    uint8_t *src = s.sand;
    uint8_t *dst = s.sand_next;
    memset(dst, 0, sizeof(s_sand_b));
    int32_t bias = s.smooth_roll > 3 ? 1 : (s.smooth_roll < -3 ? -1 : 0);
    bool strong = s.smooth_roll > 18 || s.smooth_roll < -18;
    bool reverse = (s.step_phase++ & 1U) != 0U;
    uint16_t crossed = 0;

    for(int32_t y = SIFT_ROWS - 1; y >= 0; y--) {
        for(int32_t n = 0; n < SIFT_COLS; n++) {
            int32_t x = reverse ? SIFT_COLS - 1 - n : n;
            int32_t index = y * SIFT_COLS + x;
            uint8_t value = src[index];
            if(value == 0) continue;
            if((sift_rand() % 100U) < 48U) {
                if(dst[index] == 0) dst[index] = value;
                continue;
            }

            int32_t side = bias != 0 ? bias : ((sift_rand() & 1U) ? 1 : -1);
            int32_t moves[4][2];
            int32_t move_count = 0;
            if(bias != 0) {
                moves[move_count][0] = side;
                moves[move_count][1] = 1;
                move_count++;
            }
            moves[move_count][0] = 0;
            moves[move_count][1] = 1;
            move_count++;
            moves[move_count][0] = -side;
            moves[move_count][1] = 1;
            move_count++;
            if(strong) {
                moves[move_count][0] = side;
                moves[move_count][1] = 0;
                move_count++;
            }

            bool moved = false;
            for(int32_t m = 0; m < move_count; m++) {
                int32_t nx = x + moves[m][0];
                int32_t ny = y + moves[m][1];
                if(nx < 0 || nx >= SIFT_COLS || ny < 0 || ny >= SIFT_ROWS) continue;
                int32_t ni = ny * SIFT_COLS + nx;
                if(!s_inside[ni] || src[ni] != 0 || dst[ni] != 0) continue;
                src[index] = 0;
                dst[ni] = value;
                if(ny >= SIFT_NECK_ROW && y < SIFT_NECK_ROW) crossed++;
                moved = true;
                break;
            }
            if(!moved && dst[index] == 0) dst[index] = value;
        }
    }

    uint8_t *tmp = s.sand;
    s.sand = s.sand_next;
    s.sand_next = tmp;
    uint32_t instant = (uint32_t)crossed * 12U;
    s.stats.flow = (uint16_t)((s.stats.flow * 7U + instant * 2U) / 10U);
    sand_recount();
}

static void update_tilt(uint32_t now)
{
    bool manual = now < s.manual_until;
    s.manual = manual;

    if(s.sensor_live && !manual) {
        s.target_roll = s.sensor_roll;
        s.target_pitch = s.sensor_pitch;
        s.auto_now = false;
    }
    else if(s.view == VIEW_WATCH && s.auto_drift && !manual) {
        int32_t phase = (int32_t)((now / 47U) % 360U);
        int32_t triangle = phase < 180 ? phase : 360 - phase;
        s.target_roll = (triangle - 90) * 13 / 90;
        s.target_pitch = ((phase < 180 ? phase : 360 - phase) - 90) * 5 / 90;
        s.auto_now = true;
    }
    else if(!manual) {
        s.auto_now = false;
        s.target_roll = (s.target_roll * 7) / 8;
        s.target_pitch = (s.target_pitch * 7) / 8;
    }
    else {
        s.auto_now = false;
    }

    if(s.sensor_live && manual) s.auto_now = false;

    int32_t ease = s.sensor_live && !manual ? 2 : 5;
    s.smooth_roll += (s.target_roll - s.smooth_roll) / ease;
    s.smooth_pitch += (s.target_pitch - s.smooth_pitch) / ease;
}

static void update_idle(uint32_t now)
{
    if(s.view == VIEW_WATCH && s.dim_on && now - s.last_input > SIFT_IDLE_DIM_MS) {
        if(!s.dimmed) {
            s.dimmed = true;
            s.dim_start = now;
        }
    }
    else {
        s.dimmed = false;
    }
}

static int32_t dim_percent(uint32_t now)
{
    if(!s.dimmed) return 0;
    uint32_t age = now - s.dim_start;
    if(age > 1200U) return 60;
    return (int32_t)(age * 60U / 1200U);
}

static void draw_background(void)
{
    fill_rect(0, 0, SIFT_W, SIFT_H, COL_INK);

    /* A sparse dot field keeps the dark panel from looking empty. */
    for(int32_t y = 8; y < SIFT_H; y += 7) {
        for(int32_t x = 8; x < SIFT_W; x += 7) {
            uint32_t h = sift_hash(x, y);
            if(h % 100U > 94U) {
                put_px(x, y, (h & 1U) ? COL_LINE : COL_MINT_DIM);
            }
        }
    }

    /* Fixed star clusters. */
    for(int32_t i = 0; i < 30; i++) {
        int32_t x = (int32_t)(sift_hash(i, 3) % SIFT_W);
        int32_t y = (int32_t)(sift_hash(i, 7) % SIFT_H);
        uint16_t color = (sift_hash(i, 11) & 1U) ? COL_DIM : COL_MINT_DIM;
        put_px(x, y, color);
        if((i % 7) == 0) {
            put_px(x - 2, y, color);
            put_px(x + 2, y, color);
            put_px(x, y - 2, color);
            put_px(x, y + 2, color);
        }
    }

    /* The 1.85" AMOLED has rounded glass; the four corner cutouts are
     * painted in the panel mask after every view is rendered. */
}

static void draw_battery(int32_t x, int32_t y)
{
    fill_rect(x, y, 22, 10, COL_DIM);
    fill_rect(x + 22, y + 3, 2, 4, COL_DIM);
    fill_rect(x + 2, y + 2, 18, 6, COL_INK);
    for(int32_t i = 0; i < 4; i++) fill_rect(x + 3 + i * 4, y + 3, 3, 4, COL_MINT);
}

static void draw_apps_icon(int32_t x, int32_t y)
{
    for(int32_t row = 0; row < 3; row++) {
        for(int32_t col = 0; col < 3; col++) {
            fill_rect(x + col * 4, y + row * 4, 2, 2, COL_MUTED);
        }
    }
}

static void draw_back_chevron(int32_t x, int32_t y)
{
    for(int32_t i = 0; i < 7; i++) {
        int32_t dx = 8 - (i < 4 ? i * 2 : (6 - i) * 2);
        fill_rect(x + dx, y + i * 2, 2, 2, COL_MINT);
    }
}

static void draw_brand_header(void)
{
    if((lv_tick_get() / 440U) % 2U == 0U) fill_rect(22, 15, 6, 6, COL_SAND);
    else fill_rect(22, 15, 6, 6, COL_SAND_DIM);
    draw_text("SIFT", 34, 13, 2, COL_MINT, 0);
    draw_apps_icon(100, 15);
    draw_text("APPS", 114, 16, 1, COL_MUTED, 0);
    draw_battery(344, 14);
}

static void draw_sensor_label(void)
{
    const char *label = s.sensor_live ? "6-AXIS LIVE" : (s.auto_now ? "6-AXIS AUTO" : "6-AXIS SIM");
    uint16_t color = s.sensor_live ? COL_MINT : COL_DIM;
    draw_text(label, 195, 17, 1, color, 1);
}

static void draw_clock(void)
{
    char hh[4];
    char mm[4];
    char ss[4];
    snprintf(hh, sizeof(hh), "%02d", clock_hour());
    snprintf(mm, sizeof(mm), "%02d", s.clock.minute);
    snprintf(ss, sizeof(ss), "%02d", s.clock.second);

    draw_text(hh, 22, 32, 6, COL_INK2, 0);
    draw_text(hh, 20, 30, 6, COL_PAPER, 0);
    int32_t colon_x = 94;
    if((lv_tick_get() % 1000U) < 540U || s.dimmed) {
        draw_text(":", colon_x, 32, 6, COL_SAND, 0);
    }
    draw_text(mm, 130, 32, 6, COL_PAPER, 0);
    if(!s.h24) draw_text(clock_ampm(), 208, 64, 2, COL_SAND, 0);

    draw_text(day_name(s.clock.day), 368, 35, 2, COL_MINT, 2);
    char date[10];
    snprintf(date, sizeof(date), "%02d %s", s.clock.mday, month_name(s.clock.month));
    draw_text(date, 368, 53, 2, COL_PAPER, 2);
    draw_text("SEC", 342, 78, 1, COL_MUTED, 2);
    draw_text(ss, 368, 70, 2, COL_SAND, 2);

    hline(22, 87, 346, COL_LINE);
    for(int32_t x = 22; x <= 368; x += 43) fill_rect(x, 87, 1, 2, COL_MINT_DIM);
    fill_rect(194, 86, 3, 3, COL_SAND);
}

static int32_t hg_half_width(int32_t row)
{
    if(row < 0) row = 0;
    if(row > 39) row = 39;
    return hg_half_widths[row];
}

static void draw_cap(int32_t y)
{
    fill_rect(195 - 108, y, 216, 14, COL_WOOD_DARK);
    fill_rect(195 - 106, y + 2, 212, 10, COL_WOOD);
    fill_rect(195 - 103, y + 3, 206, 2, COL_WOOD_HI);
    for(int32_t x = 195 - 84; x <= 195 + 84; x += 21) {
        fill_rect(x, y + 4, 1, 7, COL_WOOD_DARK);
    }
    fill_rect(195 - 100, y + 5, 4, 4, COL_SAND_DIM);
    fill_rect(195 + 96, y + 5, 4, 4, COL_SAND_DIM);
}

static void draw_hourglass(void)
{
    uint16_t sand_colors[] = {COL_SAND, COL_SAND_HI, COL_SAND_DIM, COL_SAND_PALE};

    /* Warm glow behind the glass. */
    for(int32_t y = 110; y < 350; y += 9) {
        for(int32_t x = 45; x < 345; x += 9) {
            int32_t dx = x - 195;
            int32_t dy = y - 226;
            if(dx * dx / 4 + dy * dy < 18000 && (sift_hash(x, y) % 100U) > 82U) {
                put_px(x, y, COL_INK2);
            }
        }
    }

    /* Wooden posts. */
    fill_rect(93, 98, 7, 256, COL_WOOD_DARK);
    fill_rect(94, 100, 2, 252, COL_WOOD);
    fill_rect(96, 102, 1, 210, COL_WOOD_HI);
    fill_rect(291, 98, 7, 256, COL_WOOD_DARK);
    fill_rect(292, 100, 2, 252, COL_WOOD);
    fill_rect(294, 102, 1, 210, COL_WOOD_HI);

    /* Glass body. */
    for(int32_t row = 0; row < SIFT_ROWS; row++) {
        int32_t half = hg_half_width(row < 40 ? row : 79 - row) + 7;
        int32_t y = SIFT_HG_TOP + row * SIFT_CELL;
        fill_rect(195 - half, y, half * 2, SIFT_CELL, COL_GLASS);
        fill_rect(195 - half, y, 2, SIFT_CELL, row < 4 || row > 75 ? COL_MINT : COL_MINT_DIM);
        fill_rect(195 + half - 2, y, 2, SIFT_CELL, row < 4 || row > 75 ? COL_MINT : COL_MINT_DIM);
    }

    /* Sand grains. */
    for(int32_t y = 0; y < SIFT_ROWS; y++) {
        for(int32_t x = 0; x < SIFT_COLS; x++) {
            uint8_t value = s.sand[y * SIFT_COLS + x];
            if(value == 0) continue;
            int32_t px = SIFT_GRID_X0 + x * SIFT_CELL;
            int32_t py = SIFT_GRID_Y0 + y * SIFT_CELL;
            uint16_t color = sand_colors[(value - 1) & 3];
            fill_rect(px, py, SIFT_CELL, SIFT_CELL, color);
            if(y == 0 || s.sand[(y - 1) * SIFT_COLS + x] == 0) {
                fill_rect(px, py, SIFT_CELL, 1, COL_SAND_HI);
            }
        }
    }

    bool nearly_empty = s.stats.total > 0 &&
                        (s.stats.top * 100U / s.stats.total) < 5U;
    if(!nearly_empty && s.stats.flow > 2U) {
        fill_rect(181, 224, 28, 3, COL_SAND);
        fill_rect(188, 220, 2, 9, COL_SAND_HI);
        fill_rect(200, 222, 2, 7, COL_SAND_HI);
    }

    draw_cap(92);
    draw_cap(346);
}

static void draw_button(int32_t x, int32_t y, int32_t w, int32_t h, const char *label,
                        uint16_t fill, uint16_t border, uint16_t text)
{
    fill_rect(x, y, w, h, fill);
    stroke_rect(x, y, w, h, border, 2);
    draw_text(label, x + w / 2, y + (h - 14) / 2, 2, text, 1);
}

static void draw_watch_footer(void)
{
    hline(22, 370, 346, COL_LINE);

    char value[16];
    snprintf(value, sizeof(value), "%+d~", (int)s.smooth_roll);
    draw_text("ROLL", 22, 376, 1, COL_MUTED, 0);
    draw_text(value, 22, 385, 2, COL_PAPER, 0);

    uint32_t percent = s.stats.total == 0 ? 0 : (uint32_t)s.stats.top * 100U / s.stats.total;
    if(percent < 5U) percent = 0;
    snprintf(value, sizeof(value), "%u%%", (unsigned)percent);
    draw_text("SAND", 195, 376, 1, COL_MUTED, 1);
    draw_text(value, 195, 385, 2, COL_SAND, 1);

    snprintf(value, sizeof(value), "%02u", (unsigned)(s.stats.flow > 99U ? 99U : s.stats.flow));
    draw_text("FLOW", 368, 376, 1, COL_MUTED, 2);
    draw_text(value, 368, 385, 2, COL_MINT, 2);

    bool empty = s.stats.total > 0 && (s.stats.top * 100U / s.stats.total) < 5U;
    bool pulse = ((lv_tick_get() / 230U) % 2U) != 0U;
    uint16_t flip_color = s.sensor_live ? (empty && pulse ? COL_SAND_HI : COL_SAND) : COL_DIM;
    draw_text(s.sensor_live ? "SENSOR FLIP / TURN WATCH FACE DOWN"
                            : "SENSOR FLIP / LINK 6-AXIS",
              195, 404, 1, flip_color, 1);

    const char *hint = s.sensor_live ? "SWIPE PAGES  /  DRAG OR TILT"
                                     : "SWIPE PAGES  /  DRAG TILT";
    if(lv_tick_get() < s.notice_until) hint = s.notice;
    draw_text(hint, 195, 419, 1, COL_MUTED, 1);
}

static void draw_watch(void)
{
    draw_brand_header();
    draw_sensor_label();
    draw_clock();
    draw_hourglass();
    draw_watch_footer();
}

static void draw_app_header(const char *title, const char *subtitle)
{
    char time_text[8];
    snprintf(time_text, sizeof(time_text), "%02d:%02d", clock_hour(), s.clock.minute);
    draw_back_chevron(22, 22);
    draw_text(title, 48, 16, 3, COL_PAPER, 0);
    draw_text(time_text, 368, 18, 2, COL_PAPER, 2);
    if(!s.h24) draw_text(clock_ampm(), 368, 34, 1, COL_SAND, 2);
    hline(22, 44, 346, COL_LINE);
    draw_text(subtitle, 22, 52, 1, COL_MUTED, 0);
}

static void draw_mini_hourglass(int32_t cx, int32_t cy, uint16_t color, uint16_t sand)
{
    fill_rect(cx - 15, cy - 18, 30, 4, color);
    fill_rect(cx - 15, cy + 14, 30, 4, color);
    for(int32_t i = 0; i < 7; i++) {
        int32_t half = 14 - i * 2;
        fill_rect(cx - half, cy - 14 + i * 4, 3, 4, color);
        fill_rect(cx + half - 3, cy - 14 + i * 4, 3, 4, color);
        fill_rect(cx - half, cy + 11 - i * 4, 3, 4, color);
        fill_rect(cx + half - 3, cy + 11 - i * 4, 3, 4, color);
    }
    fill_rect(cx - 6, cy - 4, 12, 3, sand);
    fill_rect(cx - 4, cy, 8, 3, sand);
}

static void draw_icon_stopwatch(int32_t cx, int32_t cy)
{
    fill_disc(cx, cy + 2, 18, COL_MINT);
    fill_disc(cx, cy + 2, 14, COL_INK2);
    fill_rect(cx - 3, cy - 23, 6, 7, COL_MINT);
    draw_line(cx, cy + 2, cx, cy - 9, COL_PAPER, 2);
    draw_line(cx, cy + 2, cx + 10, cy + 2, COL_SAND, 2);
    fill_rect(cx - 2, cy, 4, 4, COL_SAND);
}

static void draw_icon_weather(int32_t cx, int32_t cy)
{
    fill_disc(cx - 7, cy - 6, 11, COL_SAND);
    draw_line(cx - 7, cy - 22, cx - 7, cy - 18, COL_SAND, 2);
    draw_line(cx - 7, cy + 6, cx - 7, cy + 10, COL_SAND, 2);
    draw_line(cx - 23, cy - 6, cx - 19, cy - 6, COL_SAND, 2);
    draw_line(cx + 5, cy - 6, cx + 9, cy - 6, COL_SAND, 2);
    draw_line(cx - 18, cy - 17, cx - 15, cy - 14, COL_SAND, 2);
    draw_line(cx + 1, cy - 17, cx + 4, cy - 20, COL_SAND, 2);
    fill_rect(cx + 2, cy + 1, 30, 13, COL_CLOUD);
    fill_rect(cx + 7, cy - 5, 14, 19, COL_CLOUD);
    fill_rect(cx + 20, cy - 2, 11, 16, COL_CLOUD);
}

static void draw_icon_settings(int32_t cx, int32_t cy)
{
    draw_line(cx - 22, cy - 10, cx + 18, cy - 10, COL_MUTED, 2);
    draw_line(cx - 22, cy, cx + 18, cy, COL_MUTED, 2);
    draw_line(cx - 22, cy + 10, cx + 18, cy + 10, COL_MUTED, 2);
    fill_rect(cx - 3, cy - 13, 6, 8, COL_SAND);
    fill_rect(cx + 9, cy - 3, 6, 8, COL_MINT);
    fill_rect(cx - 14, cy + 7, 6, 8, COL_SAND);
}

static void draw_tile_icon(uint8_t index, int32_t cx, int32_t cy)
{
    if(index == 0) draw_mini_hourglass(cx, cy, COL_SAND, COL_SAND_HI);
    else if(index == 1) draw_icon_stopwatch(cx, cy);
    else if(index == 2) draw_icon_weather(cx, cy);
    else draw_icon_settings(cx, cy);
}

static void app_tile_rect(uint8_t index, int32_t *x, int32_t *y, int32_t *w, int32_t *h)
{
    *x = 22 + (index % 2) * 179;
    *y = 82 + (index / 2) * 142;
    *w = 167;
    *h = 130;
}

static const char *app_title(uint8_t index)
{
    static const char *names[] = {"TIMER", "STOPWATCH", "WEATHER", "SETTINGS"};
    return names[index & 3U];
}

static const char *app_subtitle(uint8_t index)
{
    static const char *names[] = {"FOCUS", "PRECISION", "LOCAL SKY", "SYSTEM"};
    return names[index & 3U];
}

static void app_status(uint8_t index, char *out, size_t out_size)
{
    if(index == 0) {
        if(s.timer_running) {
            uint32_t secs = (s.timer_remaining + 999U) / 1000U;
            snprintf(out, out_size, "%02u:%02u", (unsigned)(secs / 60U), (unsigned)(secs % 60U));
        }
        else if(s.timer_remaining == 0U) snprintf(out, out_size, "DONE");
        else snprintf(out, out_size, "%uM", (unsigned)(s.timer_duration / 60000U));
    }
    else if(index == 1) {
        snprintf(out, out_size, "%s", s.sw_running ? "RUN" : (s.sw_elapsed ? "HOLD" : "ZERO"));
    }
    else if(index == 2) {
        int temp_c, high_c, low_c, humidity, wind, condition;
        bool night;
        weather_values(&temp_c, &high_c, &low_c, &humidity, &wind, &night, &condition);
        int temp = weather_temp(temp_c);
        snprintf(out, out_size, "%d~%c", temp, s.weather_unit);
    }
    else {
        snprintf(out, out_size, "%s", s.auto_drift ? "AUTO" : "MANUAL");
    }
}

static void draw_app_drawer(void)
{
    draw_app_header("APPS", "04 PIXEL TOOLS");
    for(uint8_t i = 0; i < 4; i++) {
        int32_t x;
        int32_t y;
        int32_t w;
        int32_t h;
        app_tile_rect(i, &x, &y, &w, &h);
        bool selected = i == s.app_index;
        fill_rect(x, y, w, h, selected ? COL_INK2 : COL_INK);
        stroke_rect(x, y, w, h, selected ? COL_SAND : COL_LINE, selected ? 2 : 1);
        char number[4];
        snprintf(number, sizeof(number), "%02u", (unsigned)(i + 1));
        draw_text(number, x + 10, y + 9, 1, selected ? COL_SAND : COL_DIM, 0);
        if(selected) {
            fill_rect(x + w - 15, y + 8, 4, 4, COL_SAND);
            fill_rect(x + w - 10, y + 12, 4, 4, COL_SAND);
        }
        draw_tile_icon(i, x + w / 2, y + 42);
        draw_text(app_title(i), x + w / 2, y + 70, 2, COL_PAPER, 1);
        draw_text(app_subtitle(i), x + w / 2, y + 91, 1, COL_MUTED, 1);
        char status[16];
        app_status(i, status, sizeof(status));
        draw_text(status, x + w / 2, y + 109, 1, selected ? COL_SAND : COL_MUTED, 1);
        if((i == 0 && s.timer_running) || (i == 1 && s.sw_running)) {
            if((lv_tick_get() / 240U) % 2U == 0U) fill_rect(x + w - 16, y + h - 14, 4, 4, COL_SAND);
        }
    }
    hline(22, 376, 346, COL_LINE);
    draw_text("TAP OPEN  /  SWIPE PAGES", 195, 390, 1, COL_DIM, 1);
}

static void draw_timer_bar(int32_t x, int32_t y, int32_t w, int32_t h, int32_t percent, bool active)
{
    fill_rect(x, y, w, h, COL_INK2);
    stroke_rect(x, y, w, h, COL_LINE2, 1);
    int32_t fill_w = (w - 4) * clamp_i32(percent, 0, 100) / 100;
    if(fill_w > 0) {
        fill_rect(x + 2, y + 2, fill_w, h - 4, active ? COL_SAND : COL_SAND_DIM);
    }
    for(int32_t tx = x + 10; tx < x + w - 4; tx += 10) fill_rect(tx, y + 2, 1, h - 4, COL_INK);
}

static void draw_timer(void)
{
    char time_text[12];
    uint32_t secs = (s.timer_remaining + 999U) / 1000U;
    snprintf(time_text, sizeof(time_text), "%02u:%02u", (unsigned)(secs / 60U), (unsigned)(secs % 60U));
    char subtitle[32];
    snprintf(subtitle, sizeof(subtitle), "COUNTDOWN / %u MIN", (unsigned)(s.timer_duration / 60000U));
    draw_app_header("TIMER", subtitle);

    bool done = s.timer_remaining == 0U && !s.timer_running;
    bool blink = (lv_tick_get() / 260U) % 2U == 0U;
    if(done && blink) stroke_rect(58, 84, 274, 64, COL_SAND, 2);
    draw_text(time_text, 195, 94, 7, done && blink ? COL_SAND : COL_PAPER, 1);
    draw_text("REMAINING", 195, 150, 1, COL_DIM, 1);
    int32_t progress = s.timer_duration ? (int32_t)(s.timer_remaining * 100U / s.timer_duration) : 0;
    draw_timer_bar(45, 170, 300, 15, progress, s.timer_running);

    static const uint32_t presets[] = {60000U, 180000U, 300000U, 600000U};
    static const char *labels[] = {"1M", "3M", "5M", "10M"};
    for(uint8_t i = 0; i < 4; i++) {
        int32_t x = 22 + i * 89;
        bool selected = i == s.timer_selected;
        draw_button(x, 214, 79, 30, labels[i],
                    selected ? COL_INK2 : COL_INK,
                    selected ? COL_SAND : COL_LINE2,
                    selected ? COL_SAND : COL_MUTED);
    }

    const char *status = s.timer_running ? "RUNNING" :
                         (done ? "TIME UP" : (s.timer_remaining < presets[s.timer_selected] ? "PAUSED" : "READY"));
    draw_text(status, 195, 260, 2,
              s.timer_running ? COL_MINT : (done ? COL_SAND : COL_PAPER), 1);

    const char *start_label = s.timer_running ? "PAUSE" : (done ? "AGAIN" : "START");
    draw_button(72, 302, 150, 42, start_label,
                (s.timer_running || done) ? COL_SAND : COL_INK,
                (s.timer_running || done) ? COL_SAND_HI : COL_SAND,
                (s.timer_running || done) ? COL_INK : COL_SAND);
    draw_button(234, 302, 84, 42, "RESET", COL_INK, COL_LINE2, COL_MUTED);
    draw_text("SWIPE PAGES / TAP CONTROLS", 195, 414, 1, COL_DIM, 1);
}

static void draw_stopwatch(void)
{
    uint32_t now = lv_tick_get();
    uint32_t elapsed = sw_current_elapsed(now);
    uint32_t total_sec = elapsed / 1000U;
    char time_text[12];
    char cs_text[6];
    snprintf(time_text, sizeof(time_text), "%02u:%02u", (unsigned)((total_sec / 60U) % 100U), (unsigned)(total_sec % 60U));
    snprintf(cs_text, sizeof(cs_text), ".%02u", (unsigned)((elapsed / 10U) % 100U));
    draw_app_header("STOPWATCH", s.sw_running ? "RUNNING / ENTER TO STOP" : "PRECISION / ENTER TO START");

    uint32_t current = total_sec % 60U;
    for(uint8_t i = 0; i < 60; i++) {
        int32_t trail = (int32_t)((current + 60U - i) % 60U);
        int32_t size = (i % 5 == 0) ? 3 : 2;
        uint16_t color = COL_LINE2;
        if(trail < 6) {
            color = trail == 5 ? COL_MINT : COL_MINT_DIM;
            size = (i % 5 == 0) ? 4 : 3;
        }
        if(i == current) {
            color = COL_SAND;
            size = 4;
        }
        fill_rect(sw_ring_x[i] - size / 2, sw_ring_y[i] - size / 2, size, size, color);
    }

    draw_text(time_text, 195, 157, 6, COL_PAPER, 1);
    draw_text(cs_text, 195, 206, 2, COL_SAND, 1);
    if(s.sw_running && (now / 220U) % 2U == 0U) fill_rect(144, 222, 4, 4, COL_CORAL);

    char lap[28];
    if(s.sw_lap_count > 0) {
        uint32_t ms = s.sw_laps[s.sw_lap_count - 1];
        snprintf(lap, sizeof(lap), "LAP %02u  %02u:%02u.%02u",
                 (unsigned)s.sw_lap_count,
                 (unsigned)((ms / 60000U) % 100U),
                 (unsigned)((ms / 1000U) % 60U),
                 (unsigned)((ms / 10U) % 100U));
    }
    else snprintf(lap, sizeof(lap), "NO LAPS YET");
    draw_text(lap, 195, 296, 1, COL_MUTED, 1);

    draw_button(22, 318, 107, 38, s.sw_running ? "STOP" : "START",
                s.sw_running ? COL_INK2 : COL_MINT,
                s.sw_running ? COL_CORAL : COL_MINT_HI,
                s.sw_running ? COL_CORAL : COL_INK);
    draw_button(141, 318, 107, 38, "LAP", COL_INK,
                s.sw_running ? COL_MINT_DIM : COL_LINE2,
                s.sw_running ? COL_MINT : COL_DIM);
    draw_button(260, 318, 108, 38, "RESET", COL_INK, COL_LINE2, COL_MUTED);
    draw_text("SWIPE PAGES / START LAP RESET", 195, 414, 1, COL_DIM, 1);
}

static void weather_values(int *temp_c, int *high_c, int *low_c, int *humidity,
                           int *wind, bool *night, int *condition)
{
    int seed = s.clock.mday * 13 + s.clock.month * 7 + (s.clock.valid ? 0 : 5);
    int base = 15 + (seed % 8);
    *temp_c = base;
    *high_c = base + 3 + (seed % 3);
    *low_c = base - 4 - (seed % 2);
    *humidity = 48 + (seed * 7) % 36;
    *wind = 5 + (seed * 11) % 17;
    *night = s.clock.hour < 6 || s.clock.hour >= 19;
    *condition = seed % 3;
}

static int weather_temp(int celsius)
{
    return s.weather_unit == 'F' ? (celsius * 9) / 5 + 32 : celsius;
}

static void draw_sun(int32_t cx, int32_t cy, int32_t radius)
{
    fill_disc(cx, cy, radius, COL_SAND);
    for(int32_t i = 0; i < 8; i++) {
        static const int8_t dirs[8][2] = {
            {1, 0}, {1, 1}, {0, 1}, {-1, 1}, {-1, 0}, {-1, -1}, {0, -1}, {1, -1}
        };
        int32_t x1 = cx + dirs[i][0] * (radius + 4);
        int32_t y1 = cy + dirs[i][1] * (radius + 4);
        int32_t x2 = cx + dirs[i][0] * (radius + 10);
        int32_t y2 = cy + dirs[i][1] * (radius + 10);
        draw_line(x1, y1, x2, y2, COL_SAND, 2);
    }
}

static void draw_moon(int32_t cx, int32_t cy, int32_t radius)
{
    for(int32_t dy = -radius; dy <= radius; dy += 3) {
        for(int32_t dx = -radius; dx <= radius; dx += 3) {
            int32_t r2 = dx * dx + dy * dy;
            if(r2 > radius * radius) continue;
            int32_t bx = dx - radius / 2;
            int32_t by = dy - radius / 6;
            if(bx * bx + by * by < (radius * 4 / 5) * (radius * 4 / 5)) continue;
            fill_rect(cx + dx, cy + dy, 3, 3, COL_PAPER);
        }
    }
}

static void draw_cloud(int32_t cx, int32_t cy)
{
    fill_rect(cx - 27, cy + 2, 55, 15, COL_CLOUD);
    fill_rect(cx - 17, cy - 8, 20, 22, COL_CLOUD);
    fill_rect(cx - 2, cy - 15, 24, 27, COL_CLOUD);
    fill_rect(cx + 15, cy - 4, 14, 20, COL_CLOUD);
    fill_rect(cx - 22, cy + 15, 46, 2, COL_RAIN);
}

static void draw_weather_art(int32_t cx, int32_t cy, int condition, bool night)
{
    if(condition == 0) {
        if(night) draw_moon(cx, cy, 27);
        else draw_sun(cx, cy, 24);
    }
    else if(condition == 1) {
        if(night) draw_moon(cx - 14, cy - 12, 18);
        else draw_sun(cx - 15, cy - 12, 16);
        draw_cloud(cx + 3, cy + 4);
    }
    else {
        draw_cloud(cx, cy - 4);
        for(int32_t i = 0; i < 5; i++) {
            int32_t x = cx - 19 + i * 9;
            int32_t y = cy + 24 + (i % 3) * 5;
            fill_rect(x, y, 2, 6, COL_RAIN);
        }
    }
}

static void draw_mini_weather(int32_t cx, int32_t cy, int condition, bool night)
{
    if(condition == 0) {
        if(night) draw_moon(cx, cy, 8);
        else fill_disc(cx, cy, 7, COL_SAND);
    }
    else if(condition == 1) {
        if(night) draw_moon(cx - 4, cy - 3, 6);
        else fill_disc(cx - 4, cy - 3, 5, COL_SAND);
        fill_rect(cx - 5, cy + 2, 20, 6, COL_CLOUD);
        fill_rect(cx, cy - 2, 10, 9, COL_CLOUD);
    }
    else {
        fill_rect(cx - 9, cy - 3, 20, 7, COL_CLOUD);
        fill_rect(cx - 2, cy - 7, 10, 10, COL_CLOUD);
        fill_rect(cx - 5, cy + 7, 2, 4, COL_RAIN);
        fill_rect(cx + 2, cy + 9, 2, 4, COL_RAIN);
    }
}

static void draw_weather(void)
{
    int temp_c, high_c, low_c, humidity, wind, condition;
    bool night;
    weather_values(&temp_c, &high_c, &low_c, &humidity, &wind, &night, &condition);
    char text[32];

    draw_app_header("WEATHER", "LOCAL SKY / OFFLINE SAMPLE");
    draw_weather_art(80, 137, condition, night);

    snprintf(text, sizeof(text), "%d~", weather_temp(temp_c));
    draw_text(text, 164, 92, 7, COL_PAPER, 0);
    fill_rect(314, 96, 44, 24, COL_INK2);
    stroke_rect(314, 96, 44, 24, COL_SKY, 1);
    snprintf(text, sizeof(text), "~%c", s.weather_unit);
    draw_text(text, 336, 102, 2, COL_SKY, 1);

    static const char *conditions[] = {"CLEAR", "CLOUD", "RAIN"};
    draw_text(conditions[condition], 164, 154, 2, COL_SKY, 0);
    snprintf(text, sizeof(text), "H %d~  L %d~", weather_temp(high_c), weather_temp(low_c));
    draw_text(text, 164, 178, 1, COL_MUTED, 0);

    hline(22, 212, 346, COL_LINE);
    for(int32_t i = 0; i < 5; i++) {
        int32_t cx = 54 + i * 70;
        int32_t hour_temp = temp_c + ((i == 0) ? 0 : (i == 4 ? -1 : 1));
        char label[6];
        if(i == 0) snprintf(label, sizeof(label), "NOW");
        else snprintf(label, sizeof(label), "+%dH", (int)i);
        draw_text(label, cx, 224, 1, COL_DIM, 1);
        draw_mini_weather(cx, 250, condition, night);
        snprintf(text, sizeof(text), "%d~", weather_temp(hour_temp));
        draw_text(text, cx, 282, 2, COL_PAPER, 1);
        if(i < 4) vline(89 + i * 70, 232, 58, COL_LINE);
    }

    fill_rect(22, 310, 167, 50, COL_INK2);
    stroke_rect(22, 310, 167, 50, COL_LINE, 1);
    draw_text("HUMIDITY", 32, 319, 1, COL_DIM, 0);
    snprintf(text, sizeof(text), "%d%%", humidity);
    draw_text(text, 32, 334, 2, COL_PAPER, 0);

    fill_rect(201, 310, 167, 50, COL_INK2);
    stroke_rect(201, 310, 167, 50, COL_LINE, 1);
    draw_text("WIND", 211, 319, 1, COL_DIM, 0);
    snprintf(text, sizeof(text), "%d KMH", wind);
    draw_text(text, 211, 334, 2, COL_PAPER, 0);

    draw_text("SWIPE PAGES / TAP TEMP UNIT", 195, 394, 1, COL_DIM, 1);
}

static void draw_switch(int32_t x, int32_t y, bool on)
{
    fill_rect(x, y, 50, 22, on ? COL_INK2 : COL_INK);
    stroke_rect(x, y, 50, 22, on ? COL_SAND : COL_LINE2, 2);
    if(on) fill_rect(x + 34, y + 4, 12, 14, COL_SAND);
    else fill_rect(x + 4, y + 4, 12, 14, COL_DIM);
}

static void settings_row_rect(uint8_t index, int32_t *x, int32_t *y, int32_t *w, int32_t *h)
{
    *x = 22;
    *y = 80 + index * 58;
    *w = 346;
    *h = 54;
}

static void draw_settings(void)
{
    static const char *titles[] = {"AUTO DRIFT", "24H CLOCK", "DIM STANDBY", "SENSOR ZERO"};
    static const char *subs[] = {"IDLE MOTION", "TIME FORMAT", "AFTER 42S", "TOUCH TO CALIBRATE"};
    draw_app_header("SETTINGS", "SYSTEM / 04 OPTIONS");

    for(uint8_t i = 0; i < 4; i++) {
        int32_t x, y, w, h;
        settings_row_rect(i, &x, &y, &w, &h);
        bool selected = i == s.settings_index;
        if(selected) {
            fill_rect(x, y, w, h, COL_INK2);
            fill_rect(x - 6, y + 10, 3, h - 20, COL_SAND);
        }
        draw_text(titles[i], x + 2, y + 10, 2, COL_PAPER, 0);
        draw_text(subs[i], x + 2, y + 30, 1, COL_DIM, 0);
        if(i < 3) {
            bool on = i == 0 ? s.auto_drift : (i == 1 ? s.h24 : s.dim_on);
            draw_switch(x + 292, y + 16, on);
            draw_text(on ? "ON" : "OFF", x + 284, y + 21, 1, on ? COL_SAND : COL_DIM, 2);
        }
        else {
            draw_text(s.sensor_live ? "6-AXIS" : "SIM", x + w - 2, y + 21, 1,
                      s.sensor_live ? COL_MINT : COL_MUTED, 2);
        }
        hline(x, y + h - 2, w, COL_LINE);
    }

    hline(22, 316, 346, COL_LINE);
    const char *sensor = s.sensor_live ? "6-AXIS LIVE" : "SIMULATED";
    static const char *labels[] = {"SENSOR", "PANEL", "KEYS", "IMU", "OS"};
    static const char *values[] = {NULL, "390 X 450", "KEY1 / KEY2", "LSM6DS3TR-C", "SIFT 0.6"};
    for(uint8_t i = 0; i < 5; i++) {
        int32_t y = 328 + i * 14;
        draw_text(labels[i], 22, y, 1, COL_DIM, 0);
        draw_text(i == 0 ? sensor : values[i], 368, y, 1, i == 0 && s.sensor_live ? COL_MINT : COL_MUTED, 2);
    }
    draw_text("SWIPE PAGES / TAP ROW / BACK", 195, 414, 1, COL_DIM, 1);
}

static void draw_timer_alert(void)
{
    uint32_t now = lv_tick_get();
    if(s.view == VIEW_TIMER || now >= s.timer_alert_until) return;
    fill_rect(22, 404, 346, 28, COL_INK);
    stroke_rect(22, 404, 346, 28, COL_SAND, 2);
    draw_text("TIMER DONE / TAP TO OPEN", 195, 414, 1, COL_SAND, 1);
}

static void draw_dimmed(uint32_t now)
{
    int32_t percent = dim_percent(now);
    if(percent <= 0) return;
    for(int32_t i = 0; i < SIFT_W * SIFT_H; i++) s_fb[i] = dim_color(s_fb[i], percent);
    if(percent < 25) return;
    fill_rect(124, 210, 142, 30, COL_INK);
    stroke_rect(124, 210, 142, 30, COL_MINT_DIM, 1);
    if((now % 1400U) < 900U) draw_text("TAP TO WAKE", 195, 219, 2, COL_MINT, 1);
}

static void draw_panel_mask(void)
{
    const int32_t r = SIFT_PANEL_RADIUS;
    for(int32_t y = 0; y < r; y++) {
        for(int32_t x = 0; x < r; x++) {
            int32_t dx = r - x;
            int32_t dy = r - y;
            if(dx * dx + dy * dy <= r * r) continue;
            put_px(x, y, COL_INK);
            put_px(SIFT_W - 1 - x, y, COL_INK);
            put_px(x, SIFT_H - 1 - y, COL_INK);
            put_px(SIFT_W - 1 - x, SIFT_H - 1 - y, COL_INK);
        }
    }
}

static void sift_render(void)
{
    clock_update();
    draw_background();
    switch(s.view) {
    case VIEW_APPS:
        draw_app_drawer();
        break;
    case VIEW_TIMER:
        draw_timer();
        break;
    case VIEW_STOPWATCH:
        draw_stopwatch();
        break;
    case VIEW_WEATHER:
        draw_weather();
        break;
    case VIEW_SETTINGS:
        draw_settings();
        break;
    case VIEW_WATCH:
    default:
        draw_watch();
        break;
    }
    draw_panel_mask();
    if(s.view == VIEW_WATCH) draw_dimmed(lv_tick_get());
    draw_timer_alert();
    if(s_canvas != NULL) lv_obj_invalidate(s_canvas);
}

static bool point_in_rect(int32_t x, int32_t y, int32_t rx, int32_t ry, int32_t rw, int32_t rh)
{
    return x >= rx && x < rx + rw && y >= ry && y < ry + rh;
}

static void open_view(sift_view_t view)
{
    s.view = view;
    s.settings_index = 0;
    s.manual_until = 0;
    s.last_input = lv_tick_get();
    s.dimmed = false;
    vibe_pulse();
    printf("[sift_watch] view=%d\n", (int)view);
}

static void go_back(void)
{
    open_view(s.view == VIEW_APPS ? VIEW_WATCH : VIEW_APPS);
}

static void sift_page_step(int32_t direction)
{
    int32_t next = ((int32_t)s.view + direction + 6) % 6;
    open_view((sift_view_t)next);
}

static void sift_handle_swipe(int32_t dx, int32_t dy)
{
    int32_t ax = dx < 0 ? -dx : dx;
    int32_t ay = dy < 0 ? -dy : dy;
    if(ax < SIFT_SWIPE_MIN && ay < SIFT_SWIPE_MIN) return;

    if(ax >= ay) {
        /* Left swipe advances in the ring; right swipe goes back. */
        sift_page_step(dx < 0 ? 1 : -1);
    }
    else if(dy < 0) {
        open_view(VIEW_APPS);
    }
    else {
        open_view(VIEW_WATCH);
    }
    printf("[sift_watch] swipe dx=%ld dy=%ld view=%d\n",
           (long)dx, (long)dy, (int)s.view);
}

static void sift_handle_tap(int x, int y)
{
    uint32_t now = lv_tick_get();
    if(s.dimmed) {
        s.dimmed = false;
        s.last_input = now;
        return;
    }
    s.last_input = now;
    if(s.view != VIEW_TIMER && lv_tick_get() < s.timer_alert_until && point_in_rect(x, y, 22, 404, 346, 28)) {
        open_view(VIEW_TIMER);
        return;
    }

    if(s.view == VIEW_WATCH) {
        if(point_in_rect(x, y, 96, 8, 58, 32)) {
            open_view(VIEW_APPS);
        }
        return;
    }

    if(point_in_rect(x, y, 14, 12, 38, 42)) {
        go_back();
        return;
    }

    if(s.view == VIEW_APPS) {
        for(uint8_t i = 0; i < 4; i++) {
            int32_t rx, ry, rw, rh;
            app_tile_rect(i, &rx, &ry, &rw, &rh);
            if(point_in_rect(x, y, rx, ry, rw, rh)) {
                s.app_index = i;
                open_view((sift_view_t)(VIEW_TIMER + i));
                return;
            }
        }
        return;
    }

    if(s.view == VIEW_TIMER) {
        for(uint8_t i = 0; i < 4; i++) {
            if(point_in_rect(x, y, 22 + i * 89, 214, 79, 30)) {
                timer_select(i);
                return;
            }
        }
        if(point_in_rect(x, y, 72, 302, 150, 42)) timer_toggle(now);
        else if(point_in_rect(x, y, 234, 302, 84, 42)) timer_reset();
        return;
    }

    if(s.view == VIEW_STOPWATCH) {
        if(point_in_rect(x, y, 22, 318, 107, 38)) sw_toggle(now);
        else if(point_in_rect(x, y, 141, 318, 107, 38)) sw_lap(now);
        else if(point_in_rect(x, y, 260, 318, 108, 38)) sw_reset();
        return;
    }

    if(s.view == VIEW_WEATHER) {
        if(point_in_rect(x, y, 151, 84, 217, 106)) {
            s.weather_unit = s.weather_unit == 'C' ? 'F' : 'C';
            s.last_input = now;
        }
        return;
    }

    if(s.view == VIEW_SETTINGS) {
        for(uint8_t i = 0; i < 4; i++) {
            int32_t rx, ry, rw, rh;
            settings_row_rect(i, &rx, &ry, &rw, &rh);
            if(!point_in_rect(x, y, rx, ry, rw, rh)) continue;
            s.settings_index = i;
            if(i == 0) s.auto_drift = !s.auto_drift;
            else if(i == 1) s.h24 = !s.h24;
            else if(i == 2) s.dim_on = !s.dim_on;
            else {
                sift_imu_zero();
                s.manual_until = 0;
            }
            s.last_input = now;
            return;
        }
    }
}

static void sift_handle_key(uint32_t key)
{
    uint32_t now = lv_tick_get();
    if(s.dimmed) {
        s.dimmed = false;
        s.last_input = now;
        return;
    }

    if(s.view == VIEW_WATCH) {
        if(key == LV_KEY_ENTER || key == LV_KEY_NEXT || key == LV_KEY_RIGHT) {
            open_view(VIEW_APPS);
        }
        else if(key == LV_KEY_LEFT) s.target_roll = clamp_i32(s.target_roll - 6, -45, 45);
        else if(key == LV_KEY_UP) s.target_pitch = clamp_i32(s.target_pitch - 5, -32, 32);
        else if(key == LV_KEY_DOWN) s.target_pitch = clamp_i32(s.target_pitch + 5, -32, 32);
        s.manual_until = now + 800U;
        s.last_input = now;
        return;
    }

    if(key == LV_KEY_ESC || key == LV_KEY_HOME) {
        go_back();
        return;
    }

    if(s.view == VIEW_APPS) {
        if(key == LV_KEY_RIGHT) s.app_index = (uint8_t)((s.app_index + 1) & 3U);
        else if(key == LV_KEY_LEFT) s.app_index = (uint8_t)((s.app_index + 3) & 3U);
        else if(key == LV_KEY_DOWN) s.app_index = (uint8_t)((s.app_index + 2) & 3U);
        else if(key == LV_KEY_UP) s.app_index = (uint8_t)((s.app_index + 2) & 3U);
        else if(key == LV_KEY_ENTER) open_view((sift_view_t)(VIEW_TIMER + s.app_index));
        s.last_input = now;
        return;
    }

    if(s.view == VIEW_TIMER) {
        if(key == LV_KEY_ENTER) timer_toggle(now);
        else if(key == LV_KEY_LEFT) timer_select((uint8_t)((s.timer_selected + 3) & 3U));
        else if(key == LV_KEY_RIGHT) timer_select((uint8_t)((s.timer_selected + 1) & 3U));
        s.last_input = now;
        return;
    }

    if(s.view == VIEW_STOPWATCH) {
        if(key == LV_KEY_ENTER) sw_toggle(now);
        else if(key == LV_KEY_NEXT) sw_lap(now);
        else if(key == LV_KEY_LEFT) sw_reset();
        s.last_input = now;
        return;
    }

    if(s.view == VIEW_WEATHER) {
        if(key == LV_KEY_ENTER) s.weather_unit = s.weather_unit == 'C' ? 'F' : 'C';
        s.last_input = now;
        return;
    }

    if(s.view == VIEW_SETTINGS) {
        if(key == LV_KEY_DOWN) s.settings_index = (uint8_t)((s.settings_index + 1) & 3U);
        else if(key == LV_KEY_UP) s.settings_index = (uint8_t)((s.settings_index + 3) & 3U);
        else if(key == LV_KEY_ENTER) {
            uint8_t i = s.settings_index;
            if(i == 0) s.auto_drift = !s.auto_drift;
            else if(i == 1) s.h24 = !s.h24;
            else if(i == 2) s.dim_on = !s.dim_on;
            else {
                sift_imu_zero();
            }
        }
        s.last_input = now;
    }
}

static bool event_point(lv_event_t *event, int32_t *x, int32_t *y)
{
    (void)event;
    lv_indev_t *indev = lv_indev_active();
    if(indev == NULL) return false;
    lv_point_t point;
    lv_indev_get_point(indev, &point);
    lv_area_t area;
    lv_obj_get_coords(s_canvas, &area);
    *x = point.x - area.x1;
    *y = point.y - area.y1;
    return *x >= 0 && *x < SIFT_W && *y >= 0 && *y < SIFT_H;
}

static void sift_canvas_event_cb(lv_event_t *event)
{
    lv_event_code_t code = lv_event_get_code(event);
    if(code == LV_EVENT_KEY) {
        sift_handle_key(lv_event_get_key(event));
        return;
    }

    if(code == LV_EVENT_PRESSED) {
        int32_t x, y;
        if(!event_point(event, &x, &y)) return;
        uint32_t now = lv_tick_get();
        s.last_input = now;
        s.touch_active = true;
        s.touch_moved = false;
        s.touch_swiping = false;
        s.touch_suppress = s.dimmed;
        if(s.dimmed) {
            s.dimmed = false;
            return;
        }
        s.touch_start_x = x;
        s.touch_start_y = y;
        s.touch_start_roll = s.target_roll;
        s.touch_start_pitch = s.target_pitch;
        s.touch_at = now;
        return;
    }

    if(code == LV_EVENT_PRESSING) {
        if(!s.touch_active) return;
        int32_t x, y;
        if(!event_point(event, &x, &y)) return;
        int32_t dx = x - s.touch_start_x;
        int32_t dy = y - s.touch_start_y;
        int32_t ax = dx < 0 ? -dx : dx;
        int32_t ay = dy < 0 ? -dy : dy;
        int32_t maxd = ax > ay ? ax : ay;
        uint32_t elapsed = lv_tick_get() - s.touch_at;
        if(dx * dx + dy * dy > 36) s.touch_moved = true;
        if(!s.touch_swiping && maxd >= SIFT_SWIPE_MIN &&
           (maxd >= SIFT_SWIPE_LONG || elapsed <= 280U)) {
            s.touch_swiping = true;
            s.target_roll = s.touch_start_roll;
            s.target_pitch = s.touch_start_pitch;
            s.manual_until = 0;
        }
        if(!s.touch_suppress && s.view == VIEW_WATCH && !s.touch_swiping) {
            s.target_roll = clamp_i32(s.touch_start_roll + dx * 150 / SIFT_W, -45, 45);
            s.target_pitch = clamp_i32(s.touch_start_pitch + dy * 105 / SIFT_H, -32, 32);
            s.manual_until = lv_tick_get() + 1800U;
            s.last_input = lv_tick_get();
        }
        return;
    }

    if(code == LV_EVENT_RELEASED) {
        if(!s.touch_active) return;
        int32_t x, y;
        bool has_point = event_point(event, &x, &y);
        int32_t dx = has_point ? x - s.touch_start_x : 0;
        int32_t dy = has_point ? y - s.touch_start_y : 0;
        bool suppress = s.touch_suppress;
        bool moved = s.touch_moved;
        bool swiping = s.touch_swiping;
        s.touch_active = false;
        s.touch_moved = false;
        s.touch_swiping = false;
        s.touch_suppress = false;
        s.last_input = lv_tick_get();
        if(suppress) return;

        int32_t ax = dx < 0 ? -dx : dx;
        int32_t ay = dy < 0 ? -dy : dy;
        int32_t maxd = ax > ay ? ax : ay;
        uint32_t elapsed = lv_tick_get() - s.touch_at;
        bool swipe = swiping || (has_point && !suppress &&
                     (maxd >= SIFT_SWIPE_LONG ||
                      (maxd >= SIFT_SWIPE_MIN &&
                       (s.view != VIEW_WATCH || elapsed <= 280U))));
        if(swipe) {
            sift_handle_swipe(dx, dy);
            return;
        }
        if(!moved && has_point) sift_handle_tap(x, y);
        else if(s.view == VIEW_WATCH && moved) s.manual_until = lv_tick_get() + 650U;
        return;
    }

    if(code == LV_EVENT_PRESS_LOST) {
        s.touch_active = false;
        s.touch_moved = false;
        s.touch_swiping = false;
        s.touch_suppress = false;
    }
}

#if SIFT_HAS_IMU
static rt_device_t s_imu_acce;
static bool s_imu_tried;
static bool s_imu_have_base;
static int32_t s_imu_base_x;
static int32_t s_imu_base_y;
static bool s_imu_filter_ready;
static int32_t s_imu_fx;
static int32_t s_imu_fy;
static int32_t s_imu_fz;
static uint32_t s_imu_log_at;
static bool s_imu_flip_armed;
static bool s_imu_face_down;
static uint32_t s_imu_face_down_at;
static uint32_t s_imu_last_flip_at;

static void imu_init(void)
{
    if(s_imu_tried) return;
    s_imu_tried = true;

    s_imu_acce = rt_device_find("acce_sift");
    if(s_imu_acce == NULL) {
        HAL_PIN_Set(PAD_PA40, I2C3_SCL, PIN_PULLUP, 1);
        HAL_PIN_Set(PAD_PA39, I2C3_SDA, PIN_PULLUP, 1);
        struct rt_sensor_config cfg;
        memset(&cfg, 0, sizeof(cfg));
        cfg.intf.dev_name = "i2c3";
        cfg.intf.user_data = (void *)LSM6DSL_ADDR_DEFAULT;
        cfg.irq_pin.pin = RT_PIN_NONE;
        if(rt_hw_lsm6dsl_init("sift", &cfg) != RT_EOK) {
            printf("[sift_watch] imu init failed\n");
            return;
        }
        s_imu_acce = rt_device_find("acce_sift");
    }
    if(s_imu_acce == NULL) {
        printf("[sift_watch] imu not found\n");
        return;
    }
    if(rt_device_open(s_imu_acce, RT_DEVICE_FLAG_RDONLY) != RT_EOK) {
        printf("[sift_watch] imu open failed\n");
        s_imu_acce = NULL;
        return;
    }
    rt_device_control(s_imu_acce, RT_SENSOR_CTRL_SET_ODR, (void *)(rt_uint32_t)104);
    printf("[sift_watch] imu ready\n");
}

static void sift_imu_zero(void)
{
    s_imu_have_base = false;
    s_imu_filter_ready = false;
    s_imu_flip_armed = false;
    s_imu_face_down = false;
    s_imu_face_down_at = 0;
    s.sensor_roll = 0;
    s.sensor_pitch = 0;
    printf("[sift_watch] imu zero requested\n");
}

static void imu_update(void)
{
    if(s_imu_acce == NULL) return;
    struct rt_sensor_data data;
    if(rt_device_read(s_imu_acce, 0, &data, 1) != 1) {
        s.sensor_live = false;
        return;
    }
    int32_t ax = data.data.acce.x;
    int32_t ay = data.data.acce.y;
    int32_t az = data.data.acce.z;

    /* Light first-order EMA (alpha = 3/4): one sample of lag at the 25 Hz
     * render cadence keeps the tilt responsive while trimming spikes. */
    if(!s_imu_filter_ready) {
        s_imu_fx = ax;
        s_imu_fy = ay;
        s_imu_fz = az;
        s_imu_filter_ready = true;
    }
    else {
        s_imu_fx = (s_imu_fx + ax * 3) / 4;
        s_imu_fy = (s_imu_fy + ay * 3) / 4;
        s_imu_fz = (s_imu_fz + az * 3) / 4;
    }
    int32_t fx = s_imu_fx;
    int32_t fy = s_imu_fy;
    int32_t fz = s_imu_fz;

    if(!s_imu_have_base) {
        s_imu_base_x = fx;
        s_imu_base_y = fy;
        s_imu_have_base = true;
        s_imu_flip_armed = false;
        s_imu_face_down = false;
        return;
    }
    int32_t dx = fx - s_imu_base_x;
    int32_t dy = fy - s_imu_base_y;
    /* ~60 degrees per g: 1000 mg reads 60 degrees, so 30 degrees reads ~30. */
    s.sensor_roll = clamp_i32(dx * 60 / 1000, -45, 45);
    s.sensor_pitch = clamp_i32(dy * 60 / 1000, -32, 32);
    s.sensor_live = true;

    uint32_t now = lv_tick_get();
    if(now - s_imu_log_at >= 500U) {
        s_imu_log_at = now;
        printf("[sift_watch] imu raw=%ld,%ld,%ld f=%ld,%ld,%ld roll=%ld pitch=%ld live=%d\n",
               (long)ax, (long)ay, (long)az,
               (long)fx, (long)fy, (long)fz,
               (long)s.sensor_roll, (long)s.sensor_pitch,
               s.sensor_live ? 1 : 0);
    }

    if(fz >= SIFT_IMU_FACE_DOWN_MG) {
        if(!s_imu_face_down) {
            s_imu_face_down = true;
            s_imu_face_down_at = now;
            printf("[sift_watch] imu face down az=%ld\n", (long)fz);
        }
        if(s_imu_flip_armed && now - s_imu_face_down_at >= 160U &&
           now - s_imu_last_flip_at >= SIFT_IMU_FLIP_COOLDOWN_MS) {
            s_imu_flip_armed = false;
            s_imu_last_flip_at = now;
            sift_flip();
        }
    }
    else if(fz <= SIFT_IMU_FACE_UP_MG) {
        if(s_imu_face_down) {
            s_imu_face_down = false;
            printf("[sift_watch] imu face up az=%ld\n", (long)fz);
        }
        if(!s_imu_flip_armed && now - s_imu_last_flip_at >= SIFT_IMU_FLIP_COOLDOWN_MS) {
            s_imu_flip_armed = true;
        }
    }
}
#else
static void imu_init(void) {}
static void imu_update(void) { s.sensor_live = false; }
static void sift_imu_zero(void)
{
    s.sensor_roll = 0;
    s.sensor_pitch = 0;
    s.sensor_live = false;
}
#endif

#if SIFT_HAS_KEY
static bool s_key1_raw;
static bool s_key1_down;
static uint32_t s_key1_raw_at;
static bool s_key2_raw;
static bool s_key2_down;
static uint32_t s_key2_raw_at;
static bool s_vibe_ready;
static bool s_vibe_on;
static uint32_t s_vibe_off_at;

static void key_init(void)
{
    rt_pin_mode(SIFT_KEY1_PIN, PIN_MODE_INPUT_PULLDOWN);
    rt_pin_mode(SIFT_KEY2_PIN, PIN_MODE_INPUT_PULLDOWN);
    s_key1_raw = rt_pin_read(SIFT_KEY1_PIN) != 0;
    s_key1_down = s_key1_raw;
    s_key2_raw = rt_pin_read(SIFT_KEY2_PIN) != 0;
    s_key2_down = s_key2_raw;
    s_key1_raw_at = 0;
    s_key2_raw_at = 0;
    printf("[sift_watch] keys ready key1=%d key2=%d levels=%d,%d\n",
           (int)SIFT_KEY1_PIN, (int)SIFT_KEY2_PIN,
           s_key1_down ? 1 : 0, s_key2_down ? 1 : 0);
}

static bool key_pressed_edge(int pin, bool *raw, bool *down, uint32_t *raw_at, uint32_t now)
{
    bool level = rt_pin_read(pin) != 0; /* KEY1/KEY2 are active high. */
    if(level != *raw) {
        *raw = level;
        *raw_at = now;
    }
    if(level != *down && now - *raw_at >= 20U) {
        *down = level;
        return level;
    }
    return false;
}

static void key_poll(void)
{
    uint32_t now = lv_tick_get();
    if(key_pressed_edge(SIFT_KEY1_PIN, &s_key1_raw, &s_key1_down, &s_key1_raw_at, now)) {
        printf("[sift_watch] key1 press\n");
        vibe_pulse();
        sift_handle_key(LV_KEY_HOME);
        snprintf(s.notice, sizeof(s.notice), "KEY1");
        s.notice_until = lv_tick_get() + 600U;
    }
    if(key_pressed_edge(SIFT_KEY2_PIN, &s_key2_raw, &s_key2_down, &s_key2_raw_at, now)) {
        printf("[sift_watch] key2 press\n");
        vibe_pulse();
        sift_handle_key(LV_KEY_ENTER);
        snprintf(s.notice, sizeof(s.notice), "KEY2");
        s.notice_until = lv_tick_get() + 600U;
    }
}

static void vibe_init(void)
{
    rt_pin_mode(SIFT_VIBE_PIN, PIN_MODE_OUTPUT);
    rt_pin_write(SIFT_VIBE_PIN, PIN_LOW);
    s_vibe_ready = true;
    s_vibe_on = false;
    s_vibe_off_at = 0;
    printf("[sift_watch] vibe ready pin=%d\n", (int)SIFT_VIBE_PIN);
}

static void vibe_pulse(void)
{
    if(!s_vibe_ready) return;
    rt_pin_write(SIFT_VIBE_PIN, PIN_HIGH);
    s_vibe_on = true;
    s_vibe_off_at = lv_tick_get() + 25U;
}

static void vibe_update(uint32_t now)
{
    if(!s_vibe_on) return;
    if((int32_t)(now - s_vibe_off_at) >= 0) {
        rt_pin_write(SIFT_VIBE_PIN, PIN_LOW);
        s_vibe_on = false;
    }
}
#else
static void key_init(void) {}
static void key_poll(void) {}
static void vibe_init(void) {}
static void vibe_pulse(void) {}
static void vibe_update(uint32_t now) { (void)now; }
#endif

static void sift_tick_cb(lv_timer_t *timer)
{
    (void)timer;
    uint32_t now = lv_tick_get();
    uint32_t elapsed = now - s.last_tick;
    if(elapsed > 100U) elapsed = 100U;
    s.last_tick = now;

    timer_update(now);
    imu_update();
    key_poll();
    vibe_update(now);
    update_tilt(now);

    s.sim_accum += elapsed;
    uint8_t guard = 0;
    while(s.sim_accum >= SIFT_SIM_STEP_MS && guard++ < 4) {
        sand_step();
        s.sim_accum -= SIFT_SIM_STEP_MS;
    }

    if(s.stats.total > 0) {
        uint32_t top_percent = (uint32_t)s.stats.top * 100U / s.stats.total;
        if(top_percent < 5U) {
            if(s.empty_since == 0U) s.empty_since = now;
            /* A finished hourglass stays finished; only a six-axis flip
             * or a fresh app start moves the sand again. */
            s.stats.flow = 0;
        }
        else s.empty_since = 0;
    }

    update_idle(now);
    sift_render();
}

static void sift_create_group(void)
{
    s_group = lv_group_create();
    lv_group_add_obj(s_group, s_canvas);
    lv_group_focus_obj(s_canvas);

    lv_indev_t *indev = NULL;
    while((indev = lv_indev_get_next(indev)) != NULL) {
        lv_indev_type_t type = lv_indev_get_type(indev);
        if(type == LV_INDEV_TYPE_KEYPAD || type == LV_INDEV_TYPE_ENCODER) {
            lv_indev_set_group(indev, s_group);
        }
    }
}

void sift_watch_create(void)
{
    lv_obj_t *screen = lv_screen_active();
    lv_display_t *display = lv_display_get_default();
    int32_t screen_w = display != NULL ? lv_display_get_horizontal_resolution(display) : SIFT_W;
    int32_t screen_h = display != NULL ? lv_display_get_vertical_resolution(display) : SIFT_H;

    app_set_name("sift_watch");
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x040B08), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);

    memset(&s, 0, sizeof(s));
    s.view = VIEW_WATCH;
    s.auto_drift = true;
    s.h24 = true;
    s.dim_on = true;
    s.weather_unit = 'C';
    s.timer_selected = 2;
    s.timer_duration = 300000U;
    s.timer_remaining = 300000U;
    s.last_tick = lv_tick_get();
    s.last_input = s.last_tick;

    time_t now_time = time(NULL);
    if(now_time > (time_t)1600000000) s.clock_epoch = (uint32_t)now_time;
    else s.clock_epoch = 1767225600U; /* deterministic fallback: 2026-01-01 */
    s.clock_base_tick = lv_tick_get();

    /* Build the hourglass interior mask. */
    memset(s_inside, 0, sizeof(s_inside));
    for(int32_t y = 0; y < SIFT_ROWS; y++) {
        int32_t half = hg_half_width(y < 40 ? y : 79 - y);
        for(int32_t x = 0; x < SIFT_COLS; x++) {
            int32_t center = x * SIFT_CELL + 1;
            if(center >= 90 - half && center <= 90 + half) s_inside[y * SIFT_COLS + x] = 1;
        }
    }
    sand_init();

#if defined(SIFT_HAS_APP_CANVAS_ALLOC)
    s_fb = (uint16_t *)app_canvas_mem_alloc((size_t)SIFT_W * SIFT_H * sizeof(uint16_t));
#else
    s_fb = (uint16_t *)lv_malloc((size_t)SIFT_W * SIFT_H * sizeof(uint16_t));
#endif
    if(s_fb == NULL) {
        lv_obj_t *error = lv_label_create(screen);
        lv_label_set_text(error, "SIFT framebuffer allocation failed");
        lv_obj_center(error);
        printf("[sift_watch] framebuffer allocation failed\n");
        return;
    }
    memset(s_fb, 0, (size_t)SIFT_W * SIFT_H * sizeof(uint16_t));

    s_canvas = lv_canvas_create(screen);
    if(s_canvas == NULL) {
#if defined(SIFT_HAS_APP_CANVAS_ALLOC)
        app_canvas_mem_free(s_fb);
#else
        lv_free(s_fb);
#endif
        s_fb = NULL;
        printf("[sift_watch] canvas creation failed\n");
        return;
    }
    app_obj_set_name(s_canvas, "sift_canvas");
    lv_obj_set_size(s_canvas, SIFT_W, SIFT_H);
    lv_obj_set_pos(s_canvas, (screen_w - SIFT_W) / 2, (screen_h - SIFT_H) / 2);
    lv_obj_set_style_pad_all(s_canvas, 0, 0);
    lv_obj_set_style_border_width(s_canvas, 0, 0);
    lv_obj_set_style_bg_opa(s_canvas, LV_OPA_TRANSP, 0);
    lv_obj_set_style_radius(s_canvas, 0, 0);
    lv_obj_remove_flag(s_canvas, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(s_canvas, LV_OBJ_FLAG_CLICKABLE);
    lv_canvas_set_buffer(s_canvas, s_fb, SIFT_W, SIFT_H, LV_COLOR_FORMAT_RGB565);
    lv_obj_add_event_cb(s_canvas, sift_canvas_event_cb, LV_EVENT_ALL, NULL);
    sift_create_group();

    imu_init();
    key_init();
    vibe_init();
    sift_render();

    s_render_timer = lv_timer_create(sift_tick_cb, SIFT_RENDER_MS, NULL);
    if(s_render_timer == NULL) {
        printf("[sift_watch] render timer failed\n");
    }
    printf("[sift_watch] created display=%ldx%ld\n", (long)screen_w, (long)screen_h);
}

#endif /* LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4 */
