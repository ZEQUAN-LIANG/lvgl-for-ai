#ifndef PERF_MONITOR_H
#define PERF_MONITOR_H

#include "lvgl.h"

#include "perf_protocol.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

void perf_monitor_create(void);

/*
 * Parse and apply one serial line; the parser is pure, only this call touches
 * widgets.  Call from the LVGL task, or wrap in lvgl_port_lock() /
 * lvgl_port_unlock().  The firmware shell owns the UART/USB-Serial read loop
 * and may route every complete line here: non-PERF lines return
 * PERF_PARSE_NOT_PERF.  PORTRAIT / LANDSCAPE rebuild the layout, and landscape
 * also switches the display rotation.
 */
perf_parse_result_t perf_monitor_ingest(const char * line, size_t len);

uint16_t perf_monitor_last_seq(void);
bool perf_monitor_is_live(void);

#endif

#endif /* PERF_MONITOR_H */
