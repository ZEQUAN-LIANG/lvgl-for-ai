#include "capture.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <direct.h>
#define make_dir(path) _mkdir(path)
#else
#include <sys/stat.h>
#define make_dir(path) mkdir(path, 0777)
#endif

bool capture_init(capture_t * capture,
                  adapter_t * adapter,
                  const char * session_dir,
                  bool record,
                  long max_frames,
                  bool live,
                  bool async_encode,
                  uint64_t encode_budget_bytes)
{
    memset(capture, 0, sizeof(*capture));
    capture->adapter = adapter;
    capture->enabled = false;
    capture->live = live;
    capture->max_frames = max_frames;
    capture->frame_no = 0;
    capture->snapshot_no = 0;
    capture->truncated = false;
    if(session_dir == NULL) return true;

    snprintf(capture->session_dir, sizeof(capture->session_dir), "%s",
             session_dir);

    if(!record) return true;

    char frames_dir[1100];
    snprintf(frames_dir, sizeof(frames_dir), "%s/frames", capture->session_dir);
    if(make_dir(frames_dir) != 0 && errno != EEXIST) {
        fprintf(stderr, "[engine] cannot create %s\n", frames_dir);
        return false;
    }
    capture->enabled = true;
    if(async_encode) {
        const adapter_info_t * info = adapter_info(adapter);
        uint64_t budget = encode_budget_bytes == 0u
                              ? FRAME_ENCODER_BUDGET_BYTES
                              : encode_budget_bytes;
        if(info == NULL || info->width == 0u || info->height == 0u) {
            return false;
        }
        capture->encoder = frame_encoder_start(session_dir, info->width,
                                               info->height, budget);
        if(capture->encoder == NULL) return false;
    }
    return true;
}

int capture_frame(capture_t * capture,
                  char * relpath,
                  size_t relpath_size,
                  capture_frame_result_t * result)
{
    if(result != NULL) memset(result, 0, sizeof(*result));
    if(relpath != NULL && relpath_size > 0) relpath[0] = '\0';
    if(capture == NULL) return 0;

    if(!capture->enabled) {
        if(!capture->live || capture->session_dir[0] == '\0') return 0;
        char live_path[2048];
        snprintf(live_path, sizeof(live_path), "%s/live.rgba",
                 capture->session_dir);
        if(adapter_save_rgba(capture->adapter, live_path) != 0) {
            return -1;
        }
        capture->frame_no++;
        if(result != NULL) result->preview_written = true;
        return 0;
    }

    if(capture->frame_no < capture->max_frames) {
        char relative[64];
        snprintf(relative, sizeof(relative), "frames/%06ld.png",
                 capture->frame_no + 1);
        if(capture->encoder != NULL) {
            const uint8_t * framebuffer = adapter_framebuffer(capture->adapter);
            if(framebuffer == NULL) return -1;
            if(frame_encoder_submit(capture->encoder, capture->frame_no + 1,
                                    framebuffer) != 0) {
                return -1;
            }
        }
        else {
            char path[2048];
            snprintf(path, sizeof(path), "%s/%s", capture->session_dir,
                     relative);
            if(adapter_save_png(capture->adapter, path) != 0) {
                return -1;
            }
        }
        capture->frame_no++;
        if(relpath != NULL && relpath_size > 0) {
            snprintf(relpath, relpath_size, "%s", relative);
        }
        if(result != NULL) result->frame_written = true;
    }
    else {
        capture->truncated = true;
    }

    if(capture->live) {
        char live_path[2048];
        snprintf(live_path, sizeof(live_path), "%s/live.rgba",
                 capture->session_dir);
        bool raw_saved = adapter_save_rgba(capture->adapter, live_path) == 0;
        if(raw_saved) {
            if(result != NULL) result->preview_written = true;
        }
        else {
            fprintf(stderr,
                    "[engine] cannot write the live preview frame to %s\n",
                    live_path);
        }
    }
    return 0;
}

void capture_close(capture_t * capture)
{
    if(capture == NULL) return;
    if(capture->encoder != NULL) {
        frame_encoder_stop(capture->encoder);
        capture->encoder = NULL;
    }
    capture->enabled = false;
}

void capture_drain(capture_t * capture)
{
    if(capture == NULL || capture->encoder == NULL) return;
    frame_encoder_drain(capture->encoder);
}

bool capture_encoder_failed(capture_t * capture)
{
    return capture != NULL && capture->encoder != NULL &&
           frame_encoder_failed(capture->encoder);
}

int capture_snapshot(capture_t * capture,
                     const char * label,
                     char * relpath,
                     size_t relpath_size)
{
    if(relpath != NULL && relpath_size > 0) relpath[0] = '\0';
    if(capture == NULL || label == NULL || capture->session_dir[0] == '\0') {
        return -1;
    }

    char snapshots_dir[1100];
    snprintf(snapshots_dir, sizeof(snapshots_dir), "%s/snapshots",
             capture->session_dir);
    if(make_dir(snapshots_dir) != 0 && errno != EEXIST) {
        fprintf(stderr, "[engine] cannot create %s\n", snapshots_dir);
        return -1;
    }

    char relative[256];
    snprintf(relative, sizeof(relative), "snapshots/%03ld_%s.png",
             capture->snapshot_no + 1, label);
    char path[2048];
    snprintf(path, sizeof(path), "%s/%s", capture->session_dir, relative);
    if(adapter_save_png(capture->adapter, path) != 0) {
        return -1;
    }
    capture->snapshot_no++;
    if(relpath != NULL && relpath_size > 0) {
        snprintf(relpath, relpath_size, "%s", relative);
    }
    return 0;
}

long capture_frame_count(const capture_t * capture)
{
    return capture == NULL ? 0 : capture->frame_no;
}

bool capture_truncated(const capture_t * capture)
{
    return capture != NULL && capture->truncated;
}
