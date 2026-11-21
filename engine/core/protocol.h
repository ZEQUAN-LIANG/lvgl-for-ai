#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdbool.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    long seq;
    char verb[32];
    const char * args;
} command_t;

bool protocol_parse(char * line, command_t * command);

void protocol_ready(FILE * out, const char * protocol,
                    const char * lvgl_version, const char * lvgl_src,
                    unsigned width, unsigned height, const char * mode,
                    const char * adapter, long frames, long max_frames,
                    bool truncated, const char * capabilities_json);

void protocol_reply_ok(FILE * out, long seq, const char * extra_fields);
void protocol_reply_error(FILE * out, long seq, const char * code,
                          const char * message);

#ifdef __cplusplus
}
#endif

#endif
