#ifndef FRAME_ANALYSIS_H
#define FRAME_ANALYSIS_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool rgb_equal;
    long changed_px;
    uint32_t min_x;
    uint32_t min_y;
    uint32_t max_x;
    uint32_t max_y;
    unsigned max_delta;
} frame_analysis_t;

void frame_analysis_compare(const uint8_t * previous, const uint8_t * current,
                            uint32_t width, uint32_t height, int threshold,
                            frame_analysis_t * analysis);

#ifdef __cplusplus
}
#endif

#endif
