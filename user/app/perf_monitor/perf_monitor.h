#ifndef PERF_MONITOR_H
#define PERF_MONITOR_H

#include "lvgl.h"

#include "perf_protocol.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

void perf_monitor_create(void);

perf_parse_result_t perf_monitor_ingest(const char * line, size_t len);

uint16_t perf_monitor_last_seq(void);
bool perf_monitor_is_live(void);

#endif

#endif
