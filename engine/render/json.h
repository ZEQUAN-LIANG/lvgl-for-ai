#ifndef JSON_H
#define JSON_H

#include <stddef.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

void json_write_string(FILE * out, const char * value);

int json_quote(const char * value, char * out, size_t out_size);

#ifdef __cplusplus
}
#endif

#endif
