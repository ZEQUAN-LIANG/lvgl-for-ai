/**
 * @file timeline.h
 * ``timeline.ndjson`` writer (schema ``lvgl-verify-loop-timeline-v1``).
 *
 * Row types: frame / input / wait / mark / snapshot / end. One JSON object
 * per line; the engine records what happened, it never judges the result.
 */

#ifndef TIMELINE_H
#define TIMELINE_H

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    FILE * out;
    bool enabled;
} timeline_t;

/**
 * Open timeline.ndjson under session_dir. record=false disables writing.
 * Returns false only when recording was requested and the file could not be
 * opened, so the session can record the evidence error.
 */
bool timeline_init(timeline_t * timeline, const char * session_dir,
                   bool record);

void timeline_close(timeline_t * timeline);

void timeline_frame(timeline_t * timeline, long frame_no, uint32_t t_ms,
                    const char * file);

/**
 * Input rows carry ``source`` (``virtual`` for protocol commands, ``real``
 * for Win32 input). ``seq`` is written when it is non-negative; real input
 * has no protocol sequence and passes -1.
 */
void timeline_input_pointer(timeline_t * timeline, long seq,
                            const char * source, long frame_no, uint32_t t_ms,
                            const char * action, long x, long y,
                            const char * hit, const char * hit_class);

void timeline_input_key(timeline_t * timeline, long seq, const char * source,
                        long frame_no, uint32_t t_ms, const char * action,
                        const char * key, bool delivered);

void timeline_input_encoder(timeline_t * timeline, long seq,
                            const char * source, long frame_no, uint32_t t_ms,
                            long diff);

void timeline_wait(timeline_t * timeline, uint32_t t_ms_start,
                   uint32_t t_ms_end, long frame_start, long frame_end);

void timeline_mark(timeline_t * timeline, long frame_no, uint32_t t_ms,
                   const char * id);

void timeline_snapshot(timeline_t * timeline, long frame_no, uint32_t t_ms,
                       const char * label, const char * file);

void timeline_end(timeline_t * timeline, long frame_count, uint32_t t_ms,
                  bool truncated);

#ifdef __cplusplus
}
#endif

#endif
