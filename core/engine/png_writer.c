#include "png_writer.h"

#include <limits.h>
#include <png.h>
#include <stddef.h>
// cppcheck-suppress misra-c2012-21.6
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// cppcheck-suppress misra-c2012-8.7
int png_writer_write_xrgb(const uint8_t * xrgb, uint32_t width,
                          uint32_t height, const char * path)
{
    int result = -1;
    if((xrgb != NULL) && (path != NULL) && (width != 0u) && (height != 0u) &&
       ((size_t)width <= (((size_t)INT32_MAX) / 3u))) {
        size_t pixel_count = (size_t)width * (size_t)height;
        if(pixel_count <= (SIZE_MAX / 3u)) {
            // cppcheck-suppress misra-c2012-21.3
            unsigned char * rgb = (unsigned char *)malloc(pixel_count * 3u);
            if(rgb != NULL) {
                for(size_t i = 0u; i < pixel_count; i++) {
                    rgb[(i * 3u) + 0u] = xrgb[(i * 4u) + 2u];
                    rgb[(i * 3u) + 1u] = xrgb[(i * 4u) + 1u];
                    rgb[(i * 3u) + 2u] = xrgb[(i * 4u) + 0u];
                }
                png_image image;
                // cppcheck-suppress misra-c2012-17.7
                memset(&image, 0, sizeof(image));
                image.version = PNG_IMAGE_VERSION;
                image.width = width;
                image.height = height;
                image.format = PNG_FORMAT_RGB;
                image.flags = PNG_IMAGE_FLAG_FAST;
                // cppcheck-suppress misra-c2012-17.3
                if(png_image_write_to_file(&image, path, 0, rgb,
                                           (png_int_32)((size_t)width * 3u),
                                           NULL) != 0) {
                    result = 0;
                }
                else {
                    // cppcheck-suppress misra-c2012-17.7
                    fprintf(stderr, "[engine] cannot write %s: %s\n", path,
                            image.message);
                }
                // cppcheck-suppress misra-c2012-21.3
                free(rgb);
            }
            else {
                // cppcheck-suppress misra-c2012-17.7
                fprintf(stderr, "[engine] cannot allocate the PNG pixel buffer\n");
            }
        }
        else {
            // cppcheck-suppress misra-c2012-17.7
            fprintf(stderr, "[engine] PNG frame is too large: %ux%u\n", width,
                    height);
        }
    }
    else {
        if((xrgb != NULL) && (path != NULL)) {
            // cppcheck-suppress misra-c2012-17.7
            fprintf(stderr, "[engine] invalid PNG size: %ux%u\n", width, height);
        }
        result = -1;
    }
    return result;
}
