#include "protocol.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

static char * skip_spaces(char * text)
{
    while(*text != '\0' && isspace((unsigned char)*text)) text++;
    return text;
}

bool protocol_parse(char * line, command_t * command)
{
    if(line == NULL || command == NULL) return false;

    size_t length = strlen(line);
    while(length > 0 &&
          (line[length - 1u] == '\n' || line[length - 1u] == '\r')) {
        line[--length] = '\0';
    }

    char * cursor = skip_spaces(line);
    if(*cursor == '\0') return false;

    char * end = NULL;
    long seq = strtol(cursor, &end, 10);
    if(end == cursor || seq < 0) return false;

    cursor = skip_spaces(end);
    if(*cursor == '\0') return false;

    char * verb_start = cursor;
    while(*cursor != '\0' && !isspace((unsigned char)*cursor)) cursor++;
    size_t verb_length = (size_t)(cursor - verb_start);
    if(verb_length == 0 || verb_length >= sizeof(command->verb)) return false;
    memcpy(command->verb, verb_start, verb_length);
    command->verb[verb_length] = '\0';

    command->seq = seq;
    command->args = skip_spaces(cursor);
    return true;
}

void protocol_ready(FILE * out, const char * protocol,
                    const char * lvgl_version, const char * lvgl_src,
                    unsigned width, unsigned height, const char * mode,
                    const char * adapter, long frames, long max_frames,
                    bool truncated, const char * capabilities_json)
{
    fprintf(out,
            "{\"ready\":true,\"seq\":0,\"protocol\":\"%s\",\"lvgl\":\"%s\","
            "\"lvgl_src\":\"%s\","
            "\"display\":{\"width\":%u,\"height\":%u,\"format\":\"XRGB8888\"},"
            "\"mode\":\"%s\",\"inputs\":[\"real\",\"virtual\"],"
            "\"capabilities\":%s,\"adapter\":\"%s\",\"frames\":%ld,"
            "\"max_frames\":%ld,\"truncated\":%s}\n",
            protocol, lvgl_version, lvgl_src != NULL ? lvgl_src : "", width,
            height, mode, capabilities_json != NULL ? capabilities_json : "[]",
            adapter != NULL ? adapter : "unknown", frames, max_frames,
            truncated ? "true" : "false");
    fflush(out);
}

void protocol_reply_ok(FILE * out, long seq, const char * extra_fields)
{
    fprintf(out,
            "{\"protocol\":\"lvgl-ai-engine-v1\",\"seq\":%ld,\"ok\":true%s}\n",
            seq, extra_fields != NULL ? extra_fields : "");
    fflush(out);
}

void protocol_reply_error(FILE * out, long seq, const char * code,
                          const char * message)
{
    fprintf(out,
            "{\"protocol\":\"lvgl-ai-engine-v1\",\"seq\":%ld,\"ok\":false,"
            "\"error\":\"%s\",\"message\":\"%s\"}\n",
            seq, code != NULL ? code : "error", message != NULL ? message : "");
    fflush(out);
}
