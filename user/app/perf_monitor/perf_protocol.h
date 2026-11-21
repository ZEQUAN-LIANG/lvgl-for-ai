#ifndef PERF_PROTOCOL_H
#define PERF_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PERF_PROTOCOL_VERSION  1
#define PERF_PROTOCOL_MAX_LINE 320
#define PERF_PROTOCOL_BARS     16
#define PERF_PROTOCOL_HOST_MAX 12

#define PERF_GPU_UNKNOWN  0xFF
#define PERF_TEMP_UNKNOWN ((int16_t)-32768)
#define PERF_PING_UNKNOWN 0xFFFF
#define PERF_TIME_UNKNOWN 0xFFFF

typedef struct {
    uint16_t seq;
    uint8_t cpu;
    uint8_t gpu;
    uint32_t mem_mb;
    uint32_t mem_total_mb;
    uint16_t freq_mhz;
    int16_t temp_c;
    int16_t gpu_temp_c;
    uint32_t down_kib_s;
    uint32_t up_kib_s;
    uint16_t ping_ms;
    uint16_t hhmm;
    uint8_t thread_count;
    uint8_t bars[PERF_PROTOCOL_BARS];
    char host[PERF_PROTOCOL_HOST_MAX + 1];
} perf_sample_t;

typedef enum {
    PERF_PARSE_OK = 0,
    PERF_PARSE_NOT_PERF,
    PERF_PARSE_EMPTY,
    PERF_PARSE_TOO_LONG,
    PERF_PARSE_BAD_VERSION,
    PERF_PARSE_MISSING_FIELD,
    PERF_PARSE_BAD_FIELD,
    PERF_PARSE_BAD_VALUE,
    PERF_PARSE_HELLO,
    PERF_PARSE_DEMO,
    PERF_PARSE_LIVE,
    PERF_PARSE_PING,
    PERF_PARSE_PORTRAIT,
    PERF_PARSE_LANDSCAPE
} perf_parse_result_t;

void perf_sample_init(perf_sample_t * sample);
perf_parse_result_t perf_protocol_parse(const char * line, size_t len,
                                        perf_sample_t * sample);
const char * perf_parse_result_name(perf_parse_result_t result);
bool perf_parse_starts_with_perf(const char * line, size_t len);

#ifdef __cplusplus
}
#endif

#endif
