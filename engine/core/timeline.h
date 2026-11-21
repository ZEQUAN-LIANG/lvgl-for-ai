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

bool timeline_init(timeline_t * timeline, const char * session_dir,
                   bool record);

void timeline_close(timeline_t * timeline);

void timeline_frame(timeline_t * timeline, long frame_no, uint32_t t_ms,
                    const char * file);

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
