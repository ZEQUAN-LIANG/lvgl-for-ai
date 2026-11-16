#ifndef CAPTURE_H
#define CAPTURE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "adapter.h"
#include "frame_encoder.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    adapter_t * adapter;
    char session_dir[1024];
    bool enabled;
    bool live;
    long max_frames;
    long frame_no;
    long snapshot_no;
    bool truncated;
    frame_encoder_t * encoder;
} capture_t;

typedef struct {
    bool frame_written;
    bool preview_written;
} capture_frame_result_t;

/**
 * Prepare frames/ under session_dir. record=false disables frame history.
 * ``live=true`` writes session_dir/live.rgba on every retained frame, whether
 * or not recording is on; the file is raw RGBA8888 for the web preview and is
 * never an evidence artifact. ``max_frames`` caps recorded PNG frames; 0
 * means no frame is saved and the first changed frame sets ``truncated``.
 * The raw live frame keeps updating after the cap. Returns false only when
 * recording was requested and frames/ could not be created.
 */
bool capture_init(capture_t * capture, adapter_t * adapter,
                  const char * session_dir, bool record, long max_frames,
                  bool live, bool async_encode, uint64_t encode_budget_bytes);

/**
 * Save the current framebuffer. With record=true and room left this writes
 * frames/NNNNNN.png and reports ``frame_written``; otherwise it sets
 * ``truncated`` without consuming a frame number. With live=true the raw
 * preview is written after the PNG, including once max_frames is reached.
 * Returns 0 on success, -1 when a PNG or the live-only preview failed.
 */
int capture_frame(capture_t * capture, char * relpath, size_t relpath_size,
                  capture_frame_result_t * result);

void capture_close(capture_t * capture);

void capture_drain(capture_t * capture);

bool capture_encoder_failed(capture_t * capture);

/**
 * Save the current framebuffer as snapshots/NNN_<label>.png. Snapshots are
 * explicit evidence, so they are written even when recording is off.
 */
int capture_snapshot(capture_t * capture, const char * label, char * relpath,
                     size_t relpath_size);

long capture_frame_count(const capture_t * capture);

bool capture_truncated(const capture_t * capture);

#ifdef __cplusplus
}
#endif

#endif
