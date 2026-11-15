/**
 * @file frame_diff.h
 * ``frame_diffs.ndjson`` and optional ``reference_diffs.ndjson`` writers
 * (schema ``lvgl-verify-loop-frame-diffs-v1``).
 *
 * A pixel counts as changed when any RGB channel differs by more than
 * ``threshold`` (0..255, default 10). ``bbox`` is the union rectangle of all
 * changed pixels and is ``null`` when nothing changed. ``changed_ratio`` is
 * ``changed_px / (width * height)``; ``max_delta`` is the largest RGB channel
 * difference in the whole frame divided by 255.
 *
 * Previous-frame mode skips the first retained frame; later frames compare
 * against the previous retained frame. When changed-only recording skips
 * identical framebuffers, no row is written for those ticks, so prev_frame_no
 * stays on the last saved frame. Reference mode writes a row for every
 * retained frame and compares against the caller-supplied reference pixels.
 *
 * Both modes use ``frame_analysis`` so strict RGB equality and threshold
 * statistics come from one traversal.
 */

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

/**
 * Open frame_diffs.ndjson under session_dir. record=false disables writing.
 * Returns false when the file cannot be written or memory is unavailable.
 */
bool frame_diff_open_previous(frame_diff_t * diff, const char * session_dir,
                              uint32_t width, uint32_t height, int threshold,
                              bool record);

/**
 * Open reference_diffs.ndjson under session_dir. ``reference`` is borrowed
 * XRGB8888 pixels with the same dimensions as the framebuffer.
 */
bool frame_diff_open_reference(frame_diff_t * diff, const char * session_dir,
                               const uint8_t * reference, uint32_t width,
                               uint32_t height, int threshold, bool record);

/**
 * Compare against the previous recorded frame; the first call only stores it.
 * ``analysis`` may carry a result the caller already computed against that
 * same previous frame (the session shares the changed-only traversal); when
 * it is NULL the diff computes the analysis from its own previous buffer.
 */
void frame_diff_record_previous(frame_diff_t * diff, const uint8_t * frame,
                                long frame_no, uint32_t t_ms,
                                const frame_analysis_t * analysis);

/** Compare ``frame`` against the reference pixels for every call. */
void frame_diff_record_reference(frame_diff_t * diff, const uint8_t * frame,
                                 long frame_no, uint32_t t_ms);

void frame_diff_close(frame_diff_t * diff);

#ifdef __cplusplus
}
#endif

#endif
