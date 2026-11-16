/**
 * @file frame_analysis.h
 * One traversal answering both questions the engine asks about a pair of
 * XRGB8888 framebuffers.
 *
 * The engine keeps two deliberately different definitions:
 *
 * - **strict RGB equality** decides whether changed-only recording may skip
 *   a frame. Alpha is not evidence and is ignored; every red, green and blue
 *   byte must match.
 * - **threshold statistics** feed ``frame_diffs.ndjson``. A pixel counts as
 *   changed when any RGB channel differs by more than ``threshold`` (0..255,
 *   default 10); ``max_delta`` still reports the largest channel difference
 *   in the whole frame, so sub-threshold anti-aliasing remains visible there.
 *
 * ``frame_analysis_compare`` evaluates both in a single pass so callers do
 * not scan the frame once per definition.
 */

#ifndef FRAME_ANALYSIS_H
#define FRAME_ANALYSIS_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    /** True when every RGB channel of every pixel is identical. */
    bool rgb_equal;
    /** Pixels whose largest RGB channel delta is greater than the threshold. */
    long changed_px;
    /**
     * Union rectangle of changed pixels. When ``changed_px`` is 0 the values
     * are initialised to ``min_x == width``, ``min_y == height`` and
     * ``max_x == max_y == 0``; callers write ``bbox:null`` in that case.
     */
    uint32_t min_x;
    uint32_t min_y;
    uint32_t max_x;
    uint32_t max_y;
    /** Largest RGB channel difference in the whole frame (0..255). */
    unsigned max_delta;
} frame_analysis_t;

/**
 * Compare two frames with the same dimensions. ``previous`` and ``current``
 * are XRGB8888 pixels, ``width * height * 4`` bytes each. ``threshold`` is
 * the inclusive limit: a delta equal to the threshold is not counted as
 * changed. ``analysis`` receives the combined result.
 */
void frame_analysis_compare(const uint8_t * previous, const uint8_t * current,
                            uint32_t width, uint32_t height, int threshold,
                            frame_analysis_t * analysis);

#ifdef __cplusplus
}
#endif

#endif
