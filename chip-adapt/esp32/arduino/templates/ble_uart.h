#ifndef BLE_UART_H
#define BLE_UART_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define BLE_UART_MAX_LINE      320
#define BLE_UART_OVERFLOW_LINE "\x01"

#ifndef BLE_UART_DEVICE_NAME
#define BLE_UART_DEVICE_NAME "LVGL-C6-PERF"
#endif

void ble_uart_begin(const char * name);
bool ble_uart_pop_line(char * out, size_t cap);
void ble_uart_send(const char * data, size_t len);
void ble_uart_send_line(const char * text);
bool ble_uart_connected(void);
uint16_t ble_uart_mtu(void);
void ble_uart_poll(void);

#endif
