#ifndef PNG_WRITER_H
#define PNG_WRITER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int png_writer_write_xrgb(const uint8_t * xrgb, uint32_t width, uint32_t height,
                          const char * path);

#ifdef __cplusplus
}
#endif

#endif
