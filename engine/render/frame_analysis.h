/**
 * One traversal that answers both questions the engine asks about a pair of
 * XRGB8888 framebuffers: strict RGB equality (changed-only recording may skip
 * a frame only when every RGB byte matches; alpha is ignored) and threshold
 * statistics for ``frame_diffs.ndjson`` (a pixel counts as changed when any
 * RGB channel differs by more than ``threshold``, 0..255, default 10).
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
     * Union rectangle of changed pixels. With no changed pixel the sentinels
     * are min_x == width, min_y == height, max_x == max_y == 0.
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
