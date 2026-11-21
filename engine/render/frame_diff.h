#ifndef FRAME_DIFF_H
#define FRAME_DIFF_H

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "frame_analysis.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    FILE * out;
    bool enabled;
    bool reference_mode;
    uint8_t * previous;
    const uint8_t * reference;
    uint32_t width;
    uint32_t height;
    int threshold;
    long prev_frame_no;
    bool has_previous;
} frame_diff_t;

bool frame_diff_open_previous(frame_diff_t * diff, const char * session_dir,
                              uint32_t width, uint32_t height, int threshold,
                              bool record);

bool frame_diff_open_reference(frame_diff_t * diff, const char * session_dir,
                               const uint8_t * reference, uint32_t width,
                               uint32_t height, int threshold, bool record);

void frame_diff_record_previous(frame_diff_t * diff, const uint8_t * frame,
                                long frame_no, uint32_t t_ms,
                                const frame_analysis_t * analysis);

void frame_diff_record_reference(frame_diff_t * diff, const uint8_t * frame,
                                 long frame_no, uint32_t t_ms);

void frame_diff_close(frame_diff_t * diff);

#ifdef __cplusplus
}
#endif

#endif
