#include "frame_diff.h"

#include <stdlib.h>
#include <string.h>

static int clamp_threshold(int threshold)
{
    if(threshold < 0) return 0;
    if(threshold > 255) return 255;
    return threshold;
}

static bool open_writer(frame_diff_t * diff,
                        const char * session_dir,
                        const char * filename)
{
    char path[2048];
    snprintf(path, sizeof(path), "%s/%s", session_dir, filename);
    diff->out = fopen(path, "w");
    if(diff->out == NULL) {
        fprintf(stderr, "[engine] cannot write %s\n", path);
        return false;
    }
    diff->enabled = true;
    return true;
}

static void reset(frame_diff_t * diff)
{
    memset(diff, 0, sizeof(*diff));
}

bool frame_diff_open_previous(frame_diff_t * diff,
                              const char * session_dir,
                              uint32_t width,
                              uint32_t height,
                              int threshold,
                              bool record)
{
    if(diff == NULL) return false;
    reset(diff);
    if(!record || session_dir == NULL || width == 0 || height == 0) return false;

    diff->width = width;
    diff->height = height;
    diff->threshold = clamp_threshold(threshold);
    diff->previous = (uint8_t *)malloc((size_t)width * height * 4u);
    if(diff->previous == NULL) {
        fprintf(stderr, "[engine] cannot allocate the frame diff buffer\n");
        return false;
    }
    if(!open_writer(diff, session_dir, "frame_diffs.ndjson")) {
        free(diff->previous);
        reset(diff);
        return false;
    }
    return true;
}

bool frame_diff_open_reference(frame_diff_t * diff,
                               const char * session_dir,
                               const uint8_t * reference,
                               uint32_t width,
                               uint32_t height,
                               int threshold,
                               bool record)
{
    if(diff == NULL) return false;
    reset(diff);
    if(!record || session_dir == NULL || reference == NULL || width == 0 ||
       height == 0) {
        return false;
    }

    diff->reference_mode = true;
    diff->reference = reference;
    diff->width = width;
    diff->height = height;
    diff->threshold = clamp_threshold(threshold);
    if(!open_writer(diff, session_dir, "reference_diffs.ndjson")) {
        reset(diff);
        return false;
    }
    return true;
}

static void write_row(frame_diff_t * diff,
                      long frame_no,
                      long prev_frame_no,
                      bool has_previous,
                      uint32_t t_ms,
                      const frame_analysis_t * stats)
{
    double pixels = (double)diff->width * (double)diff->height;
    fprintf(diff->out,
            "{\"schema\":\"lvgl-ai-frame-diffs-v1\",\"frame_no\":%ld,\"t_ms\":%lu,"
            "\"width\":%u,\"height\":%u,\"threshold\":%d,",
            frame_no, (unsigned long)t_ms, diff->width, diff->height,
            diff->threshold);
    if(has_previous) {
        fprintf(diff->out, "\"prev_frame_no\":%ld,", prev_frame_no);
    }
    else {
        fputs("\"prev_frame_no\":null,", diff->out);
    }
    if(stats->changed_px == 0) {
        fputs("\"bbox\":null,", diff->out);
    }
    else {
        fprintf(diff->out,
                "\"bbox\":{\"x\":%u,\"y\":%u,\"w\":%u,\"h\":%u},",
                stats->min_x, stats->min_y,
                stats->max_x - stats->min_x + 1u,
                stats->max_y - stats->min_y + 1u);
    }
    fprintf(diff->out,
            "\"changed_px\":%ld,\"changed_ratio\":%.9f,\"max_delta\":%.9f}\n",
            stats->changed_px,
            pixels > 0.0 ? (double)stats->changed_px / pixels : 0.0,
            (double)stats->max_delta / 255.0);
    fflush(diff->out);
}

void frame_diff_record_previous(frame_diff_t * diff,
                                const uint8_t * frame,
                                long frame_no,
                                uint32_t t_ms,
                                const frame_analysis_t * analysis)
{
    if(diff == NULL || !diff->enabled || frame == NULL) return;

    size_t bytes = (size_t)diff->width * diff->height * 4u;
    if(!diff->has_previous) {
        memcpy(diff->previous, frame, bytes);
        diff->has_previous = true;
        diff->prev_frame_no = frame_no;
        return;
    }

    frame_analysis_t computed;
    if(analysis == NULL) {
        frame_analysis_compare(diff->previous, frame, diff->width,
                               diff->height, diff->threshold, &computed);
        analysis = &computed;
    }
    write_row(diff, frame_no, diff->prev_frame_no, true, t_ms, analysis);
    memcpy(diff->previous, frame, bytes);
    diff->prev_frame_no = frame_no;
}

void frame_diff_record_reference(frame_diff_t * diff,
                                 const uint8_t * frame,
                                 long frame_no,
                                 uint32_t t_ms)
{
    if(diff == NULL || !diff->enabled || !diff->reference_mode ||
       frame == NULL || diff->reference == NULL) {
        return;
    }

    frame_analysis_t analysis;
    frame_analysis_compare(diff->reference, frame, diff->width, diff->height,
                           diff->threshold, &analysis);
    /* Reference rows have no previous frame; prev_frame_no is null. */
    write_row(diff, frame_no, 0, false, t_ms, &analysis);
}

void frame_diff_close(frame_diff_t * diff)
{
    if(diff == NULL) return;
    if(diff->out != NULL) {
        fflush(diff->out);
        fclose(diff->out);
    }
    free(diff->previous);
    reset(diff);
}
