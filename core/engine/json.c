#include "json.h"

#include <stdint.h>
#include <string.h>

static const char * json_escape(char c, char * scratch)
{
    switch(c) {
        case '"':
            return "\\\"";
        case '\\':
            return "\\\\";
        case '\b':
            return "\\b";
        case '\f':
            return "\\f";
        case '\n':
            return "\\n";
        case '\r':
            return "\\r";
        case '\t':
            return "\\t";
        default:
            break;
    }
    if((unsigned char)c < 0x20u) {
        static const char hex[] = "0123456789abcdef";
        scratch[0] = '\\';
        scratch[1] = 'u';
        scratch[2] = '0';
        scratch[3] = '0';
        scratch[4] = hex[((unsigned char)c >> 4) & 0xFu];
        scratch[5] = hex[(unsigned char)c & 0xFu];
        scratch[6] = '\0';
        return scratch;
    }
    return NULL;
}

void json_write_string(FILE * out, const char * value)
{
    if(out == NULL) return;
    fputc('"', out);
    if(value != NULL) {
        for(const unsigned char * cursor = (const unsigned char *)value;
            *cursor != '\0'; cursor++) {
            char scratch[8];
            const char * escaped = json_escape((char)*cursor, scratch);
            if(escaped != NULL) {
                fputs(escaped, out);
            }
            else {
                fputc((int)*cursor, out);
            }
        }
    }
    fputc('"', out);
}

int json_quote(const char * value, char * out, size_t out_size)
{
    if(out == NULL || out_size == 0) return -1;
    size_t used = 0;
    if(used + 1u >= out_size) return -1;
    out[used++] = '"';
    if(value != NULL) {
        for(const unsigned char * cursor = (const unsigned char *)value;
            *cursor != '\0'; cursor++) {
            char scratch[8];
            const char * escaped = json_escape((char)*cursor, scratch);
            const char * source =
                escaped != NULL ? escaped : (const char *)cursor;
            size_t length = escaped != NULL ? strlen(escaped) : 1u;
            if(used + length + 2u > out_size) return -1;
            for(size_t i = 0; i < length; i++) out[used++] = source[i];
        }
    }
    if(used + 1u >= out_size) return -1;
    out[used++] = '"';
    out[used] = '\0';
    return 0;
}
