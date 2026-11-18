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
 * Parse and apply one serial line.  Call this from the LVGL task, or wrap the
 * call in the target's lvgl_port_lock()/lvgl_port_unlock().  The parser itself
 * is pure; this function only touches widgets.
 *
 * The firmware shell owns the UART/USB-Serial read loop and line assembly.
 * It can route every complete line through perf_monitor_ingest(): non-PERF
 * lines return PERF_PARSE_NOT_PERF and are ignored.
 *
 * PERF PORTRAIT / PERF LANDSCAPE rebuild the layout; on a 172x320 panel the
 * landscape command also switches the LVGL display rotation.
 */
perf_parse_result_t perf_monitor_ingest(const char * line, size_t len);

uint16_t perf_monitor_last_seq(void);
bool perf_monitor_is_live(void);

#endif

#endif /* PERF_MONITOR_H */
