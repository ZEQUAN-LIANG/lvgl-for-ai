/**
 * One engine session: owns the refresh -> capture -> timeline -> diff
 * orchestration and the evidence write error state.
 *
 * Enforces the retained-frame invariant: one refresh produces at most one
 * retained frame, and its PNG, timeline frame row and diff rows share the same
 * ``frame_no`` and ``t_ms``. It also owns the changed-only comparison buffer,
 * so identical RGB frames are skipped before any evidence is written and frame
 * numbers stay contiguous.
 *
 * main.c keeps argument parsing, adapter/window lifecycle, protocol dispatch
 * and real-input callbacks; every evidence write goes through here.
 */

#ifndef SESSION_H
#define SESSION_H

#include "adapter.h"
#include "capture.h"
#include "frame_analysis.h"
#include "frame_diff.h"
#include "timeline.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    SESSION_ERROR_NONE = 0,
    SESSION_ERROR_EVIDENCE_INIT,
    SESSION_ERROR_CAPTURE,
    SESSION_ERROR_SNAPSHOT
} session_error_t;

typedef bool (*session_service_fn)(void * user);

typedef struct {
    adapter_t * adapter;
    const char * session_dir;
    uint32_t width;
    uint32_t height;
    bool record;
    bool live;
    bool record_changed_only;
    bool async_encode;
    uint64_t encode_budget_bytes;
    long max_frames;
    int diff_threshold;
    const uint8_t * reference;
    uint32_t reference_width;
    uint32_t reference_height;
    void (*present)(void * user);
    void * present_user;
} session_config_t;

typedef struct {
    adapter_t * adapter;
    capture_t capture;
    timeline_t timeline;
    frame_diff_t frame_diff;
    frame_diff_t reference_diff;
    bool has_reference;
    uint32_t t_ms;
    bool ended;

    uint32_t width;
    uint32_t height;
    int diff_threshold;
    bool changed_only;
    bool has_previous;
    uint8_t * previous;
    session_error_t error;

    void (*present)(void * user);
    void * present_user;
} session_t;

void session_init(session_t * session, const session_config_t * config);

/** Refresh the display, then record at most one retained frame. */
void session_refresh_frame(session_t * session);

/** tick <ms>: lv_tick_inc -> lv_timer_handler -> refresh -> record. */
void session_tick(session_t * session, uint32_t ms);

/** wait <ms>: tick in 16 ms steps and write the wait row; true when painted. */
bool session_wait_ms(session_t * session, unsigned long ms,
                     session_service_fn service, void * service_user);

/** wait frames <n>: n 16 ms ticks and the wait row; true when painted. */
bool session_wait_frames(session_t * session, unsigned long frames,
                         session_service_fn service, void * service_user);

void session_mark(session_t * session, const char * id);

void session_input_pointer(session_t * session, long seq, const char * source,
                           const char * action, long x, long y,
                           const char * hit, const char * hit_class);

void session_input_key(session_t * session, long seq, const char * source,
                       const char * action, const char * key, bool delivered);

void session_input_encoder(session_t * session, long seq, const char * source,
                           long diff);

/** Refresh + present, then write snapshots/NNN_<label>.png and its row. */
int session_snapshot(session_t * session, const char * label, char * relative,
                     size_t relative_size);

void session_drain_encoding(session_t * session);

bool session_encoder_failed(session_t * session);

void session_end(session_t * session);

void session_close(session_t * session);

long session_frame_count(const session_t * session);
uint32_t session_t_ms(const session_t * session);
bool session_truncated(const session_t * session);

#ifdef __cplusplus
}
#endif

#endif
