#include "perf_protocol.h"

#include <ctype.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#define PERF_MAX_MEM_MB   4194304U
#define PERF_MAX_FREQ_MHZ 100000U
#define PERF_MAX_NET_KIB  4194304U

void perf_sample_init(perf_sample_t * sample)
{
    if(sample == NULL) return;

    memset(sample, 0, sizeof(*sample));
    sample->gpu = PERF_GPU_UNKNOWN;
    sample->temp_c = PERF_TEMP_UNKNOWN;
    sample->gpu_temp_c = PERF_TEMP_UNKNOWN;
    sample->ping_ms = PERF_PING_UNKNOWN;
    sample->hhmm = PERF_TIME_UNKNOWN;
    sample->thread_count = PERF_PROTOCOL_BARS;
    memcpy(sample->host, "DESKTOP", 8);
}

static bool parse_u32(const char * text, uint32_t min, uint32_t max,
                      uint32_t * out)
{
    char * end = NULL;
    unsigned long value;

    if(text == NULL || text[0] == '\0' || out == NULL) return false;
    if(text[0] == '-') return false;

    errno = 0;
    value = strtoul(text, &end, 10);
    if(errno != 0 || end == text || *end != '\0') return false;
    if(value < min || value > max) return false;

    *out = (uint32_t)value;
    return true;
}

static bool parse_i16(const char * text, int16_t min, int16_t max,
                      int16_t * out)
{
    char * end = NULL;
    long value;

    if(text == NULL || text[0] == '\0' || out == NULL) return false;

    errno = 0;
    value = strtol(text, &end, 10);
    if(errno != 0 || end == text || *end != '\0') return false;
    if(value < min || value > max) return false;

    *out = (int16_t)value;
    return true;
}

static bool parse_bars(const char * text, uint8_t bars[PERF_PROTOCOL_BARS])
{
    const char * cursor = text;
    size_t index = 0;

    memset(bars, 0, PERF_PROTOCOL_BARS);
    if(text == NULL || text[0] == '\0') return false;

    while(*cursor != '\0') {
        char * end = NULL;
        unsigned long value;

        if(index >= PERF_PROTOCOL_BARS) return false;
        if(*cursor == ',') return false;

        errno = 0;
        value = strtoul(cursor, &end, 10);
        if(errno != 0 || end == cursor || value > 100) return false;
        bars[index++] = (uint8_t)value;

        if(*end == '\0') break;
        if(*end != ',') return false;
        cursor = end + 1;
        if(*cursor == '\0') return false;
    }

    return index > 0;
}

static void copy_host(const char * text, char host[PERF_PROTOCOL_HOST_MAX + 1])
{
    size_t index = 0;

    if(text == NULL) text = "";
    while(text[index] != '\0' && index < PERF_PROTOCOL_HOST_MAX) {
        unsigned char ch = (unsigned char)text[index];
        if(!isalnum(ch) && ch != '-' && ch != '_' && ch != '.') break;
        host[index] = (char)ch;
        index++;
    }
    host[index] = '\0';
    if(index == 0) memcpy(host, "HOST", 5);
}

bool perf_parse_starts_with_perf(const char * line, size_t len)
{
    size_t index = 0;

    if(line == NULL) return false;
    while(index < len && (line[index] == ' ' || line[index] == '\t')) index++;
    if(len - index < 4) return false;
    if(memcmp(line + index, "PERF", 4) != 0) return false;
    if(len - index == 4) return true;
    return line[index + 4] == ' ' || line[index + 4] == '\t';
}

const char * perf_parse_result_name(perf_parse_result_t result)
{
    switch(result) {
        case PERF_PARSE_OK:
            return "ok";
        case PERF_PARSE_NOT_PERF:
            return "not-perf";
        case PERF_PARSE_EMPTY:
            return "empty";
        case PERF_PARSE_TOO_LONG:
            return "too-long";
        case PERF_PARSE_BAD_VERSION:
            return "bad-version";
        case PERF_PARSE_MISSING_FIELD:
            return "missing-field";
        case PERF_PARSE_BAD_FIELD:
            return "bad-field";
        case PERF_PARSE_BAD_VALUE:
            return "bad-value";
        case PERF_PARSE_HELLO:
            return "hello";
        case PERF_PARSE_DEMO:
            return "demo";
        case PERF_PARSE_LIVE:
            return "live";
        case PERF_PARSE_PING:
            return "ping";
        case PERF_PARSE_PORTRAIT:
            return "portrait";
        case PERF_PARSE_LANDSCAPE:
            return "landscape";
        default:
            return "unknown";
    }
}

perf_parse_result_t perf_protocol_parse(const char * line, size_t len,
                                        perf_sample_t * sample)
{
    char buffer[PERF_PROTOCOL_MAX_LINE + 1];
    char * cursor;
    size_t start = 0;
    size_t end;
    bool have_version = false;
    bool have_seq = false;
    bool have_cpu = false;

    if(sample == NULL) return PERF_PARSE_BAD_FIELD;
    perf_sample_init(sample);

    if(line == NULL) return PERF_PARSE_EMPTY;
    if(len > PERF_PROTOCOL_MAX_LINE) return PERF_PARSE_TOO_LONG;

    while(start < len && (line[start] == ' ' || line[start] == '\t')) start++;
    end = len;
    while(end > start && (line[end - 1] == ' ' || line[end - 1] == '\t' ||
                          line[end - 1] == '\r' || line[end - 1] == '\n')) {
        end--;
    }
    if(end == start) return PERF_PARSE_EMPTY;
    if(!perf_parse_starts_with_perf(line + start, end - start)) {
        return PERF_PARSE_NOT_PERF;
    }

    memcpy(buffer, line + start, end - start);
    buffer[end - start] = '\0';

    cursor = buffer + 4;
    while(*cursor == ' ' || *cursor == '\t') cursor++;
    if(*cursor == '\0') return PERF_PARSE_BAD_FIELD;

    if(strcmp(cursor, "HELLO") == 0) return PERF_PARSE_HELLO;
    if(strcmp(cursor, "DEMO") == 0) return PERF_PARSE_DEMO;
    if(strcmp(cursor, "LIVE") == 0) return PERF_PARSE_LIVE;
    if(strcmp(cursor, "PING") == 0) return PERF_PARSE_PING;
    if(strcmp(cursor, "PORTRAIT") == 0) return PERF_PARSE_PORTRAIT;
    if(strcmp(cursor, "LANDSCAPE") == 0) return PERF_PARSE_LANDSCAPE;

    while(*cursor != '\0') {
        char * token;
        char * next;
        char * equals;
        const char * key;
        const char * value;

        while(*cursor == ' ' || *cursor == '\t') cursor++;
        if(*cursor == '\0') break;

        token = cursor;
        next = strchr(cursor, ' ');
        if(next == NULL) next = strchr(cursor, '\t');
        if(next != NULL) {
            *next = '\0';
            cursor = next + 1;
        }
        else {
            cursor = token + strlen(token);
        }

        equals = strchr(token, '=');
        if(equals == NULL || equals == token || equals[1] == '\0') {
            return equals == NULL ? PERF_PARSE_BAD_FIELD : PERF_PARSE_BAD_VALUE;
        }
        *equals = '\0';
        key = token;
        value = equals + 1;

        if(strcmp(key, "v") == 0) {
            uint32_t version;
            if(!parse_u32(value, PERF_PROTOCOL_VERSION, PERF_PROTOCOL_VERSION,
                          &version)) {
                return PERF_PARSE_BAD_VERSION;
            }
            have_version = true;
        }
        else if(strcmp(key, "seq") == 0) {
            uint32_t parsed;
            if(!parse_u32(value, 0, 65535, &parsed))
                return PERF_PARSE_BAD_VALUE;
            sample->seq = (uint16_t)parsed;
            have_seq = true;
        }
        else if(strcmp(key, "cpu") == 0) {
            uint32_t parsed;
            if(!parse_u32(value, 0, 100, &parsed)) return PERF_PARSE_BAD_VALUE;
            sample->cpu = (uint8_t)parsed;
            have_cpu = true;
        }
        else if(strcmp(key, "gpu") == 0) {
            uint32_t parsed;
            if(!parse_u32(value, 0, 100, &parsed)) return PERF_PARSE_BAD_VALUE;
            sample->gpu = (uint8_t)parsed;
        }
        else if(strcmp(key, "mem") == 0) {
            if(!parse_u32(value, 0, PERF_MAX_MEM_MB, &sample->mem_mb)) {
                return PERF_PARSE_BAD_VALUE;
            }
        }
        else if(strcmp(key, "memt") == 0) {
            if(!parse_u32(value, 0, PERF_MAX_MEM_MB, &sample->mem_total_mb)) {
                return PERF_PARSE_BAD_VALUE;
            }
        }
        else if(strcmp(key, "freq") == 0) {
            uint32_t parsed;
            if(!parse_u32(value, 0, PERF_MAX_FREQ_MHZ, &parsed)) {
                return PERF_PARSE_BAD_VALUE;
            }
            sample->freq_mhz = (uint16_t)parsed;
        }
        else if(strcmp(key, "temp") == 0) {
            if(!parse_i16(value, -1, 150, &sample->temp_c)) {
                return PERF_PARSE_BAD_VALUE;
            }
        }
        else if(strcmp(key, "gtemp") == 0) {
            if(!parse_i16(value, -1, 150, &sample->gpu_temp_c)) {
                return PERF_PARSE_BAD_VALUE;
            }
        }
        else if(strcmp(key, "down") == 0) {
            if(!parse_u32(value, 0, PERF_MAX_NET_KIB, &sample->down_kib_s)) {
                return PERF_PARSE_BAD_VALUE;
            }
        }
        else if(strcmp(key, "up") == 0) {
            if(!parse_u32(value, 0, PERF_MAX_NET_KIB, &sample->up_kib_s)) {
                return PERF_PARSE_BAD_VALUE;
            }
        }
        else if(strcmp(key, "ping") == 0) {
            uint32_t parsed;
            if(!parse_u32(value, 0, 60000, &parsed))
                return PERF_PARSE_BAD_VALUE;
            sample->ping_ms = (uint16_t)parsed;
        }
        else if(strcmp(key, "time") == 0) {
            uint32_t parsed;
            if(!parse_u32(value, 0, 2359, &parsed)) return PERF_PARSE_BAD_VALUE;
            if(parsed % 100 > 59) return PERF_PARSE_BAD_VALUE;
            sample->hhmm = (uint16_t)parsed;
        }
        else if(strcmp(key, "host") == 0) {
            copy_host(value, sample->host);
        }
        else if(strcmp(key, "th") == 0) {
            if(!parse_bars(value, sample->bars)) return PERF_PARSE_BAD_VALUE;
        }
        else if(strcmp(key, "thn") == 0) {
            uint32_t parsed;
            if(!parse_u32(value, 1, PERF_PROTOCOL_BARS, &parsed)) {
                return PERF_PARSE_BAD_VALUE;
            }
            sample->thread_count = (uint8_t)parsed;
        }
    }

    if(!have_version) return PERF_PARSE_BAD_VERSION;
    if(!have_seq || !have_cpu) return PERF_PARSE_MISSING_FIELD;
    return PERF_PARSE_OK;
}
