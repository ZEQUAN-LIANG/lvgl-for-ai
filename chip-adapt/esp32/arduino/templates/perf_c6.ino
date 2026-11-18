#include <Arduino.h>
#include <SPI.h>
#include <string.h>

#include "Display_ST7789.h"
#include "lvgl.h"

extern "C" {
#include "perf_monitor.h"
}

static uint8_t s_draw_buf[LCD_WIDTH * 40 * 2]
    __attribute__((aligned(4)));
static uint8_t s_rot_buf[LCD_WIDTH * 48 * 2]
    __attribute__((aligned(4)));
static uint8_t s_shadow[LCD_WIDTH * LCD_HEIGHT / 2]
    __attribute__((aligned(4)));

static uint32_t tick_cb(void)
{
    return (uint32_t)millis();
}

static void send_area(const lv_area_t * area, const uint8_t * src,
                      uint32_t stride)
{
    const uint16_t width = (uint16_t)(area->x2 - area->x1 + 1);
    const uint16_t height = (uint16_t)(area->y2 - area->y1 + 1);

    LCD_SetCursor((uint16_t)area->x1, (uint16_t)area->y1,
                  (uint16_t)area->x2, (uint16_t)area->y2);
    SPI.beginTransaction(SPISettings(SPIFreq, MSBFIRST, SPI_MODE0));
    digitalWrite(EXAMPLE_PIN_NUM_LCD_CS, LOW);
    digitalWrite(EXAMPLE_PIN_NUM_LCD_DC, HIGH);
    for(uint16_t row = 0; row < height; row++) {
        int32_t py = area->y1 + row;
        if(py >= 0 && py < LCD_HEIGHT) {
            const uint16_t * pixels = (const uint16_t *)src;
            for(uint16_t col = 0; col < width; col++) {
                int32_t px = area->x1 + col;
                if(px < 0 || px >= LCD_WIDTH) continue;
                uint16_t value = pixels[col];
                uint8_t r = (uint8_t)(((value >> 11) & 0x1F) * 255 / 31);
                uint8_t g = (uint8_t)(((value >> 5) & 0x3F) * 255 / 63);
                uint8_t b = (uint8_t)((value & 0x1F) * 255 / 31);
                uint8_t lum = (uint8_t)((r * 3u + g * 6u + b) / 10u);
                uint8_t nib = (uint8_t)(lum >> 4);
                size_t index = (size_t)py * LCD_WIDTH + (size_t)px;
                if((index & 1u) == 0u) {
                    s_shadow[index / 2u] = (uint8_t)(nib << 4);
                }
                else {
                    s_shadow[index / 2u] |= nib;
                }
            }
        }
        SPI.writeBytes(src, (size_t)width * 2u);
        src += stride;
    }
    digitalWrite(EXAMPLE_PIN_NUM_LCD_CS, HIGH);
    SPI.endTransaction();
}

static void flush_cb(lv_display_t * disp, const lv_area_t * area,
                     uint8_t * px_map)
{
    lv_display_rotation_t rotation = lv_display_get_rotation(disp);
    lv_color_format_t cf = lv_display_get_color_format(disp);
    lv_area_t out_area = *area;
    const uint8_t * src = px_map;
    uint32_t stride = lv_draw_buf_width_to_stride(
        lv_area_get_width(area), cf);

    if(rotation != LV_DISPLAY_ROTATION_0) {
        lv_display_rotate_area(disp, &out_area);
        uint32_t out_stride = lv_draw_buf_width_to_stride(
            lv_area_get_width(&out_area), cf);
        lv_draw_rotate(px_map, s_rot_buf, lv_area_get_width(area),
                       lv_area_get_height(area), (int32_t)stride,
                       (int32_t)out_stride, rotation, cf);
        src = s_rot_buf;
        stride = out_stride;
    }

    send_area(&out_area, src, stride);
    lv_display_flush_ready(disp);
}

static void dump_shadow(void)
{
    static const char hex[] = "0123456789abcdef";
    char line[129];
    size_t index = 0;

    Serial.println();
    Serial.println("SHOT BEGIN 172 320 4");
    while(index < sizeof(s_shadow)) {
        size_t count = 0;
        while(count < 128 && index < sizeof(s_shadow)) {
            uint8_t value = s_shadow[index++];
            line[count++] = hex[value >> 4];
            line[count++] = hex[value & 0x0F];
        }
        line[count] = '\0';
        Serial.println(line);
    }
    Serial.println("SHOT END");
}

static lv_display_t * create_display(void)
{
    lv_display_t * disp = lv_display_create(LCD_WIDTH, LCD_HEIGHT);

    lv_display_set_color_format(disp, LV_COLOR_FORMAT_RGB565);
    lv_display_set_buffers(disp, s_draw_buf, NULL, sizeof(s_draw_buf),
                           LV_DISPLAY_RENDER_MODE_PARTIAL);
    lv_display_set_flush_cb(disp, flush_cb);
    return disp;
}

void setup()
{
    Serial.begin(115200);
    LCD_Init();
    lv_init();
    lv_tick_set_cb(tick_cb);
    create_display();
    perf_monitor_create();
}

void loop()
{
    static char line[PERF_PROTOCOL_MAX_LINE + 1];
    static size_t line_len = 0;

    while(Serial.available() > 0) {
        int value = Serial.read();
        if(value < 0) break;
        char ch = (char)value;
        if(ch == '\r') continue;
        if(ch == '\n') {
            if(line_len > 0) {
                line[line_len] = '\0';
                if(strcmp(line, "SHOT") == 0) {
                    dump_shadow();
                }
                else if(perf_parse_starts_with_perf(line, line_len)) {
                    perf_monitor_ingest(line, line_len);
                }
                line_len = 0;
            }
            continue;
        }
        if(line_len < PERF_PROTOCOL_MAX_LINE) {
            line[line_len++] = ch;
        }
        else {
            line_len = 0;
        }
    }

    lv_timer_handler();
    delay(5);
}
