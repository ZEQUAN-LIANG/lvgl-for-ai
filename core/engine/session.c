#include "session.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WAIT_STEP_MS 16u
#define FRAME_BYTES(width, height) ((size_t)(width) * (height) * 4u)

static void session_present(session_t * session)
{
    if(session->present != NULL) session->present(session->present_user);
}

static void session_fail(session_t * session, session_error_t error)
{
    if(session->error == SESSION_ERROR_NONE) session->error = error;
}

static void session_remember(session_t * session, const uint8_t * frame)
{
    if(!session->changed_only || session->previous == NULL || frame == NULL) {
        return;
    }
    memcpy(session->previous, frame, FRAME_BYTES(session->width,
                                                session->height));
    session->has_previous = true;
}

static void session_record_frame(session_t * session)
{
    session_present(session);

    const uint8_t * framebuffer = adapter_framebuffer(session->adapter);
    frame_analysis_t analysis;
    bool has_analysis = false;
    if(session->changed_only && session->has_previous && framebuffer != NULL) {
        frame_analysis_compare(session->previous, framebuffer, session->width,
                               session->height, session->diff_threshold,
                               &analysis);
        has_analysis = true;
        if(analysis.rgb_equal) return;
    }

    char relative[64];
    capture_frame_result_t result;
    if(capture_frame(&session->capture, relative, sizeof(relative),
                     &result) != 0) {
        session_fail(session, SESSION_ERROR_CAPTURE);
        return;
    }

    if(result.frame_written) {
        long frame_no = capture_frame_count(&session->capture);
        timeline_frame(&session->timeline, frame_no, session->t_ms, relative);
        frame_diff_record_previous(&session->frame_diff, framebuffer, frame_no,
                                   session->t_ms,
                                   has_analysis ? &analysis : NULL);
        if(session->has_reference) {
            frame_diff_record_reference(&session->reference_diff, framebuffer,
                                        frame_no, session->t_ms);
        }
    }

    if(result.frame_written || result.preview_written) {
        session_remember(session, framebuffer);
    }
}

void session_init(session_t * session, const session_config_t * config)
{
    if(session == NULL) return;
    memset(session, 0, sizeof(*session));
    if(config == NULL) return;

    session->adapter = config->adapter;
    session->width = config->width;
    session->height = config->height;
    session->diff_threshold = config->diff_threshold;
    session->present = config->present;
    session->present_user = config->present_user;

    const adapter_info_t * info = adapter_info(config->adapter);
    if(config->record_changed_only && (config->record || config->live) &&
       info != NULL && info->width > 0 && info->height > 0) {
        session->previous = (uint8_t *)malloc(
            FRAME_BYTES(info->width, info->height));
        if(session->previous != NULL) {
            session->width = info->width;
            session->height = info->height;
            session->changed_only = true;
        }
        else {
            fprintf(stderr,
                    "[engine] cannot allocate the frame comparison buffer; "
                    "saving every frame\n");
        }
    }

    bool capture_ok = capture_init(&session->capture, config->adapter,
                                   config->session_dir, config->record,
                                   config->max_frames, config->live,
                                   config->async_encode,
                                   config->encode_budget_bytes);
    bool timeline_ok = timeline_init(&session->timeline, config->session_dir,
                                     config->record);
    bool diff_ok = frame_diff_open_previous(
        &session->frame_diff, config->session_dir, config->width,
        config->height, config->diff_threshold, config->record);
    if(config->record && (!capture_ok || !timeline_ok || !diff_ok)) {
        session_fail(session, SESSION_ERROR_EVIDENCE_INIT);
    }

    if(config->reference != NULL) {
        session->has_reference = frame_diff_open_reference(
            &session->reference_diff, config->session_dir, config->reference,
            config->reference_width, config->reference_height,
            config->diff_threshold, config->record);
        if(config->record && !session->has_reference) {
            session_fail(session, SESSION_ERROR_EVIDENCE_INIT);
        }
    }
}

void session_refresh_frame(session_t * session)
{
    if(session == NULL) return;
    adapter_refresh(session->adapter);
    session_record_frame(session);
}

void session_tick(session_t * session, uint32_t ms)
{
    if(session == NULL) return;
    if(ms > 0) {
        adapter_tick_inc(session->adapter, ms);
        session->t_ms += ms;
    }
    adapter_timer_handler(session->adapter);
    session_refresh_frame(session);
}

bool session_wait_ms(session_t * session,
                     unsigned long ms,
                     session_service_fn service,
                     void * service_user)
{
    if(session == NULL) return false;
    uint32_t start_t = session->t_ms;
    long start_frames = capture_frame_count(&session->capture);
    unsigned long remaining = ms;
    bool changed = false;
    while(remaining > 0) {
        unsigned long step =
            remaining > WAIT_STEP_MS ? WAIT_STEP_MS : remaining;
        session_tick(session, (uint32_t)step);
        changed = changed || adapter_last_refresh_painted(session->adapter);
        remaining -= step;
        if(service != NULL && !service(service_user)) break;
    }
    timeline_wait(&session->timeline, start_t, session->t_ms, start_frames,
                  capture_frame_count(&session->capture));
    return changed;
}

bool session_wait_frames(session_t * session,
                         unsigned long frames,
                         session_service_fn service,
                         void * service_user)
{
    if(session == NULL) return false;
    uint32_t start_t = session->t_ms;
    long start_frames = capture_frame_count(&session->capture);
    bool changed = false;
    for(unsigned long i = 0; i < frames; i++) {
        session_tick(session, WAIT_STEP_MS);
        changed = changed || adapter_last_refresh_painted(session->adapter);
        if(service != NULL && !service(service_user)) break;
    }
    timeline_wait(&session->timeline, start_t, session->t_ms, start_frames,
                  capture_frame_count(&session->capture));
    return changed;
}

void session_mark(session_t * session, const char * id)
{
    if(session == NULL || id == NULL) return;
    timeline_mark(&session->timeline, capture_frame_count(&session->capture),
                  session->t_ms, id);
}

void session_input_pointer(session_t * session,
                           long seq,
                           const char * source,
                           const char * action,
                           long x,
                           long y,
                           const char * hit,
                           const char * hit_class)
{
    if(session == NULL) return;
    timeline_input_pointer(&session->timeline, seq, source,
                           capture_frame_count(&session->capture),
                           session->t_ms, action, x, y, hit, hit_class);
}

void session_input_key(session_t * session,
                       long seq,
                       const char * source,
                       const char * action,
                       const char * key,
                       bool delivered)
{
    if(session == NULL) return;
    timeline_input_key(&session->timeline, seq, source,
                       capture_frame_count(&session->capture),
                       session->t_ms, action, key, delivered);
}

void session_input_encoder(session_t * session,
                           long seq,
                           const char * source,
                           long diff)
{
    if(session == NULL) return;
    timeline_input_encoder(&session->timeline, seq, source,
                           capture_frame_count(&session->capture),
                           session->t_ms, diff);
}

int session_snapshot(session_t * session,
                     const char * label,
                     char * relative,
                     size_t relative_size)
{
    if(relative != NULL && relative_size > 0) relative[0] = '\0';
    if(session == NULL || label == NULL) return -1;

    adapter_refresh(session->adapter);
    session_present(session);

    char path[256];
    if(capture_snapshot(&session->capture, label, path, sizeof(path)) != 0) {
        session_fail(session, SESSION_ERROR_SNAPSHOT);
        return -1;
    }
    timeline_snapshot(&session->timeline,
                      capture_frame_count(&session->capture), session->t_ms,
                      label, path);
    if(relative != NULL && relative_size > 0) {
        snprintf(relative, relative_size, "%s", path);
    }
    return 0;
}

void session_drain_encoding(session_t * session)
{
    if(session == NULL) return;
    capture_drain(&session->capture);
}

bool session_encoder_failed(session_t * session)
{
    if(session == NULL) return false;
    return capture_encoder_failed(&session->capture);
}

void session_end(session_t * session)
{
    if(session == NULL || session->ended) return;
    session_drain_encoding(session);
    timeline_end(&session->timeline, capture_frame_count(&session->capture),
                 session->t_ms, capture_truncated(&session->capture));
    session->ended = true;
}

void session_close(session_t * session)
{
    if(session == NULL) return;
    free(session->previous);
    session->previous = NULL;
    session->has_previous = false;
    session->changed_only = false;
    capture_close(&session->capture);
    frame_diff_close(&session->frame_diff);
    frame_diff_close(&session->reference_diff);
    timeline_close(&session->timeline);
}

long session_frame_count(const session_t * session)
{
    return session == NULL ? 0 : capture_frame_count(&session->capture);
}

uint32_t session_t_ms(const session_t * session)
{
    return session == NULL ? 0 : session->t_ms;
}

bool session_truncated(const session_t * session)
{
    return session != NULL && capture_truncated(&session->capture);
}
