#include <Arduino.h>
#include <SPI.h>
#include <stdio.h>
#include <string.h>

#include "Display_ST7789.h"
#include "ble_uart.h"
#include "lvgl.h"

extern "C" {
#include "perf_monitor.h"
}

#ifndef PERF_ENABLE_SHOT
#define PERF_ENABLE_SHOT 1
#endif

static uint8_t s_draw_buf[LCD_WIDTH * 40 * 2] __attribute__((aligned(4)));
static uint8_t s_rot_buf[LCD_WIDTH * 48 * 2] __attribute__((aligned(4)));
#if PERF_ENABLE_SHOT
static uint8_t s_shadow[LCD_WIDTH * LCD_HEIGHT / 2]
    __attribute__((aligned(4)));
#endif

static const char * s_layout = "portrait";

enum ReplyChannel { REPLY_USB, REPLY_BLE };

static uint32_t tick_cb(void)
{
    return (uint32_t)millis();
}

static void send_reply(ReplyChannel channel, const char * text)
{
    if(channel == REPLY_BLE) {
        ble_uart_send_line(text);
    }
    else {
        Serial.println(text);
    }
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
#if PERF_ENABLE_SHOT
            const uint16_t * pixels = (const uint16_t *)src;
            for(uint16_t col = 0; col < width; col++) {
                int32_t px = area->x1 + col;
                if(px < 0 || px >= LCD_WIDTH) {
                    continue;
                }
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
#else
            (void)py;
#endif
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

#if PERF_ENABLE_SHOT
static void dump_shadow(ReplyChannel channel)
{
    static const char hex[] = "0123456789abcdef";
    char line[129];
    size_t index = 0;

    send_reply(channel, "SHOT BEGIN 172 320 4");
    while(index < sizeof(s_shadow)) {
        size_t count = 0;
        while(count < 128 && index < sizeof(s_shadow)) {
            uint8_t value = s_shadow[index++];
            line[count++] = hex[value >> 4];
            line[count++] = hex[value & 0x0F];
        }
        line[count] = '\0';
        send_reply(channel, line);
    }
    send_reply(channel, "SHOT END");
}
#endif

static void handle_line(const char * line, size_t len, ReplyChannel channel)
{
    if(line[0] == '\x01') {
        send_reply(channel, "@PERF ERR seq=0 code=too-long");
        return;
    }

    if(perf_parse_starts_with_perf(line, len)) {
        perf_parse_result_t result = perf_monitor_ingest(line, len);
        char reply[96];
        switch(result) {
            case PERF_PARSE_OK:
                snprintf(reply, sizeof(reply), "@PERF OK seq=%u",
                         (unsigned)perf_monitor_last_seq());
                break;
            case PERF_PARSE_HELLO:
                snprintf(reply, sizeof(reply),
                         "@PERF READY v=1 bars=16 mtu=%u",
                         (unsigned)ble_uart_mtu());
                break;
            case PERF_PARSE_PING:
                strcpy(reply, "@PERF PONG");
                break;
            case PERF_PARSE_DEMO:
                strcpy(reply, "@PERF OK DEMO");
                break;
            case PERF_PARSE_LIVE:
                strcpy(reply, "@PERF OK LIVE");
                break;
            case PERF_PARSE_PORTRAIT:
                s_layout = "portrait";
                strcpy(reply, "@PERF OK PORTRAIT");
                break;
            case PERF_PARSE_LANDSCAPE:
                s_layout = "landscape";
                strcpy(reply, "@PERF OK LANDSCAPE");
                break;
            case PERF_PARSE_NOT_PERF:
            case PERF_PARSE_EMPTY:
                return;
            case PERF_PARSE_TOO_LONG:
                strcpy(reply, "@PERF ERR seq=0 code=too-long");
                break;
            default:
                snprintf(reply, sizeof(reply), "@PERF ERR seq=%u code=%s",
                         (unsigned)perf_monitor_last_seq(),
                         perf_parse_result_name(result));
                break;
        }
        send_reply(channel, reply);
        return;
    }

    if(strcmp(line, "pages") == 0) {
        send_reply(channel, "@PAGES portrait,landscape");
        return;
    }
    if(strcmp(line, "state") == 0) {
        char reply[32];
        snprintf(reply, sizeof(reply), "@STATE page=%s", s_layout);
        send_reply(channel, reply);
        return;
    }
    if(strcmp(line, "ping") == 0) {
        send_reply(channel, "@PONG");
        return;
    }
    if(strncmp(line, "page ", 5) == 0) {
        const char * arg = line + 5;
        const char * next = NULL;
        if(strcmp(arg, "portrait") == 0) {
            next = "portrait";
        }
        else if(strcmp(arg, "landscape") == 0) {
            next = "landscape";
        }
        else if(strcmp(arg, "next") == 0 || strcmp(arg, "prev") == 0) {
            next = strcmp(s_layout, "portrait") == 0 ? "landscape"
                                                     : "portrait";
        }
        else {
            char reply[64];
            snprintf(reply, sizeof(reply), "@ERR PAGE unknown=%s", arg);
            send_reply(channel, reply);
            return;
        }
        if(strcmp(next, s_layout) != 0) {
            const char * command = strcmp(next, "portrait") == 0
                                       ? "PERF PORTRAIT"
                                       : "PERF LANDSCAPE";
            perf_monitor_ingest(command, strlen(command));
            s_layout = next;
        }
        char reply[32];
        snprintf(reply, sizeof(reply), "@OK PAGE %s", s_layout);
        send_reply(channel, reply);
        return;
    }
#if PERF_ENABLE_SHOT
    if(strcmp(line, "SHOT") == 0) {
        dump_shadow(channel);
        return;
    }
#endif
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
    Serial.printf("[boot] app=perf_monitor heap=%u\n", ESP.getFreeHeap());
    ble_uart_begin(BLE_UART_DEVICE_NAME);
    Serial.printf("[boot] heap after ble=%u\n", ESP.getFreeHeap());
}

void loop()
{
    static char line[PERF_PROTOCOL_MAX_LINE + 1];
    static size_t line_len = 0;
    static bool overflow = false;

    while(Serial.available() > 0) {
        int value = Serial.read();
        if(value < 0) {
            break;
        }
        char ch = (char)value;
        if(ch == '\r') {
            continue;
        }
        if(ch == '\n') {
            if(overflow) {
                send_reply(REPLY_USB, "@PERF ERR seq=0 code=too-long");
            }
            else if(line_len > 0) {
                line[line_len] = '\0';
                handle_line(line, line_len, REPLY_USB);
            }
            line_len = 0;
            overflow = false;
            continue;
        }
        if(overflow) {
            continue;
        }
        if(line_len < PERF_PROTOCOL_MAX_LINE) {
            line[line_len++] = ch;
        }
        else {
            line_len = 0;
            overflow = true;
        }
    }

    char ble_line[BLE_UART_MAX_LINE + 1];
    while(ble_uart_pop_line(ble_line, sizeof(ble_line))) {
        handle_line(ble_line, strlen(ble_line), REPLY_BLE);
    }

    ble_uart_poll();
    lv_timer_handler();
    delay(5);
}
