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

bool capture_init(capture_t * capture, adapter_t * adapter,
                  const char * session_dir, bool record, long max_frames,
                  bool live, bool async_encode, uint64_t encode_budget_bytes);

int capture_frame(capture_t * capture, char * relpath, size_t relpath_size,
                  capture_frame_result_t * result);

void capture_close(capture_t * capture);

void capture_drain(capture_t * capture);

bool capture_encoder_failed(capture_t * capture);

int capture_snapshot(capture_t * capture, const char * label, char * relpath,
                     size_t relpath_size);

long capture_frame_count(const capture_t * capture);

bool capture_truncated(const capture_t * capture);

#ifdef __cplusplus
}
#endif

#endif
