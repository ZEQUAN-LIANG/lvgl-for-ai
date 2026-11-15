#include "timeline.h"

#include "json.h"

#include <errno.h>
#include <string.h>

static void begin_row(const timeline_t * timeline, const char * type)
{
    fprintf(timeline->out,
            "{\"schema\":\"lvgl-ai-timeline-v1\",\"type\":\"%s\"", type);
}

static void end_row(const timeline_t * timeline)
{
    fputs("}\n", timeline->out);
    fflush(timeline->out);
}

static void write_source_and_position(timeline_t * timeline, long seq,
                                      const char * source, long frame_no,
                                      uint32_t t_ms)
{
    if(seq >= 0) fprintf(timeline->out, ",\"seq\":%ld", seq);
    fprintf(timeline->out,
            ",\"frame_no\":%ld,\"t_ms\":%lu,\"source\":", frame_no,
            (unsigned long)t_ms);
    json_write_string(timeline->out, source);
}

bool timeline_init(timeline_t * timeline, const char * session_dir, bool record)
{
    if(timeline == NULL) return false;
    memset(timeline, 0, sizeof(*timeline));
    if(!record) return true;
    if(session_dir == NULL) return false;

    char path[2048];
    snprintf(path, sizeof(path), "%s/timeline.ndjson", session_dir);
    timeline->out = fopen(path, "w");
    if(timeline->out == NULL) {
        int saved = errno;
        fprintf(stderr, "[engine] cannot write %s: %s\n", path,
                strerror(saved));
        return false;
    }
    timeline->enabled = true;
    return true;
}

void timeline_close(timeline_t * timeline)
{
    if(timeline == NULL) return;
    if(timeline->out != NULL) {
        fflush(timeline->out);
        fclose(timeline->out);
        timeline->out = NULL;
    }
    timeline->enabled = false;
}

void timeline_frame(timeline_t * timeline, long frame_no, uint32_t t_ms,
                    const char * file)
{
    if(timeline == NULL || !timeline->enabled) return;
    begin_row(timeline, "frame");
    fprintf(timeline->out, ",\"frame_no\":%ld,\"t_ms\":%lu,\"file\":", frame_no,
            (unsigned long)t_ms);
    json_write_string(timeline->out, file);
    end_row(timeline);
}

void timeline_input_pointer(timeline_t * timeline, long seq,
                            const char * source, long frame_no, uint32_t t_ms,
                            const char * action, long x, long y,
                            const char * hit, const char * hit_class)
{
    if(timeline == NULL || !timeline->enabled) return;
    begin_row(timeline, "input");
    write_source_and_position(timeline, seq, source, frame_no, t_ms);
    fprintf(timeline->out,
            ",\"device\":\"pointer\",\"action\":\"%s\",\"x\":%ld,\"y\":%ld,"
            "\"hit\":",
            action, x, y);
    json_write_string(timeline->out, hit);
    fputs(",\"hit_class\":", timeline->out);
    json_write_string(timeline->out, hit_class);
    end_row(timeline);
}

void timeline_input_key(timeline_t * timeline, long seq, const char * source,
                        long frame_no, uint32_t t_ms, const char * action,
                        const char * key, bool delivered)
{
    if(timeline == NULL || !timeline->enabled) return;
    begin_row(timeline, "input");
    write_source_and_position(timeline, seq, source, frame_no, t_ms);
    fprintf(timeline->out,
            ",\"device\":\"key\",\"action\":\"%s\",\"key\":", action);
    json_write_string(timeline->out, key);
    fprintf(timeline->out, ",\"delivered\":%s", delivered ? "true" : "false");
    end_row(timeline);
}

void timeline_input_encoder(timeline_t * timeline, long seq,
                            const char * source, long frame_no, uint32_t t_ms,
                            long diff)
{
    if(timeline == NULL || !timeline->enabled) return;
    begin_row(timeline, "input");
    write_source_and_position(timeline, seq, source, frame_no, t_ms);
    fprintf(timeline->out,
            ",\"device\":\"encoder\",\"action\":\"turn\",\"diff\":%ld,"
            "\"delivered\":true",
            diff);
    end_row(timeline);
}

void timeline_wait(timeline_t * timeline, uint32_t t_ms_start,
                   uint32_t t_ms_end, long frame_start, long frame_end)
{
    if(timeline == NULL || !timeline->enabled) return;
    begin_row(timeline, "wait");
    fprintf(timeline->out,
            ",\"t_ms_start\":%lu,\"t_ms_end\":%lu,"
            "\"frame_start\":%ld,\"frame_end\":%ld",
            (unsigned long)t_ms_start, (unsigned long)t_ms_end, frame_start,
            frame_end);
    end_row(timeline);
}

void timeline_mark(timeline_t * timeline, long frame_no, uint32_t t_ms,
                   const char * id)
{
    if(timeline == NULL || !timeline->enabled) return;
    begin_row(timeline, "mark");
    fprintf(timeline->out, ",\"frame_no\":%ld,\"t_ms\":%lu,\"id\":", frame_no,
            (unsigned long)t_ms);
    json_write_string(timeline->out, id);
    end_row(timeline);
}

void timeline_snapshot(timeline_t * timeline, long frame_no, uint32_t t_ms,
                       const char * label, const char * file)
{
    if(timeline == NULL || !timeline->enabled) return;
    begin_row(timeline, "snapshot");
    fprintf(timeline->out,
            ",\"frame_no\":%ld,\"t_ms\":%lu,\"label\":", frame_no,
            (unsigned long)t_ms);
    json_write_string(timeline->out, label);
    fputs(",\"file\":", timeline->out);
    json_write_string(timeline->out, file);
    end_row(timeline);
}

void timeline_end(timeline_t * timeline, long frame_count, uint32_t t_ms,
                  bool truncated)
{
    if(timeline == NULL || !timeline->enabled) return;
    begin_row(timeline, "end");
    fprintf(timeline->out, ",\"frame_count\":%ld,\"t_ms\":%lu,\"truncated\":%s",
            frame_count, (unsigned long)t_ms, truncated ? "true" : "false");
    end_row(timeline);
}
