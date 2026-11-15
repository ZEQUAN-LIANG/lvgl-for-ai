#include "frame_analysis.h"

#include <string.h>

void frame_analysis_compare(const uint8_t * previous, const uint8_t * current,
                            uint32_t width, uint32_t height, int threshold,
                            frame_analysis_t * analysis)
{
    if(analysis == NULL) return;

    memset(analysis, 0, sizeof(*analysis));
    analysis->rgb_equal = true;
    analysis->min_x = width;
    analysis->min_y = height;

    if(previous == NULL || current == NULL) return;

    size_t pixel_count = (size_t)width * height;
    for(size_t i = 0; i < pixel_count; i++) {
        const uint8_t * left = previous + i * 4u;
        const uint8_t * right = current + i * 4u;
        unsigned delta = 0;
        for(size_t channel = 0; channel < 3u; channel++) {
            int difference = (int)left[channel] - (int)right[channel];
            unsigned magnitude =
                (unsigned)(difference < 0 ? -difference : difference);
            if(magnitude > delta) delta = magnitude;
        }
        if(delta != 0) analysis->rgb_equal = false;
        if(delta > analysis->max_delta) analysis->max_delta = delta;
        if((int)delta > threshold) {
            uint32_t x = (uint32_t)(i % width);
            uint32_t y = (uint32_t)(i / width);
            analysis->changed_px++;
            if(x < analysis->min_x) analysis->min_x = x;
            if(y < analysis->min_y) analysis->min_y = y;
            if(x > analysis->max_x) analysis->max_x = x;
            if(y > analysis->max_y) analysis->max_y = y;
        }
    }
}
