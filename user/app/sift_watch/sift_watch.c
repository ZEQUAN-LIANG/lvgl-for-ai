#include "sift_watch.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "app.h"
#include "game/zc_audio.h"
#include "game/zc_game.h"

#if defined(LVGL_VERIFY_LOOP_EZIP_ASSETS) && defined(RT_USING_FINSH)
#include "finsh.h"
#endif

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#if defined(LVGL_VERIFY_LOOP_EZIP_ASSETS) &&                                   \
    (defined(ACC_USING_LSM6DSL) || defined(CONFIG_ACC_USING_LSM6DSL))
#define SIFT_HAS_IMU 1
#include "rtthread.h"
#include "st_lsm6dsl_sensor_v1.h"
#include "bf0_hal.h"
#include "drv_io.h"
#else
#define SIFT_HAS_IMU 0
#endif

#define SIFT_CLOCK_MIN_VALID        1600000000U
#define SIFT_CLOCK_EPOCH_2026_01_01 1767225600U

/* Physical keys and the vibration motor only exist on the SiFli SDK build.
 * The exporter prepends lvgl_verify_loop_sdk.h, which defines
 * LVGL_VERIFY_LOOP_EZIP_ASSETS and pulls in rtthread.h; headless builds get
 * empty stubs. */
#if defined(LVGL_VERIFY_LOOP_EZIP_ASSETS)
#define SIFT_HAS_KEY 1
#include "rtdevice.h"
#if defined(BSP_KEY1_PIN)
#define SIFT_KEY1_PIN BSP_KEY1_PIN
#else
#define SIFT_KEY1_PIN 34
#endif
#if defined(BSP_KEY2_PIN)
#define SIFT_KEY2_PIN BSP_KEY2_PIN
#else
#define SIFT_KEY2_PIN 43
#endif
#define SIFT_VIBE_PIN 20
#else
#define SIFT_HAS_KEY 0
#endif

#if defined(__has_include)
#if __has_include("app_mem.h")
#include "app_mem.h"
#define SIFT_HAS_APP_CANVAS_ALLOC 1
#endif
#endif

#define SIFT_W                390
#define SIFT_H                450
#define SIFT_PANEL_RADIUS     44
#define SIFT_CELL             3
#define SIFT_COLS             60
#define SIFT_ROWS             80
#define SIFT_GRID_X0          105
#define SIFT_GRID_Y0          106
#define SIFT_NECK_ROW         40
#define SIFT_NECK_Y           226
#define SIFT_HG_TOP           106
#define SIFT_HG_BOTTOM        346
#define SIFT_SIM_STEP_MS      66U
#define SIFT_RENDER_MS        40U
#define SIFT_SWIPE_MIN        42
#define SIFT_SWIPE_LONG       90
#define SIFT_FLIP_MS          680U
#define SIFT_ORBIT_MIN_ELEV   (-0.05f)
#define SIFT_ORBIT_MAX_ELEV   0.85f
#define SIFT_P3_PITCH_SIGN    1
#define SIFT_P3_BASE_PITCH_PX 9
#define SIFT_P3_PARALLAX_PX   15
#define SIFT_VX               24
#define SIFT_VY               32
#define SIFT_VZ               24
#define SIFT_VNECK            16
#define SIFT_VCELL            7.5f
#define SIFT_HG_CX            195
#define SIFT_HG_CY            226
#define SIFT_FRAME_HALF_X     106
#define SIFT_FRAME_HALF_Z     90
#define SIFT_FRAME_POST_HALF  4
#define SIFT_FRAME_POST_TOP   120
#define SIFT_FRAME_CAP_HALF_X 108
#define SIFT_FRAME_CAP_HALF_Z 92
#define SIFT_FRAME_CAP_HALF_Y 7
#define SIFT_FRAME_CAP_Y      127
#define SIFT_PI               3.14159265f
/* This board's accelerometer z axis points into the screen: face-up is
 * negative, face-down is positive. */
#define SIFT_IMU_FACE_DOWN_MG     (550)
#define SIFT_IMU_FACE_UP_MG       (-250)
#define SIFT_IMU_FLIP_COOLDOWN_MS 1200U
#define SIFT_TIMER_ALERT_MS       6000U
#define SIFT_IDLE_DIM_MS          42000U

#define RGB565(r, g, b)                                                        \
    ((uint16_t)((((r) & 0xF8U) << 8) | (((g) & 0xFCU) << 3) | ((b) >> 3)))

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
static const uint16_t COL_SAND_SHADOW = RGB565(107, 63, 28);
static const uint16_t COL_WOOD = RGB565(157, 93, 47);
static const uint16_t COL_WOOD_DARK = RGB565(72, 40, 21);
static const uint16_t COL_WOOD_HI = RGB565(215, 150, 80);
static const uint16_t COL_CORAL = RGB565(255, 121, 89);
static const uint16_t COL_SKY = RGB565(143, 203, 214);
static const uint16_t COL_RAIN = RGB565(95, 144, 155);
static const uint16_t COL_CLOUD = RGB565(168, 186, 178);

static const char font_chars[] =
    " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:.-+%/?~";
static const uint8_t font_rows[][7] = {
    {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11},
    {0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E},
    {0x0F, 0x10, 0x10, 0x10, 0x10, 0x10, 0x0F},
    {0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E},
    {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F},
    {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10},
    {0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0E},
    {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11},
    {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x1F},
    {0x07, 0x02, 0x02, 0x02, 0x12, 0x12, 0x0C},
    {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11},
    {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F},
    {0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11},
    {0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11},
    {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E},
    {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10},
    {0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D},
    {0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11},
    {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E},
    {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04},
    {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E},
    {0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04},
    {0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11},
    {0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11},
    {0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04},
    {0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F},
    {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E},
    {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E},
    {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F},
    {0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E},
    {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02},
    {0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E},
    {0x0E, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x0E},
    {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08},
    {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E},
    {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x01, 0x0E},
    {0x00, 0x04, 0x04, 0x00, 0x04, 0x04, 0x00},
    {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C},
    {0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00},
    {0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00},
    {0x19, 0x1B, 0x04, 0x04, 0x08, 0x1B, 0x13},
    {0x01, 0x02, 0x02, 0x04, 0x08, 0x08, 0x10},
    {0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04},
    {0x0E, 0x0A, 0x0E, 0x00, 0x00, 0x00, 0x00},
};

static const uint8_t hg_half_widths[40] = {
    75, 75, 75, 74, 74, 74, 73, 73, 72, 71, 71, 70, 69, 68,
    66, 65, 64, 63, 61, 60, 58, 56, 55, 53, 51, 49, 47, 45,
    43, 40, 38, 35, 33, 30, 27, 25, 21, 18, 14, 10,
};

static const int16_t sw_ring_x[60] = {
    195, 205, 216, 226, 235, 244, 253, 261, 269, 275, 281, 285, 289, 292, 293,
    294, 293, 292, 289, 285, 281, 275, 269, 261, 253, 244, 235, 226, 216, 205,
    195, 185, 174, 164, 155, 145, 137, 129, 121, 115, 109, 105, 101, 98,  97,
    96,  97,  98,  101, 105, 109, 115, 121, 129, 137, 145, 155, 164, 174, 185,
};
static const int16_t sw_ring_y[60] = {
    89,  90,  91,  94,  98,  102, 108, 114, 122, 130, 138, 148, 157, 167, 178,
    188, 198, 209, 219, 228, 238, 246, 254, 262, 268, 274, 278, 282, 285, 286,
    287, 286, 285, 282, 278, 274, 268, 262, 254, 246, 238, 228, 219, 209, 198,
    188, 178, 167, 157, 148, 138, 130, 122, 114, 108, 102, 98,  94,  91,  90,
};

typedef enum {
    VIEW_WATCH = 0,
    VIEW_APPS,
    VIEW_TIMER,
    VIEW_STOPWATCH,
    VIEW_WEATHER,
    VIEW_SETTINGS,
    VIEW_ZOMBIE
} sift_view_t;

#define SIFT_PAGE_COUNT 6

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
    bool touch_orbit;
    int touch_start_x;
    int touch_start_y;
    int touch_start_roll;
    int touch_start_pitch;
    float touch_start_yaw;
    float touch_start_elev;
    uint32_t touch_at;
    float orbit_yaw;
    float orbit_yaw_target;
    float orbit_elev;
    float orbit_elev_target;
    float flip_angle;
    uint32_t flip_start;
    uint32_t last_flip_at;
    bool flip_active;
} sift_state_t;

static sift_state_t s;
static uint16_t * s_fb;
static lv_obj_t * s_canvas;
static lv_group_t * s_group;
static lv_timer_t * s_render_timer;
static uint8_t s_vox[SIFT_VX * SIFT_VY * SIFT_VZ];
static uint8_t s_vox_tmp[SIFT_VX * SIFT_VY * SIFT_VZ];
static uint8_t s_vox_inside[SIFT_VX * SIFT_VY * SIFT_VZ];
static uint16_t s_vox_top;
static uint16_t s_vox_bottom;
static uint16_t s_vox_total;
static uint16_t s_vox_flow;
static uint32_t s_vox_step;
#define SIFT_VBINS 16
#define SIFT_VCAP  512
static int16_t s_vpx[SIFT_VBINS * SIFT_VCAP];
static int16_t s_vpy[SIFT_VBINS * SIFT_VCAP];
static uint8_t s_vpc[SIFT_VBINS * SIFT_VCAP];
static uint16_t s_vbins[SIFT_VBINS];
static uint16_t s_vox_sprite[4][8][8];
static bool s_vox_sprites_ready;

static uint16_t * s_game_bg;
static bool s_game_ready;
static zc_save_t s_game_save = {0, 0, 1};
static bool s_game_save_loaded;

static void sift_render(void);
static void sift_game_enter(void);
static void vibe_pulse_ms(uint32_t ms);
static void sift_tick_cb(lv_timer_t * timer);
static void sift_canvas_event_cb(lv_event_t * event);
static void sift_handle_tap(int x, int y);
static void sift_handle_key(uint32_t key);
static void sift_handle_swipe(int32_t dx, int32_t dy);
static void sift_flip(void);
static void weather_values(int * temp_c, int * high_c, int * low_c,
                           int * humidity, int * wind, bool * night,
                           int * condition);
static int weather_temp(int celsius);
static void sift_imu_zero(void);
static void vibe_pulse(void);

static void game_sfx(zc_sfx_t id, void * user)
{
    (void)user;
    zc_audio_play(id);
}

static void game_haptic(zc_haptic_t kind, void * user)
{
    (void)user;
    if(kind == ZC_HAPTIC_TAP) vibe_pulse_ms(18);
    else if(kind == ZC_HAPTIC_HIT)
        vibe_pulse_ms(35);
    else if(kind == ZC_HAPTIC_BOSS)
        vibe_pulse_ms(70);
    else if(kind == ZC_HAPTIC_LEVEL)
        vibe_pulse_ms(25);
    else
        vibe_pulse_ms(90);
}

static bool game_load(zc_save_t * save, void * user)
{
    (void)user;
    if(!s_game_save_loaded) return false;
    *save = s_game_save;
    return true;
}

static void game_store(const zc_save_t * save, void * user)
{
    (void)user;
    s_game_save = *save;
    s_game_save_loaded = true;
}

static const zc_hooks_t s_game_hooks = {game_sfx,  game_haptic, NULL,
                                        game_load, game_store,  NULL};

static int32_t clamp_i32(int32_t value, int32_t low, int32_t high)
{
    if(value < low) return low;
    if(value > high) return high;
    return value;
}

static float clamp_f32(float value, float low, float high)
{
    if(value < low) return low;
    if(value > high) return high;
    return value;
}

static int32_t round_f32(float value)
{
    return (int32_t)(value >= 0.0f ? value + 0.5f : value - 0.5f);
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

static void fill_rect(int32_t x, int32_t y, int32_t w, int32_t h,
                      uint16_t color)
{
    int32_t x0 = x < 0 ? 0 : x;
    int32_t y0 = y < 0 ? 0 : y;
    int32_t x1 = x + w > SIFT_W ? SIFT_W : x + w;
    int32_t y1 = y + h > SIFT_H ? SIFT_H : y + h;
    for(int32_t yy = y0; yy < y1; yy++) {
        uint16_t * row = s_fb + yy * SIFT_W;
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

static void stroke_rect(int32_t x, int32_t y, int32_t w, int32_t h,
                        uint16_t color, int32_t thickness)
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

static void draw_line(int32_t x1, int32_t y1, int32_t x2, int32_t y2,
                      uint16_t color, int32_t size)
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

static const uint8_t * font_for(char ch)
{
    if(ch >= 'a' && ch <= 'z') ch = (char)(ch - 'a' + 'A');
    if(ch == ' ') return font_rows[0];
    const char * found = strchr(font_chars, ch);
    if(found == NULL || found == font_chars) return font_rows[0];
    size_t index = (size_t)(found - font_chars);
    if(index >= sizeof(font_rows) / sizeof(font_rows[0])) return font_rows[0];
    return font_rows[index];
}

static int32_t text_width(const char * text, int32_t scale)
{
    size_t len = strlen(text);
    if(len == 0) return 0;
    return (int32_t)(len * 6 * (size_t)scale - (size_t)scale);
}

static void draw_glyph(const uint8_t * glyph, int32_t x, int32_t y,
                       int32_t scale, uint16_t color)
{
    for(int32_t row = 0; row < 7; row++) {
        uint8_t bits = glyph[row];
        int32_t start = -1;
        for(int32_t col = 0; col <= 5; col++) {
            bool on = col < 5 && (bits & (1U << (4 - col))) != 0U;
            if(on && start < 0) start = col;
            if(!on && start >= 0) {
                fill_rect(x + start * scale, y + row * scale,
                          (col - start) * scale, scale, color);
                start = -1;
            }
        }
    }
}

static void draw_text(const char * text, int32_t x, int32_t y, int32_t scale,
                      uint16_t color, int align)
{
    int32_t width = text_width(text, scale);
    if(align == 1) x -= width / 2;
    else if(align == 2)
        x -= width;
    size_t len = strlen(text);
    for(size_t i = 0; i < len; i++) {
        const uint8_t * glyph = font_for(text[i]);
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

static const char * month_name(int month)
{
    static const char * names[] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                   "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};
    return (month >= 0 && month < 12) ? names[month] : "JAN";
}

static const char * day_name(int day)
{
    static const char * names[] = {"SUN", "MON", "TUE", "WED",
                                   "THU", "FRI", "SAT"};
    return (day >= 0 && day < 7) ? names[day] : "THU";
}

static void clock_update(void)
{
    uint32_t elapsed = (lv_tick_get() - s.clock_base_tick) / 1000U;
    uint32_t second = (s.clock_epoch + elapsed) & 0x3FFFFFFFU;
    if(second == s.clock_last_second && s.clock.valid) return;
    s.clock_last_second = second;

    time_t raw = (time_t)(s.clock_epoch + elapsed);
    struct tm * tm = localtime(&raw);
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

static const char * clock_ampm(void)
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
    printf("[sift_watch] timer start remaining=%u\n",
           (unsigned)s.timer_remaining);
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

static void vox_count(void)
{
    uint16_t top = 0;
    uint16_t bottom = 0;
    for(int32_t iy = 0; iy < SIFT_VY; iy++) {
        for(int32_t ix = 0; ix < SIFT_VX; ix++) {
            const uint8_t * row = &s_vox[(iy * SIFT_VX + ix) * SIFT_VZ];
            for(int32_t iz = 0; iz < SIFT_VZ; iz++) {
                if(row[iz] == 0) continue;
                if(iy < SIFT_VNECK) top++;
                else
                    bottom++;
            }
        }
    }
    s_vox_top = top;
    s_vox_bottom = bottom;
    if((uint16_t)(top + bottom) > s_vox_total)
        s_vox_total = (uint16_t)(top + bottom);
    s.stats.top = top;
    s.stats.bottom = bottom;
    s.stats.total = s_vox_total > 0 ? s_vox_total : 1;
    s.stats.flow = s_vox_flow;
}

static void vox_init(void)
{
    memset(s_vox_inside, 0, sizeof(s_vox_inside));
    for(int32_t iy = 0; iy < SIFT_VY; iy++) {
        int32_t row =
            (int32_t)((iy + 0.5f) * ((float)SIFT_ROWS / (float)SIFT_VY));
        row = clamp_i32(row, 0, SIFT_ROWS - 1);
        int32_t table_row = row < SIFT_NECK_ROW ? row : (SIFT_ROWS - 1 - row);
        float r = (float)hg_half_widths[table_row];
        for(int32_t ix = 0; ix < SIFT_VX; ix++) {
            float wx = (ix + 0.5f) * SIFT_VCELL - 90.0f;
            for(int32_t iz = 0; iz < SIFT_VZ; iz++) {
                float wz = (iz + 0.5f) * SIFT_VCELL - 90.0f;
                if(wx * wx + wz * wz <= r * r) {
                    s_vox_inside[(iy * SIFT_VX + ix) * SIFT_VZ + iz] = 1;
                }
            }
        }
    }

    memset(s_vox, 0, sizeof(s_vox));
    uint16_t top = 0;
    for(int32_t iy = 0; iy < SIFT_VNECK; iy++) {
        for(int32_t ix = 0; ix < SIFT_VX; ix++) {
            for(int32_t iz = 0; iz < SIFT_VZ; iz++) {
                int32_t i = (iy * SIFT_VX + ix) * SIFT_VZ + iz;
                if(!s_vox_inside[i]) continue;
                s_vox[i] =
                    (uint8_t)(1 + (sift_hash(ix * 7 + iz * 3, iy * 5) % 4U));
                top++;
            }
        }
    }
    s_vox_total = top;
    s_vox_top = top;
    s_vox_bottom = 0;
    s_vox_flow = 0;
    s_vox_step = 0;
    vox_count();
}

static void sand_init(void)
{
    s.flips = 0;
    s.empty_since = 0;
    s.flip_active = false;
    s.flip_angle = 0.0f;
    vox_init();
}

static void sand_mirror(void)
{
    memset(s_vox_tmp, 0, sizeof(s_vox_tmp));
    for(int32_t iy = 0; iy < SIFT_VY; iy++) {
        for(int32_t ix = 0; ix < SIFT_VX; ix++) {
            const int32_t src = (iy * SIFT_VX + ix) * SIFT_VZ;
            const int32_t dst = ((SIFT_VY - 1 - iy) * SIFT_VX + ix) * SIFT_VZ;
            memcpy(&s_vox_tmp[dst], &s_vox[src], SIFT_VZ);
        }
    }
    memcpy(s_vox, s_vox_tmp, sizeof(s_vox));
    s.empty_since = 0;
    vox_count();
}

static void sift_flip(void)
{
    uint32_t now = lv_tick_get();
    if(s.flip_active) return;
    if(now - s.last_flip_at < 160U) return;
    s.last_flip_at = now;
    s.flip_active = true;
    s.flip_start = now;
    s.flip_angle = 0.0f;
    s.flips++;
    s.last_input = now;
    snprintf(s.notice, sizeof(s.notice), "FLIP %02d", s.flips);
    s.notice_until = now + 1200U;
    vibe_pulse();
    printf("[sift_watch] flip=%d\n", s.flips);
}

static void update_flip(uint32_t now)
{
    if(!s.flip_active) return;
    uint32_t elapsed = now - s.flip_start;
    if(elapsed >= SIFT_FLIP_MS) {
        sand_mirror();
        s.flip_active = false;
        s.flip_angle = 0.0f;
        return;
    }
    s.flip_angle = (float)elapsed / (float)SIFT_FLIP_MS * SIFT_PI;
}

static void sand_step(void)
{
    if(s.flip_active) return;
    s_vox_step++;
    const uint32_t step = s_vox_step;
    uint16_t crossed = 0;
    static const int8_t dirs[8][2] = {
        {1, 0}, {-1, 0}, {0, 1}, {0, -1}, {1, 1}, {1, -1}, {-1, 1}, {-1, -1},
    };

    for(int32_t iy = SIFT_VY - 1; iy >= 0; iy--) {
        const int32_t xf = (int32_t)((step + (uint32_t)iy) & 1U);
        const int32_t zf = (int32_t)((step + (uint32_t)iy * 3U) & 1U);
        for(int32_t nx = 0; nx < SIFT_VX; nx++) {
            const int32_t ix = xf ? nx : SIFT_VX - 1 - nx;
            const int32_t row_base = (iy * SIFT_VX + ix) * SIFT_VZ;
            for(int32_t nz = 0; nz < SIFT_VZ; nz++) {
                const int32_t iz = zf ? nz : SIFT_VZ - 1 - nz;
                const int32_t i = row_base + iz;
                const uint8_t v = s_vox[i];
                if(v == 0) continue;
                if((sift_hash(ix * 13 + iz * 7, iy * 11 + (int32_t)step) %
                    100U) < 35U)
                    continue;

                bool moved = false;
                if(iy + 1 < SIFT_VY) {
                    const int32_t ni = ((iy + 1) * SIFT_VX + ix) * SIFT_VZ + iz;
                    if(s_vox_inside[ni] && s_vox[ni] == 0) {
                        s_vox[ni] = v;
                        s_vox[i] = 0;
                        moved = true;
                        if(iy < SIFT_VNECK && iy + 1 >= SIFT_VNECK) crossed++;
                    }
                }
                if(!moved && iy + 1 < SIFT_VY) {
                    const int32_t start =
                        (int32_t)(sift_hash(ix * 3 + iz * 5,
                                            iy * 7 + (int32_t)step) %
                                  8U);
                    for(int32_t k = 0; k < 8; k++) {
                        const int8_t * d = dirs[(start + k) & 7];
                        const int32_t tx = ix + d[0];
                        const int32_t tz = iz + d[1];
                        if(tx < 0 || tx >= SIFT_VX || tz < 0 || tz >= SIFT_VZ)
                            continue;
                        const int32_t ni =
                            ((iy + 1) * SIFT_VX + tx) * SIFT_VZ + tz;
                        if(!s_vox_inside[ni] || s_vox[ni] != 0) continue;
                        s_vox[ni] = v;
                        s_vox[i] = 0;
                        if(iy < SIFT_VNECK && iy + 1 >= SIFT_VNECK) crossed++;
                        break;
                    }
                }
            }
        }
    }

    uint32_t target = (uint32_t)crossed * 9U;
    s_vox_flow = (uint16_t)(((uint32_t)s_vox_flow * 82U + target * 18U) / 100U);
    vox_count();
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

static void update_orbit(uint32_t elapsed_ms)
{
    float dt = (float)elapsed_ms / 1000.0f;
    if(dt > 0.1f) dt = 0.1f;
    float ease = 1.0f - expf(-dt * 12.0f);
    s.orbit_yaw += (s.orbit_yaw_target - s.orbit_yaw) * ease;
    s.orbit_elev += (s.orbit_elev_target - s.orbit_elev) * ease;
}

static void update_idle(uint32_t now)
{
    if(s.view == VIEW_WATCH && s.dim_on &&
       now - s.last_input > SIFT_IDLE_DIM_MS) {
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

    for(int32_t y = 8; y < SIFT_H; y += 7) {
        for(int32_t x = 8; x < SIFT_W; x += 7) {
            uint32_t h = sift_hash(x, y);
            if(h % 100U > 94U) {
                put_px(x, y, (h & 1U) ? COL_LINE : COL_MINT_DIM);
            }
        }
    }

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
    for(int32_t i = 0; i < 4; i++)
        fill_rect(x + 3 + i * 4, y + 3, 3, 4, COL_MINT);
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
    else
        fill_rect(22, 15, 6, 6, COL_SAND_DIM);
    draw_text("SIFT", 34, 13, 2, COL_MINT, 0);
    draw_apps_icon(100, 15);
    draw_text("APPS", 114, 16, 1, COL_MUTED, 0);
    draw_battery(344, 14);
}

static void draw_sensor_label(void)
{
    const char * label = s.sensor_live
                             ? "6-AXIS LIVE"
                             : (s.auto_now ? "6-AXIS AUTO" : "6-AXIS SIM");
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
    snprintf(date, sizeof(date), "%02d %s", s.clock.mday,
             month_name(s.clock.month));
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

typedef struct {
    float cy;
    float sy;
    float ce;
    float se;
} orbit_m_t;

typedef struct {
    int32_t xs[4];
    int32_t ys[4];
    int32_t depth;
    uint16_t color;
} quad_face_t;

static void orbit_matrix(orbit_m_t * m)
{
    m->cy = cosf(s.orbit_yaw);
    m->sy = sinf(s.orbit_yaw);
    m->ce = cosf(s.orbit_elev);
    m->se = sinf(s.orbit_elev);
}

static float flip_cos(void)
{
    return s.flip_active ? cosf(s.flip_angle) : 1.0f;
}

static float flip_sin(void)
{
    return s.flip_active ? sinf(s.flip_angle) : 0.0f;
}

static int32_t map_local_y(float local_y, const orbit_m_t * m)
{
    float k = flip_cos() * m->ce - flip_sin() * m->cy * m->se;
    return round_f32((float)SIFT_HG_CY + (local_y - (float)SIFT_HG_CY) * k);
}

static int32_t map_local_x(float x, float local_y, const orbit_m_t * m)
{
    return round_f32(x + (local_y - (float)SIFT_HG_CY) * flip_sin() * m->sy);
}

static void project3(int32_t x, int32_t y, int32_t z, const orbit_m_t * m,
                     int32_t * out_x, int32_t * out_y, int32_t * out_depth)
{
    float fc = flip_cos();
    float fs = flip_sin();
    float yf = (float)y * fc - (float)z * fs;
    float zf = (float)y * fs + (float)z * fc;
    float px = (float)SIFT_HG_CX + (float)x * m->cy - zf * m->sy;
    float py = (float)SIFT_HG_CY - yf * m->ce + (float)x * m->sy * m->se +
               zf * m->cy * m->se;
    float pd = -((float)x * m->ce * m->sy + yf * m->se + zf * m->ce * m->cy);
    *out_x = round_f32(px);
    *out_y = round_f32(py);
    *out_depth = round_f32(pd * 100.0f);
}

static void ellipse_arc(int32_t cx, int32_t cy, int32_t rx, int32_t ry,
                        int32_t start_deg, int32_t end_deg, uint16_t color,
                        int32_t size)
{
    int32_t steps = 48;
    for(int32_t i = 0; i <= steps; i++) {
        float a = ((float)start_deg +
                   (float)(end_deg - start_deg) * (float)i / (float)steps) *
                  SIFT_PI / 180.0f;
        int32_t x = cx + round_f32((float)rx * cosf(a));
        int32_t y = cy + round_f32((float)ry * sinf(a));
        fill_rect(x - size / 2, y - size / 2, size, size, color);
    }
}

static void fill_quad(const int32_t * xs, const int32_t * ys, uint16_t color)
{
    int32_t min_y = ys[0];
    int32_t max_y = ys[0];
    for(int32_t i = 1; i < 4; i++) {
        if(ys[i] < min_y) min_y = ys[i];
        if(ys[i] > max_y) max_y = ys[i];
    }
    if(min_y < 0) min_y = 0;
    if(max_y >= SIFT_H) max_y = SIFT_H - 1;
    for(int32_t y = min_y; y <= max_y; y++) {
        int32_t xi[4];
        int32_t count = 0;
        for(int32_t i = 0; i < 4; i++) {
            int32_t j = (i + 1) & 3;
            int32_t y1 = ys[i];
            int32_t y2 = ys[j];
            if((y1 <= y && y2 > y) || (y2 <= y && y1 > y)) {
                xi[count++] =
                    xs[i] + (int32_t)(((int64_t)(y - y1) * (xs[j] - xs[i])) /
                                      (y2 - y1));
            }
        }
        if(count < 2) continue;
        int32_t x0 = xi[0];
        int32_t x1 = xi[0];
        for(int32_t i = 1; i < count; i++) {
            if(xi[i] < x0) x0 = xi[i];
            if(xi[i] > x1) x1 = xi[i];
        }
        fill_rect(x0, y, x1 - x0 + 1, 1, color);
    }
}

static void draw_box3(int32_t cx, int32_t cy, int32_t cz, int32_t hx,
                      int32_t hy, int32_t hz, const orbit_m_t * m, bool back)
{
    static const int8_t face_idx[6][4] = {
        {4, 5, 6, 7}, {1, 0, 3, 2}, {7, 6, 2, 3},
        {0, 1, 5, 4}, {5, 6, 2, 1}, {0, 4, 7, 3},
    };
    static const int8_t face_n[6][3] = {
        {0, 0, 1}, {0, 0, -1}, {0, 1, 0}, {0, -1, 0}, {1, 0, 0}, {-1, 0, 0},
    };
    int32_t corners[8][3] = {
        {cx - hx, cy - hy, cz - hz}, {cx + hx, cy - hy, cz - hz},
        {cx + hx, cy + hy, cz - hz}, {cx - hx, cy + hy, cz - hz},
        {cx - hx, cy - hy, cz + hz}, {cx + hx, cy - hy, cz + hz},
        {cx + hx, cy + hy, cz + hz}, {cx - hx, cy + hy, cz + hz},
    };
    int32_t cam_x = round_f32(-m->ce * m->sy * 100.0f);
    int32_t cam_y = round_f32(-m->se * 100.0f);
    int32_t cam_z = round_f32(-m->ce * m->cy * 100.0f);
    quad_face_t list[6];
    int32_t count = 0;
    float fc = flip_cos();
    float fs = flip_sin();

    for(int32_t f = 0; f < 6; f++) {
        float nx = (float)face_n[f][0];
        float ny = (float)face_n[f][1] * fc - (float)face_n[f][2] * fs;
        float nz = (float)face_n[f][1] * fs + (float)face_n[f][2] * fc;
        if(nx * cam_x + ny * cam_y + nz * cam_z >= 0.0f) continue;
        quad_face_t face;
        int32_t depth = 0;
        for(int32_t k = 0; k < 4; k++) {
            const int32_t * c = corners[face_idx[f][k]];
            int32_t d;
            project3(c[0], c[1], c[2], m, &face.xs[k], &face.ys[k], &d);
            depth += d;
        }
        face.depth = depth / 4;
        if((face.depth > 0) != back) continue;
        float lum = nx * -0.35f + ny * 0.8f + nz * 0.45f;
        face.color =
            lum > 0.5f ? COL_WOOD_HI : (lum > 0.05f ? COL_WOOD : COL_WOOD_DARK);
        list[count++] = face;
    }

    for(int32_t i = 1; i < count; i++) {
        quad_face_t key = list[i];
        int32_t j = i - 1;
        while(j >= 0 && list[j].depth < key.depth) {
            list[j + 1] = list[j];
            j--;
        }
        list[j + 1] = key;
    }

    for(int32_t i = 0; i < count; i++) {
        fill_quad(list[i].xs, list[i].ys, list[i].color);
        for(int32_t k = 0; k < 4; k++) {
            int32_t n = (k + 1) & 3;
            draw_line(list[i].xs[k], list[i].ys[k], list[i].xs[n],
                      list[i].ys[n], COL_WOOD_DARK, 1);
        }
    }
}

static void draw_frame3d(const orbit_m_t * m, bool back)
{
    static const int16_t posts[4][2] = {
        {-SIFT_FRAME_HALF_X, -SIFT_FRAME_HALF_Z},
        {SIFT_FRAME_HALF_X, -SIFT_FRAME_HALF_Z},
        {-SIFT_FRAME_HALF_X, SIFT_FRAME_HALF_Z},
        {SIFT_FRAME_HALF_X, SIFT_FRAME_HALF_Z},
    };
    for(int32_t i = 0; i < 4; i++) {
        draw_box3(posts[i][0], 0, posts[i][1], SIFT_FRAME_POST_HALF,
                  SIFT_FRAME_POST_TOP, SIFT_FRAME_POST_HALF, m, back);
    }
    draw_box3(0, SIFT_FRAME_CAP_Y, 0, SIFT_FRAME_CAP_HALF_X,
              SIFT_FRAME_CAP_HALF_Y, SIFT_FRAME_CAP_HALF_Z, m, back);
    draw_box3(0, -SIFT_FRAME_CAP_Y, 0, SIFT_FRAME_CAP_HALF_X,
              SIFT_FRAME_CAP_HALF_Y, SIFT_FRAME_CAP_HALF_Z, m, back);
}

static void draw_cap_details(const orbit_m_t * m)
{
    int32_t faces[2];
    if(m->se > 0.05f) {
        faces[0] = SIFT_FRAME_CAP_Y + SIFT_FRAME_CAP_HALF_Y;
        faces[1] = -SIFT_FRAME_CAP_Y + SIFT_FRAME_CAP_HALF_Y;
    }
    else if(m->se < -0.05f) {
        faces[0] = SIFT_FRAME_CAP_Y - SIFT_FRAME_CAP_HALF_Y;
        faces[1] = -SIFT_FRAME_CAP_Y - SIFT_FRAME_CAP_HALF_Y;
    }
    else {
        return;
    }

    for(int32_t f = 0; f < 2; f++) {
        int32_t face_y = faces[f];
        for(int32_t i = -1; i <= 1; i++) {
            int32_t ax, ay, bx, by, d;
            project3(-78, face_y, i * 44, m, &ax, &ay, &d);
            project3(78, face_y, i * 44, m, &bx, &by, &d);
            draw_line(ax, ay, bx, by, COL_WOOD_DARK, 1);
        }
        for(int32_t sx = -1; sx <= 1; sx += 2) {
            for(int32_t sz = -1; sz <= 1; sz += 2) {
                int32_t px, py, d;
                project3(sx * 96, face_y, sz * 64, m, &px, &py, &d);
                fill_rect(px - 1, py - 1, 3, 3, COL_SAND_DIM);
            }
        }
    }
}

static void draw_orbit_rims(const orbit_m_t * m)
{
    static const int16_t ring_y[2] = {120, -120};
    static const int16_t ring_r[2] = {80, 80};
    float fc = flip_cos();
    float fs = flip_sin();
    for(int32_t i = 0; i < 2; i++) {
        int32_t cx =
            round_f32((float)SIFT_HG_CX - (float)ring_y[i] * fs * m->sy);
        int32_t cy =
            round_f32((float)SIFT_HG_CY - (float)ring_y[i] * fc * m->ce +
                      (float)ring_y[i] * fs * m->cy * m->se);
        int32_t ry = round_f32((float)ring_r[i] *
                               fabsf(fs * m->ce + fc * m->cy * m->se));
        if(ry < 1) ry = 1;
        ellipse_arc(cx, cy, ring_r[i], ry, 180, 360, COL_MINT_DIM, 2);
        ellipse_arc(cx, cy, ring_r[i], ry, 0, 180, COL_MINT_HI, 2);
    }
}

static void draw_glass_3d(const orbit_m_t * m)
{
    float k = flip_cos() * m->ce - flip_sin() * m->cy * m->se;
    if(fabsf(k) < 0.02f) return;
    int32_t rh = round_f32((float)SIFT_CELL * fabsf(k));
    if(rh < 1) rh = 1;
    for(int32_t row = 0; row < SIFT_ROWS; row++) {
        float local_y = (float)SIFT_HG_TOP + (float)row * (float)SIFT_CELL;
        int32_t y = map_local_y(local_y, m);
        int32_t cx = map_local_x((float)SIFT_HG_CX, local_y, m);
        int32_t half = hg_half_width(row < 40 ? row : 79 - row) + 7;
        fill_rect(cx - half, y, half * 2, rh, COL_GLASS);
        uint16_t edge = (row < 4 || row > 75) ? COL_MINT : COL_MINT_DIM;
        fill_rect(cx - half, y, 2, rh, edge);
        fill_rect(cx + half - 2, y, 2, rh, edge);
        if((row % 7) == 0 || row < 8 || row > 71) {
            fill_rect(cx - half + 2, y, 1, rh, COL_MINT_HI);
            fill_rect(cx + half - 3, y, 1, rh, COL_MINT_HI);
        }
    }

    static const int16_t hi_x[5] = {144, 150, 157, 231, 237};
    static const int16_t hi_top[5] = {133, 145, 157, 281, 292};
    static const int16_t hi_h[5] = {18, 11, 8, 8, 19};
    for(int32_t i = 0; i < 5; i++) {
        float center = (float)hi_top[i] + (float)hi_h[i] * 0.5f;
        int32_t cy = map_local_y(center, m);
        int32_t cx = map_local_x((float)hi_x[i], center, m);
        int32_t hh = round_f32((float)hi_h[i] * fabsf(k));
        if(hh < 1) hh = 1;
        fill_rect(cx, cy - hh / 2, 3, hh, i < 3 ? COL_MINT_HI : COL_MINT);
    }
    int32_t neck_y = map_local_y((float)(SIFT_NECK_Y - 4), m);
    int32_t neck_h = round_f32(8.0f * fabsf(k));
    if(neck_h < 1) neck_h = 1;
    int32_t neck_cx1 =
        map_local_x((float)(SIFT_HG_CX - 14 + 1), (float)(SIFT_NECK_Y - 4), m);
    int32_t neck_cx2 =
        map_local_x((float)(SIFT_HG_CX + 14 - 3), (float)(SIFT_NECK_Y - 4), m);
    fill_rect(neck_cx1, neck_y - neck_h / 2, 2, neck_h, COL_MINT_DIM);
    fill_rect(neck_cx2, neck_y - neck_h / 2, 2, neck_h, COL_MINT_DIM);
}

static inline bool vox_solid(int32_t ix, int32_t iy, int32_t iz)
{
    if(ix < 0 || ix >= SIFT_VX || iy < 0 || iy >= SIFT_VY || iz < 0 ||
       iz >= SIFT_VZ) {
        return false;
    }
    return s_vox[(iy * SIFT_VX + ix) * SIFT_VZ + iz] != 0;
}

static void build_vox_sprites(void)
{
    uint16_t tones[4] = {COL_SAND_DIM, COL_SAND, COL_SAND_HI, COL_SAND_PALE};
    for(int32_t i = 0; i < 4; i++) {
        for(int32_t r = 0; r < 8; r++) {
            for(int32_t c = 0; c < 8; c++) s_vox_sprite[i][r][c] = tones[i];
        }
        for(int32_t c = 0; c < 8; c++) s_vox_sprite[i][0][c] = COL_SAND_PALE;
        for(int32_t r = 0; r < 8; r++) s_vox_sprite[i][r][0] = COL_SAND_PALE;
    }
    s_vox_sprites_ready = true;
}

static void draw_voxels(const orbit_m_t * m)
{
    if(!s_vox_sprites_ready) build_vox_sprites();
    memset(s_vbins, 0, sizeof(s_vbins));

    for(int32_t iy = 0; iy < SIFT_VY; iy++) {
        for(int32_t ix = 0; ix < SIFT_VX; ix++) {
            const int32_t base = (iy * SIFT_VX + ix) * SIFT_VZ;
            for(int32_t iz = 0; iz < SIFT_VZ; iz++) {
                const uint8_t v = s_vox[base + iz];
                if(v == 0) continue;
                if(vox_solid(ix - 1, iy, iz) && vox_solid(ix + 1, iy, iz) &&
                   vox_solid(ix, iy - 1, iz) && vox_solid(ix, iy + 1, iz) &&
                   vox_solid(ix, iy, iz - 1) && vox_solid(ix, iy, iz + 1)) {
                    continue;
                }
                const float wx = (ix + 0.5f) * SIFT_VCELL - 90.0f;
                const float wz = (iz + 0.5f) * SIFT_VCELL - 90.0f;
                const float y_local =
                    (float)SIFT_HG_TOP +
                    (iy + 0.5f) *
                        ((float)(SIFT_HG_BOTTOM - SIFT_HG_TOP) / SIFT_VY);
                const float wy = -(y_local - (float)SIFT_HG_CY);
                int32_t px, py, depth;
                project3(round_f32(wx), round_f32(wy), round_f32(wz), m, &px,
                         &py, &depth);
                int32_t bin = (depth + 22000) * SIFT_VBINS / 44000;
                bin = clamp_i32(bin, 0, SIFT_VBINS - 1);
                if(s_vbins[bin] >= SIFT_VCAP) continue;
                const int32_t pos = bin * SIFT_VCAP + s_vbins[bin]++;
                s_vpx[pos] = (int16_t)px;
                s_vpy[pos] = (int16_t)py;
                int32_t ci = (int32_t)v - 1;
                if(bin >= 12 && ci > 0) ci--;
                else if(bin <= 3 && ci < 3)
                    ci++;
                s_vpc[pos] = (uint8_t)ci;
            }
        }
    }

    for(int32_t bin = SIFT_VBINS - 1; bin >= 0; bin--) {
        const int32_t base = bin * SIFT_VCAP;
        const uint16_t n = s_vbins[bin];
        for(uint16_t k = 0; k < n; k++) {
            const int32_t px = s_vpx[base + k];
            const int32_t py = s_vpy[base + k];
            const uint16_t (*sprite)[8] = s_vox_sprite[s_vpc[base + k]];
            for(int32_t r = 0; r < 8; r++) {
                for(int32_t c = 0; c < 8; c++) {
                    put_px(px - 4 + c, py - 4 + r, sprite[r][c]);
                }
            }
        }
    }
}

static void draw_hourglass(void)
{
    for(int32_t y = 110; y < 350; y += 9) {
        for(int32_t x = 45; x < 345; x += 9) {
            int32_t dx = x - 195;
            int32_t dy = y - 226;
            if(dx * dx / 4 + dy * dy < 18000 &&
               (sift_hash(x, y) % 100U) > 82U) {
                put_px(x, y, COL_INK2);
            }
        }
    }

    orbit_m_t m;
    orbit_matrix(&m);

    draw_frame3d(&m, true);
    draw_glass_3d(&m);
    draw_voxels(&m);
    draw_orbit_rims(&m);
    draw_frame3d(&m, false);
    draw_cap_details(&m);

    bool nearly_empty =
        s.stats.total > 0 && (s.stats.top * 100U / s.stats.total) < 5U;
    if(!nearly_empty && s.stats.flow > 2U) {
        int32_t glow_y = map_local_y((float)SIFT_NECK_Y, &m);
        fill_rect(181, glow_y - 2, 28, 3, COL_SAND);
        fill_rect(188, glow_y - 6, 2, 9, COL_SAND_HI);
        fill_rect(200, glow_y - 4, 2, 7, COL_SAND_HI);
    }
}

static void draw_button(int32_t x, int32_t y, int32_t w, int32_t h,
                        const char * label, uint16_t fill, uint16_t border,
                        uint16_t text)
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

    uint32_t percent =
        s.stats.total == 0 ? 0 : (uint32_t)s.stats.top * 100U / s.stats.total;
    if(percent < 5U) percent = 0;
    snprintf(value, sizeof(value), "%u%%", (unsigned)percent);
    draw_text("SAND", 195, 376, 1, COL_MUTED, 1);
    draw_text(value, 195, 385, 2, COL_SAND, 1);

    snprintf(value, sizeof(value), "%02u",
             (unsigned)(s.stats.flow > 99U ? 99U : s.stats.flow));
    draw_text("FLOW", 368, 376, 1, COL_MUTED, 2);
    draw_text(value, 368, 385, 2, COL_MINT, 2);

    bool empty = s.stats.total > 0 && (s.stats.top * 100U / s.stats.total) < 5U;
    bool pulse = ((lv_tick_get() / 230U) % 2U) != 0U;
    uint16_t flip_color =
        s.sensor_live ? (empty && pulse ? COL_SAND_HI : COL_SAND) : COL_DIM;
    draw_text(s.sensor_live ? "SENSOR FLIP / TURN WATCH FACE DOWN"
                            : "SENSOR FLIP / LINK 6-AXIS",
              195, 404, 1, flip_color, 1);

    const char * hint = "TAP FLIP  /  DRAG ORBIT  /  SWIPE PAGES";
    if(s.sensor_live) hint = "TAP FLIP  /  DRAG ORBIT  /  TILT SENSOR";
    else if(s.auto_now)
        hint = "TAP FLIP  /  DRAG ORBIT  /  AUTO DRIFT";
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

static void draw_app_header(const char * title, const char * subtitle)
{
    char time_text[8];
    snprintf(time_text, sizeof(time_text), "%02d:%02d", clock_hour(),
             s.clock.minute);
    draw_back_chevron(22, 22);
    draw_text(title, 48, 16, 3, COL_PAPER, 0);
    draw_text(time_text, 368, 18, 2, COL_PAPER, 2);
    if(!s.h24) draw_text(clock_ampm(), 368, 34, 1, COL_SAND, 2);
    hline(22, 44, 346, COL_LINE);
    draw_text(subtitle, 22, 52, 1, COL_MUTED, 0);
}

static void draw_mini_hourglass(int32_t cx, int32_t cy, uint16_t color,
                                uint16_t sand)
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

static void draw_icon_zombie(int32_t cx, int32_t cy)
{
    fill_rect(cx - 8, cy - 20, 16, 13, COL_LINE);
    fill_rect(cx - 6, cy - 18, 12, 9, COL_MINT_DIM);
    fill_rect(cx - 4, cy - 15, 3, 3, COL_SAND);
    fill_rect(cx + 2, cy - 15, 3, 3, COL_SAND);
    fill_rect(cx - 5, cy - 10, 10, 2, COL_INK);
    fill_rect(cx - 2, cy - 8, 4, 2, COL_SAND_DIM);
    fill_rect(cx - 13, cy + 7, 26, 6, COL_INK);
    fill_rect(cx - 10, cy + 8, 20, 4, COL_LINE2);
    fill_rect(cx - 4, cy + 3, 8, 8, COL_LINE2);
    draw_line(cx, cy + 4, cx + 15, cy - 6, COL_SAND_DIM, 3);
    fill_rect(cx + 13, cy - 9, 5, 5, COL_SAND);
    fill_rect(cx - 24, cy + 2, 7, 2, COL_MINT);
    fill_rect(cx - 24, cy + 2, 2, 7, COL_MINT);
    fill_rect(cx + 18, cy + 2, 7, 2, COL_MINT);
    fill_rect(cx + 23, cy + 2, 2, 7, COL_MINT);
    fill_rect(cx - 24, cy - 4, 2, 6, COL_MINT_DIM);
    fill_rect(cx + 23, cy - 4, 2, 6, COL_MINT_DIM);
}

static void draw_tile_icon(uint8_t index, int32_t cx, int32_t cy)
{
    if(index == 0) draw_mini_hourglass(cx, cy, COL_SAND, COL_SAND_HI);
    else if(index == 1)
        draw_icon_stopwatch(cx, cy);
    else if(index == 2)
        draw_icon_weather(cx, cy);
    else if(index == 3)
        draw_icon_settings(cx, cy);
    else
        draw_icon_zombie(cx, cy);
}

static void app_tile_rect(uint8_t index, int32_t * x, int32_t * y, int32_t * w,
                          int32_t * h)
{
    *x = 22 + (index % 3) * 119;
    *y = 82 + (index / 3) * 142;
    *w = 108;
    *h = 130;
}

static const char * app_title(uint8_t index)
{
    static const char * names[] = {"TIMER", "STOPWATCH", "WEATHER", "SETTINGS",
                                   "ZOMBIE"};
    return names[index < 5U ? index : 0U];
}

static const char * app_subtitle(uint8_t index)
{
    static const char * names[] = {"FOCUS", "PRECISION", "LOCAL SKY", "SYSTEM",
                                   "ENDLESS"};
    return names[index < 5U ? index : 0U];
}

static void app_status(uint8_t index, char * out, size_t out_size)
{
    if(index == 0) {
        if(s.timer_running) {
            uint32_t secs = (s.timer_remaining + 999U) / 1000U;
            snprintf(out, out_size, "%02u:%02u", (unsigned)(secs / 60U),
                     (unsigned)(secs % 60U));
        }
        else if(s.timer_remaining == 0U)
            snprintf(out, out_size, "DONE");
        else
            snprintf(out, out_size, "%uM",
                     (unsigned)(s.timer_duration / 60000U));
    }
    else if(index == 1) {
        snprintf(out, out_size, "%s",
                 s.sw_running ? "RUN" : (s.sw_elapsed ? "HOLD" : "ZERO"));
    }
    else if(index == 2) {
        int temp_c, high_c, low_c, humidity, wind, condition;
        bool night;
        weather_values(&temp_c, &high_c, &low_c, &humidity, &wind, &night,
                       &condition);
        int temp = weather_temp(temp_c);
        snprintf(out, out_size, "%d~%c", temp, s.weather_unit);
    }
    else if(index == 3) {
        snprintf(out, out_size, "%s", s.auto_drift ? "AUTO" : "MANUAL");
    }
    else {
        int32_t best = zc_best_wave();
        if(best > 0)
            snprintf(out, out_size, "WAVE %02d", (int)(best > 99 ? 99 : best));
        else
            snprintf(out, out_size, "READY");
    }
}

static void draw_app_drawer(void)
{
    draw_app_header("APPS", "05 PIXEL TOOLS");
    for(uint8_t i = 0; i < 5; i++) {
        int32_t x;
        int32_t y;
        int32_t w;
        int32_t h;
        app_tile_rect(i, &x, &y, &w, &h);
        bool selected = i == s.app_index;
        fill_rect(x, y, w, h, selected ? COL_INK2 : COL_INK);
        stroke_rect(x, y, w, h, selected ? COL_SAND : COL_LINE,
                    selected ? 2 : 1);
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
        draw_text(status, x + w / 2, y + 109, 1,
                  selected ? COL_SAND : COL_MUTED, 1);
        if((i == 0 && s.timer_running) || (i == 1 && s.sw_running)) {
            if((lv_tick_get() / 240U) % 2U == 0U)
                fill_rect(x + w - 16, y + h - 14, 4, 4, COL_SAND);
        }
    }
    hline(22, 376, 346, COL_LINE);
    draw_text("TAP OPEN  /  SWIPE PAGES", 195, 390, 1, COL_DIM, 1);
}

static void draw_timer_bar(int32_t x, int32_t y, int32_t w, int32_t h,
                           int32_t percent, bool active)
{
    fill_rect(x, y, w, h, COL_INK2);
    stroke_rect(x, y, w, h, COL_LINE2, 1);
    int32_t fill_w = (w - 4) * clamp_i32(percent, 0, 100) / 100;
    if(fill_w > 0) {
        fill_rect(x + 2, y + 2, fill_w, h - 4,
                  active ? COL_SAND : COL_SAND_DIM);
    }
    for(int32_t tx = x + 10; tx < x + w - 4; tx += 10)
        fill_rect(tx, y + 2, 1, h - 4, COL_INK);
}

static void draw_timer(void)
{
    char time_text[12];
    uint32_t secs = (s.timer_remaining + 999U) / 1000U;
    snprintf(time_text, sizeof(time_text), "%02u:%02u", (unsigned)(secs / 60U),
             (unsigned)(secs % 60U));
    char subtitle[32];
    snprintf(subtitle, sizeof(subtitle), "COUNTDOWN / %u MIN",
             (unsigned)(s.timer_duration / 60000U));
    draw_app_header("TIMER", subtitle);

    bool done = s.timer_remaining == 0U && !s.timer_running;
    bool blink = (lv_tick_get() / 260U) % 2U == 0U;
    if(done && blink) stroke_rect(58, 84, 274, 64, COL_SAND, 2);
    draw_text(time_text, 195, 94, 7, done && blink ? COL_SAND : COL_PAPER, 1);
    draw_text("REMAINING", 195, 150, 1, COL_DIM, 1);
    int32_t progress =
        s.timer_duration
            ? (int32_t)(s.timer_remaining * 100U / s.timer_duration)
            : 0;
    draw_timer_bar(45, 170, 300, 15, progress, s.timer_running);

    static const uint32_t presets[] = {60000U, 180000U, 300000U, 600000U};
    static const char * labels[] = {"1M", "3M", "5M", "10M"};
    for(uint8_t i = 0; i < 4; i++) {
        int32_t x = 22 + i * 89;
        bool selected = i == s.timer_selected;
        draw_button(x, 214, 79, 30, labels[i], selected ? COL_INK2 : COL_INK,
                    selected ? COL_SAND : COL_LINE2,
                    selected ? COL_SAND : COL_MUTED);
    }

    const char * status =
        s.timer_running ? "RUNNING"
                        : (done ? "TIME UP"
                                : (s.timer_remaining < presets[s.timer_selected]
                                       ? "PAUSED"
                                       : "READY"));
    draw_text(status, 195, 260, 2,
              s.timer_running ? COL_MINT : (done ? COL_SAND : COL_PAPER), 1);

    const char * start_label =
        s.timer_running ? "PAUSE" : (done ? "AGAIN" : "START");
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
    snprintf(time_text, sizeof(time_text), "%02u:%02u",
             (unsigned)((total_sec / 60U) % 100U), (unsigned)(total_sec % 60U));
    snprintf(cs_text, sizeof(cs_text), ".%02u",
             (unsigned)((elapsed / 10U) % 100U));
    draw_app_header("STOPWATCH", s.sw_running ? "RUNNING / ENTER TO STOP"
                                              : "PRECISION / ENTER TO START");

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
        fill_rect(sw_ring_x[i] - size / 2, sw_ring_y[i] - size / 2, size, size,
                  color);
    }

    draw_text(time_text, 195, 157, 6, COL_PAPER, 1);
    draw_text(cs_text, 195, 206, 2, COL_SAND, 1);
    if(s.sw_running && (now / 220U) % 2U == 0U)
        fill_rect(144, 222, 4, 4, COL_CORAL);

    char lap[28];
    if(s.sw_lap_count > 0) {
        uint32_t ms = s.sw_laps[s.sw_lap_count - 1];
        snprintf(lap, sizeof(lap), "LAP %02u  %02u:%02u.%02u",
                 (unsigned)s.sw_lap_count, (unsigned)((ms / 60000U) % 100U),
                 (unsigned)((ms / 1000U) % 60U), (unsigned)((ms / 10U) % 100U));
    }
    else
        snprintf(lap, sizeof(lap), "NO LAPS YET");
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

static void weather_values(int * temp_c, int * high_c, int * low_c,
                           int * humidity, int * wind, bool * night,
                           int * condition)
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
        static const int8_t dirs[8][2] = {{1, 0},  {1, 1},   {0, 1},  {-1, 1},
                                          {-1, 0}, {-1, -1}, {0, -1}, {1, -1}};
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
            if(bx * bx + by * by < (radius * 4 / 5) * (radius * 4 / 5))
                continue;
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
        else
            draw_sun(cx, cy, 24);
    }
    else if(condition == 1) {
        if(night) draw_moon(cx - 14, cy - 12, 18);
        else
            draw_sun(cx - 15, cy - 12, 16);
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
        else
            fill_disc(cx, cy, 7, COL_SAND);
    }
    else if(condition == 1) {
        if(night) draw_moon(cx - 4, cy - 3, 6);
        else
            fill_disc(cx - 4, cy - 3, 5, COL_SAND);
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
    weather_values(&temp_c, &high_c, &low_c, &humidity, &wind, &night,
                   &condition);
    char text[32];

    draw_app_header("WEATHER", "LOCAL SKY / OFFLINE SAMPLE");
    draw_weather_art(80, 137, condition, night);

    snprintf(text, sizeof(text), "%d~", weather_temp(temp_c));
    draw_text(text, 164, 92, 7, COL_PAPER, 0);
    fill_rect(314, 96, 44, 24, COL_INK2);
    stroke_rect(314, 96, 44, 24, COL_SKY, 1);
    snprintf(text, sizeof(text), "~%c", s.weather_unit);
    draw_text(text, 336, 102, 2, COL_SKY, 1);

    static const char * conditions[] = {"CLEAR", "CLOUD", "RAIN"};
    draw_text(conditions[condition], 164, 154, 2, COL_SKY, 0);
    snprintf(text, sizeof(text), "H %d~  L %d~", weather_temp(high_c),
             weather_temp(low_c));
    draw_text(text, 164, 178, 1, COL_MUTED, 0);

    hline(22, 212, 346, COL_LINE);
    for(int32_t i = 0; i < 5; i++) {
        int32_t cx = 54 + i * 70;
        int32_t hour_temp = temp_c + ((i == 0) ? 0 : (i == 4 ? -1 : 1));
        char label[6];
        if(i == 0) snprintf(label, sizeof(label), "NOW");
        else
            snprintf(label, sizeof(label), "+%dH", (int)i);
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
    else
        fill_rect(x + 4, y + 4, 12, 14, COL_DIM);
}

static void settings_row_rect(uint8_t index, int32_t * x, int32_t * y,
                              int32_t * w, int32_t * h)
{
    *x = 22;
    *y = 80 + index * 58;
    *w = 346;
    *h = 54;
}

static void draw_settings(void)
{
    static const char * titles[] = {"AUTO DRIFT", "24H CLOCK", "DIM STANDBY",
                                    "SENSOR ZERO"};
    static const char * subs[] = {"IDLE MOTION", "TIME FORMAT", "AFTER 42S",
                                  "TOUCH TO CALIBRATE"};
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
            draw_text(on ? "ON" : "OFF", x + 284, y + 21, 1,
                      on ? COL_SAND : COL_DIM, 2);
        }
        else {
            draw_text(s.sensor_live ? "6-AXIS" : "SIM", x + w - 2, y + 21, 1,
                      s.sensor_live ? COL_MINT : COL_MUTED, 2);
        }
        hline(x, y + h - 2, w, COL_LINE);
    }

    hline(22, 316, 346, COL_LINE);
    const char * sensor = s.sensor_live ? "6-AXIS LIVE" : "SIMULATED";
    static const char * labels[] = {"SENSOR", "PANEL", "KEYS", "IMU", "OS"};
    static const char * values[] = {NULL, "390 X 450", "KEY1 / KEY2",
                                    "LSM6DS3TR-C", "SIFT 0.6"};
    for(uint8_t i = 0; i < 5; i++) {
        int32_t y = 328 + i * 14;
        draw_text(labels[i], 22, y, 1, COL_DIM, 0);
        draw_text(i == 0 ? sensor : values[i], 368, y, 1,
                  i == 0 && s.sensor_live ? COL_MINT : COL_MUTED, 2);
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
    for(int32_t i = 0; i < SIFT_W * SIFT_H; i++)
        s_fb[i] = dim_color(s_fb[i], percent);
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
    if(s.view == VIEW_ZOMBIE) {
        if(s_game_ready) zc_render();
        else
            draw_background();
        draw_panel_mask();
        if(s_canvas != NULL) lv_obj_invalidate(s_canvas);
        return;
    }
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

static bool point_in_rect(int32_t x, int32_t y, int32_t rx, int32_t ry,
                          int32_t rw, int32_t rh)
{
    return x >= rx && x < rx + rw && y >= ry && y < ry + rh;
}

static bool inside_orbit_zone(int32_t x, int32_t y)
{
    return x > 36 && x < 354 && y > 74 && y < 372;
}

static void sift_game_enter(void)
{
    if(s_game_ready) {
        zc_enter();
        if(zc_audio_start()) {
            zc_audio_set_enabled(true);
            zc_audio_set_muted(!zc_audio_on());
        }
        return;
    }
    if(s_fb == NULL) {
        printf("[sift_watch] game has no canvas\n");
        return;
    }
    if(s_game_bg == NULL) {
#if defined(SIFT_HAS_APP_CANVAS_ALLOC)
        s_game_bg = (uint16_t *)app_canvas_mem_alloc((size_t)SIFT_W * SIFT_H *
                                                     sizeof(uint16_t));
#else
        s_game_bg =
            (uint16_t *)lv_malloc((size_t)SIFT_W * SIFT_H * sizeof(uint16_t));
#endif
    }
    zc_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.width = SIFT_W;
    cfg.height = SIFT_H;
    cfg.safe_inset = SIFT_PANEL_RADIUS;
    cfg.embedded = true;
    cfg.show_scanlines = true;
    cfg.hooks = &s_game_hooks;
    s_game_ready = zc_create(s_fb, s_game_bg, &cfg);
    if(s_game_ready) {
        zc_enter();
        if(zc_audio_start()) {
            zc_audio_set_enabled(true);
            zc_audio_set_muted(!zc_audio_on());
        }
    }
    printf("[sift_watch] game ready=%d bg=%s audio=%d\n", s_game_ready ? 1 : 0,
           s_game_bg != NULL ? "yes" : "no", zc_audio_is_started() ? 1 : 0);
}

static void open_view(sift_view_t view)
{
    sift_view_t previous = s.view;
    if(previous == VIEW_ZOMBIE && view != VIEW_ZOMBIE) {
        zc_leave();
        zc_audio_set_enabled(false);
    }
    s.view = view;
    s.settings_index = 0;
    s.manual_until = 0;
    s.last_input = lv_tick_get();
    s.dimmed = false;
    vibe_pulse();
    if(view == VIEW_ZOMBIE && previous != VIEW_ZOMBIE) sift_game_enter();
    printf("[sift_watch] view=%d\n", (int)view);
}

static void go_back(void)
{
    open_view(s.view == VIEW_APPS ? VIEW_WATCH : VIEW_APPS);
}

static void sift_page_step(int32_t direction)
{
    int32_t next =
        ((int32_t)s.view + direction + SIFT_PAGE_COUNT) % SIFT_PAGE_COUNT;
    open_view((sift_view_t)next);
}

static void sift_handle_swipe(int32_t dx, int32_t dy)
{
    int32_t ax = dx < 0 ? -dx : dx;
    int32_t ay = dy < 0 ? -dy : dy;
    if(ax < SIFT_SWIPE_MIN && ay < SIFT_SWIPE_MIN) return;

    if(ax >= ay) {
        sift_page_step(dx < 0 ? 1 : -1);
    }
    else if(dy < 0) {
        open_view(VIEW_APPS);
    }
    else {
        open_view(VIEW_WATCH);
    }
    printf("[sift_watch] swipe dx=%ld dy=%ld view=%d\n", (long)dx, (long)dy,
           (int)s.view);
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
    if(s.view != VIEW_TIMER && lv_tick_get() < s.timer_alert_until &&
       point_in_rect(x, y, 22, 404, 346, 28)) {
        open_view(VIEW_TIMER);
        return;
    }

    if(s.view == VIEW_WATCH) {
        if(point_in_rect(x, y, 96, 8, 58, 32)) {
            open_view(VIEW_APPS);
        }
        else {
            sift_flip();
        }
        return;
    }

    if(point_in_rect(x, y, 14, 12, 38, 42)) {
        go_back();
        return;
    }

    if(s.view == VIEW_APPS) {
        for(uint8_t i = 0; i < 5; i++) {
            int32_t rx, ry, rw, rh;
            app_tile_rect(i, &rx, &ry, &rw, &rh);
            if(point_in_rect(x, y, rx, ry, rw, rh)) {
                s.app_index = i;
                open_view(i == 4 ? VIEW_ZOMBIE : (sift_view_t)(VIEW_TIMER + i));
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
        else if(point_in_rect(x, y, 234, 302, 84, 42))
            timer_reset();
        return;
    }

    if(s.view == VIEW_STOPWATCH) {
        if(point_in_rect(x, y, 22, 318, 107, 38)) sw_toggle(now);
        else if(point_in_rect(x, y, 141, 318, 107, 38))
            sw_lap(now);
        else if(point_in_rect(x, y, 260, 318, 108, 38))
            sw_reset();
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
            else if(i == 1)
                s.h24 = !s.h24;
            else if(i == 2)
                s.dim_on = !s.dim_on;
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

    if(s.view == VIEW_ZOMBIE) {
        if(!zc_key(key) && (key == LV_KEY_HOME || key == LV_KEY_ESC))
            open_view(VIEW_APPS);
        s.last_input = now;
        return;
    }

    if(s.view == VIEW_WATCH) {
        if(key == LV_KEY_ENTER || key == LV_KEY_NEXT || key == LV_KEY_RIGHT) {
            open_view(VIEW_APPS);
        }
        else if(key == LV_KEY_LEFT)
            s.target_roll = clamp_i32(s.target_roll - 6, -45, 45);
        else if(key == LV_KEY_UP)
            s.target_pitch = clamp_i32(s.target_pitch - 5, -32, 32);
        else if(key == LV_KEY_DOWN)
            s.target_pitch = clamp_i32(s.target_pitch + 5, -32, 32);
        s.manual_until = now + 800U;
        s.last_input = now;
        return;
    }

    if(key == LV_KEY_ESC || key == LV_KEY_HOME) {
        go_back();
        return;
    }

    if(s.view == VIEW_APPS) {
        int32_t col = s.app_index % 3;
        if(key == LV_KEY_RIGHT && s.app_index + 1 < 5) s.app_index++;
        else if(key == LV_KEY_LEFT && col > 0)
            s.app_index--;
        else if(key == LV_KEY_DOWN && s.app_index + 3 < 5)
            s.app_index = (uint8_t)(s.app_index + 3);
        else if(key == LV_KEY_UP && s.app_index >= 3)
            s.app_index = (uint8_t)(s.app_index - 3);
        else if(key == LV_KEY_ENTER) {
            open_view(s.app_index == 4
                          ? VIEW_ZOMBIE
                          : (sift_view_t)(VIEW_TIMER + s.app_index));
        }
        s.last_input = now;
        return;
    }

    if(s.view == VIEW_TIMER) {
        if(key == LV_KEY_ENTER) timer_toggle(now);
        else if(key == LV_KEY_LEFT)
            timer_select((uint8_t)((s.timer_selected + 3) & 3U));
        else if(key == LV_KEY_RIGHT)
            timer_select((uint8_t)((s.timer_selected + 1) & 3U));
        s.last_input = now;
        return;
    }

    if(s.view == VIEW_STOPWATCH) {
        if(key == LV_KEY_ENTER) sw_toggle(now);
        else if(key == LV_KEY_NEXT)
            sw_lap(now);
        else if(key == LV_KEY_LEFT)
            sw_reset();
        s.last_input = now;
        return;
    }

    if(s.view == VIEW_WEATHER) {
        if(key == LV_KEY_ENTER)
            s.weather_unit = s.weather_unit == 'C' ? 'F' : 'C';
        s.last_input = now;
        return;
    }

    if(s.view == VIEW_SETTINGS) {
        if(key == LV_KEY_DOWN)
            s.settings_index = (uint8_t)((s.settings_index + 1) & 3U);
        else if(key == LV_KEY_UP)
            s.settings_index = (uint8_t)((s.settings_index + 3) & 3U);
        else if(key == LV_KEY_ENTER) {
            uint8_t i = s.settings_index;
            if(i == 0) s.auto_drift = !s.auto_drift;
            else if(i == 1)
                s.h24 = !s.h24;
            else if(i == 2)
                s.dim_on = !s.dim_on;
            else {
                sift_imu_zero();
            }
        }
        s.last_input = now;
    }
}

static bool event_point(lv_event_t * event, int32_t * x, int32_t * y)
{
    (void)event;
    lv_indev_t * indev = lv_indev_active();
    if(indev == NULL) return false;
    lv_point_t point;
    lv_indev_get_point(indev, &point);
    lv_area_t area;
    lv_obj_get_coords(s_canvas, &area);
    *x = point.x - area.x1;
    *y = point.y - area.y1;
    return *x >= 0 && *x < SIFT_W && *y >= 0 && *y < SIFT_H;
}

static void sift_canvas_event_cb(lv_event_t * event)
{
    lv_event_code_t code = lv_event_get_code(event);
    if(code == LV_EVENT_KEY) {
        sift_handle_key(lv_event_get_key(event));
        return;
    }

    if(s.view == VIEW_ZOMBIE) {
        int32_t x = 0, y = 0;
        bool has_point = event_point(event, &x, &y);
        if(code == LV_EVENT_PRESSED) {
            if(has_point) zc_pointer(ZC_POINTER_DOWN, (int)x, (int)y);
        }
        else if(code == LV_EVENT_PRESSING) {
            if(has_point) zc_pointer(ZC_POINTER_MOVE, (int)x, (int)y);
        }
        else if(code == LV_EVENT_RELEASED) {
            zc_pointer(has_point ? ZC_POINTER_UP : ZC_POINTER_CANCEL, (int)x,
                       (int)y);
        }
        else if(code == LV_EVENT_PRESS_LOST) {
            zc_pointer(ZC_POINTER_CANCEL, 0, 0);
        }
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
        s.touch_orbit = false;
        s.touch_suppress = s.dimmed;
        if(s.dimmed) {
            s.dimmed = false;
            return;
        }
        s.touch_start_x = x;
        s.touch_start_y = y;
        s.touch_start_roll = s.target_roll;
        s.touch_start_pitch = s.target_pitch;
        s.touch_orbit = s.view == VIEW_WATCH && inside_orbit_zone(x, y);
        s.touch_start_yaw = s.orbit_yaw_target;
        s.touch_start_elev = s.orbit_elev_target;
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
        if(!s.touch_orbit && !s.touch_swiping && maxd >= SIFT_SWIPE_MIN &&
           (maxd >= SIFT_SWIPE_LONG || elapsed <= 280U)) {
            s.touch_swiping = true;
            s.target_roll = s.touch_start_roll;
            s.target_pitch = s.touch_start_pitch;
            s.manual_until = 0;
        }
        if(!s.touch_suppress && s.view == VIEW_WATCH && s.touch_orbit &&
           !s.touch_swiping) {
            s.orbit_yaw_target = s.touch_start_yaw +
                                 (float)dx * (2.0f * SIFT_PI) / (float)SIFT_W;
            s.orbit_elev_target = clamp_f32(
                s.touch_start_elev - (float)dy * 1.15f / (float)SIFT_H,
                SIFT_ORBIT_MIN_ELEV, SIFT_ORBIT_MAX_ELEV);
            s.manual_until = lv_tick_get() + 1800U;
            s.last_input = lv_tick_get();
        }
        else if(!s.touch_suppress && s.view == VIEW_WATCH && !s.touch_swiping) {
            s.target_roll =
                clamp_i32(s.touch_start_roll + dx * 150 / SIFT_W, -45, 45);
            s.target_pitch =
                clamp_i32(s.touch_start_pitch + dy * 105 / SIFT_H, -32, 32);
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
        bool orbit = s.touch_orbit;
        s.touch_active = false;
        s.touch_moved = false;
        s.touch_swiping = false;
        s.touch_suppress = false;
        s.touch_orbit = false;
        s.last_input = lv_tick_get();
        if(suppress) return;

        int32_t ax = dx < 0 ? -dx : dx;
        int32_t ay = dy < 0 ? -dy : dy;
        int32_t maxd = ax > ay ? ax : ay;
        uint32_t elapsed = lv_tick_get() - s.touch_at;
        bool swipe =
            !orbit &&
            (swiping || (has_point && !suppress &&
                         (maxd >= SIFT_SWIPE_LONG ||
                          (maxd >= SIFT_SWIPE_MIN &&
                           (s.view != VIEW_WATCH || elapsed <= 280U)))));
        if(swipe) {
            sift_handle_swipe(dx, dy);
            return;
        }
        if(!moved && has_point) sift_handle_tap(x, y);
        else if(s.view == VIEW_WATCH && moved)
            s.manual_until = lv_tick_get() + 650U;
        return;
    }

    if(code == LV_EVENT_PRESS_LOST) {
        s.touch_active = false;
        s.touch_moved = false;
        s.touch_swiping = false;
        s.touch_suppress = false;
        s.touch_orbit = false;
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
            return;
        }
        s_imu_acce = rt_device_find("acce_sift");
    }
    if(s_imu_acce == NULL) {
        return;
    }
    if(rt_device_open(s_imu_acce, RT_DEVICE_FLAG_RDONLY) != RT_EOK) {
        s_imu_acce = NULL;
        return;
    }
    rt_device_control(s_imu_acce, RT_SENSOR_CTRL_SET_ODR,
                      (void *)(rt_uint32_t)104);
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

    if(fz >= SIFT_IMU_FACE_DOWN_MG) {
        if(!s_imu_face_down) {
            s_imu_face_down = true;
            s_imu_face_down_at = now;
        }
        if(s_imu_flip_armed && now - s_imu_face_down_at >= 160U &&
           now - s_imu_last_flip_at >= SIFT_IMU_FLIP_COOLDOWN_MS) {
            s_imu_flip_armed = false;
            s_imu_last_flip_at = now;
            sift_flip();
        }
    }
    else if(fz <= SIFT_IMU_FACE_UP_MG) {
        s_imu_face_down = false;
        if(!s_imu_flip_armed &&
           now - s_imu_last_flip_at >= SIFT_IMU_FLIP_COOLDOWN_MS) {
            s_imu_flip_armed = true;
        }
    }
}
#else
static void imu_init(void)
{
}
static void imu_update(void)
{
    s.sensor_live = false;
}
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
           (int)SIFT_KEY1_PIN, (int)SIFT_KEY2_PIN, s_key1_down ? 1 : 0,
           s_key2_down ? 1 : 0);
}

static bool key_pressed_edge(int pin, bool * raw, bool * down,
                             uint32_t * raw_at, uint32_t now)
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
    if(key_pressed_edge(SIFT_KEY1_PIN, &s_key1_raw, &s_key1_down,
                        &s_key1_raw_at, now)) {
        printf("[sift_watch] key1 press\n");
        vibe_pulse();
        sift_handle_key(LV_KEY_HOME);
        snprintf(s.notice, sizeof(s.notice), "KEY1");
        s.notice_until = lv_tick_get() + 600U;
    }
    if(key_pressed_edge(SIFT_KEY2_PIN, &s_key2_raw, &s_key2_down,
                        &s_key2_raw_at, now)) {
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

static void vibe_pulse_ms(uint32_t ms)
{
    if(!s_vibe_ready) return;
    rt_pin_write(SIFT_VIBE_PIN, PIN_HIGH);
    s_vibe_on = true;
    s_vibe_off_at = lv_tick_get() + (ms == 0U ? 1U : ms);
}

static void vibe_pulse(void)
{
    vibe_pulse_ms(25U);
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
static void key_init(void)
{
}
static void key_poll(void)
{
}
static void vibe_init(void)
{
}
static void vibe_pulse_ms(uint32_t ms)
{
    (void)ms;
}
static void vibe_pulse(void)
{
}
static void vibe_update(uint32_t now)
{
    (void)now;
}
#endif

static void sift_tick_cb(lv_timer_t * timer)
{
    (void)timer;
    uint32_t now = lv_tick_get();
    uint32_t elapsed = now - s.last_tick;
    if(elapsed > 100U) elapsed = 100U;
    s.last_tick = now;
    if(s.view == VIEW_ZOMBIE) {
        key_poll();
        vibe_update(now);
        zc_tick(now, elapsed);
        zc_audio_set_muted(!zc_audio_on());
        if(zc_wants_exit()) {
            zc_clear_exit();
            open_view(VIEW_APPS);
        }
        sift_render();
        return;
    }

    timer_update(now);
    imu_update();
    key_poll();
    vibe_update(now);
    update_flip(now);
    update_tilt(now);
    update_orbit(elapsed);

    if(s.flip_active) {
        s.sim_accum = 0;
    }
    else {
        s.sim_accum += elapsed;
        uint8_t guard = 0;
        while(s.sim_accum >= SIFT_SIM_STEP_MS && guard++ < 4) {
            sand_step();
            s.sim_accum -= SIFT_SIM_STEP_MS;
        }
    }

    if(s.stats.total > 0) {
        uint32_t top_percent = (uint32_t)s.stats.top * 100U / s.stats.total;
        if(top_percent < 5U) {
            if(s.empty_since == 0U) s.empty_since = now;
            s.stats.flow = 0;
        }
        else
            s.empty_since = 0;
    }

    update_idle(now);
    sift_render();
}

static void sift_create_group(void)
{
    s_group = lv_group_create();
    lv_group_add_obj(s_group, s_canvas);
    lv_group_focus_obj(s_canvas);

    lv_indev_t * indev = NULL;
    while((indev = lv_indev_get_next(indev)) != NULL) {
        lv_indev_type_t type = lv_indev_get_type(indev);
        if(type == LV_INDEV_TYPE_KEYPAD || type == LV_INDEV_TYPE_ENCODER) {
            lv_indev_set_group(indev, s_group);
        }
    }
}

void sift_watch_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    lv_display_t * display = lv_display_get_default();
    int32_t screen_w = display != NULL
                           ? lv_display_get_horizontal_resolution(display)
                           : SIFT_W;
    int32_t screen_h =
        display != NULL ? lv_display_get_vertical_resolution(display) : SIFT_H;

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
    s.orbit_yaw = 0.0f;
    s.orbit_yaw_target = 0.0f;
    s.orbit_elev = 0.30f;
    s.orbit_elev_target = 0.30f;
    s.flip_angle = 0.0f;

    time_t now_time = time(NULL);
    if(now_time > (time_t)SIFT_CLOCK_MIN_VALID)
        s.clock_epoch = (uint32_t)now_time;
    else
        s.clock_epoch = SIFT_CLOCK_EPOCH_2026_01_01;
    s.clock_base_tick = lv_tick_get();

    sand_init();

#if defined(SIFT_HAS_APP_CANVAS_ALLOC)
    s_fb = (uint16_t *)app_canvas_mem_alloc((size_t)SIFT_W * SIFT_H *
                                            sizeof(uint16_t));
#else
    s_fb = (uint16_t *)lv_malloc((size_t)SIFT_W * SIFT_H * sizeof(uint16_t));
#endif
    if(s_fb == NULL) {
        lv_obj_t * error = lv_label_create(screen);
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
    lv_canvas_set_buffer(s_canvas, s_fb, SIFT_W, SIFT_H,
                         LV_COLOR_FORMAT_RGB565);
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
    printf("[sift_watch] created display=%ldx%ld\n", (long)screen_w,
           (long)screen_h);
}

#if defined(LVGL_VERIFY_LOOP_EZIP_ASSETS) && defined(RT_USING_FINSH)
static int sift_zgame(int argc, char ** argv)
{
    (void)argc;
    (void)argv;
    open_view(VIEW_ZOMBIE);
    if(s_game_ready) zc_key(LV_KEY_ENTER);
    return 0;
}
MSH_CMD_EXPORT_ALIAS(sift_zgame, zgame, open zombie game);
#endif

#endif
