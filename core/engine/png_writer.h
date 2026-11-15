#ifndef PNG_WRITER_H
#define PNG_WRITER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Encode ``xrgb`` (width * height * 4 bytes, B, G, R, X) as an 8-bit RGB PNG.
 * Returns 0 on success, -1 when the buffer or file cannot be written.
 */
int png_writer_write_xrgb(const uint8_t * xrgb,
                          uint32_t width,
                          uint32_t height,
                          const char * path);

#ifdef __cplusplus
}
#endif

#endif
