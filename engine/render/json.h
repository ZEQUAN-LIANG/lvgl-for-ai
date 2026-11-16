#ifndef JSON_H
#define JSON_H

#include <stddef.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Write ``value`` as a quoted JSON string. NULL is written as "". */
void json_write_string(FILE * out, const char * value);

/**
 * Quote ``value`` into ``out``. Returns 0 on success, -1 when the buffer is
 * too small. The result includes the surrounding double quotes.
 */
int json_quote(const char * value, char * out, size_t out_size);

#ifdef __cplusplus
}
#endif

#endif
