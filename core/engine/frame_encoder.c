#include "frame_encoder.h"
#include "png_writer.h"

#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#define make_dir(path) _mkdir(path)
#define remove_dir(path) _rmdir(path)
#else
#include <pthread.h>
#include <sys/stat.h>
#include <unistd.h>
#define make_dir(path) mkdir((path), (S_IRWXU | S_IRWXG | S_IRWXO))
#define remove_dir(path) rmdir(path)
#endif

#define ENCODER_PATH_SIZE 1200
#define FRAME_ENCODER_WORKERS 3

typedef struct frame_job {
    long frame_no;
    uint64_t bytes;
    uint8_t * pixels;
    struct frame_job * next;
} frame_job_t;

struct frame_encoder {
    char session_dir[1024];
    char temp_dir[ENCODER_PATH_SIZE];
    char frames_dir[ENCODER_PATH_SIZE];
    uint32_t width;
    uint32_t height;
    uint64_t frame_bytes;
    uint64_t byte_budget;
    frame_job_t * head;
    frame_job_t * tail;
    long pending_jobs;
    uint64_t pending_bytes;
    bool stopping;
    bool failed;
    long worker_count;
#ifdef _WIN32
    CRITICAL_SECTION lock;
    HANDLE work_event;
    HANDLE progress_event;
    HANDLE threads[FRAME_ENCODER_WORKERS];
#else
    pthread_mutex_t lock;
    pthread_cond_t work_cond;
    pthread_cond_t progress_cond;
    pthread_t threads[FRAME_ENCODER_WORKERS];
#endif
};

static void encoder_lock(frame_encoder_t * encoder)
{
#ifdef _WIN32
    EnterCriticalSection(&encoder->lock);
#else
    (void)pthread_mutex_lock(&encoder->lock);
#endif
}

static void encoder_unlock(frame_encoder_t * encoder)
{
#ifdef _WIN32
    LeaveCriticalSection(&encoder->lock);
#else
    (void)pthread_mutex_unlock(&encoder->lock);
#endif
}

static void encoder_signal_work(frame_encoder_t * encoder)
{
#ifdef _WIN32
    (void)SetEvent(encoder->work_event);
#else
    (void)pthread_cond_broadcast(&encoder->work_cond);
#endif
}

static void encoder_signal_progress(frame_encoder_t * encoder)
{
#ifdef _WIN32
    (void)SetEvent(encoder->progress_event);
#else
    (void)pthread_cond_broadcast(&encoder->progress_cond);
#endif
}

static void encoder_wait_work(frame_encoder_t * encoder)
{
#ifdef _WIN32
    (void)ResetEvent(encoder->work_event);
    LeaveCriticalSection(&encoder->lock);
    (void)WaitForSingleObject(encoder->work_event, INFINITE);
    EnterCriticalSection(&encoder->lock);
#else
    (void)pthread_cond_wait(&encoder->work_cond, &encoder->lock);
#endif
}

static void encoder_wait_progress(frame_encoder_t * encoder)
{
#ifdef _WIN32
    LeaveCriticalSection(&encoder->lock);
    (void)WaitForSingleObject(encoder->progress_event, INFINITE);
    EnterCriticalSection(&encoder->lock);
#else
    (void)pthread_cond_wait(&encoder->progress_cond, &encoder->lock);
#endif
}

static bool build_path(char * out,
                       size_t out_size,
                       const char * directory,
                       const char * name)
{
    int written = snprintf(out, out_size, "%s/%s", directory, name);
    return (written > 0) && ((size_t)written < out_size);
}

static bool numbered_name(char * out, size_t out_size, long frame_no,
                          const char * suffix)
{
    int written = snprintf(out, out_size, "%06ld%s", frame_no, suffix);
    return (written > 0) && ((size_t)written < out_size);
}

static bool tmp_path_for(const frame_encoder_t * encoder,
                         long frame_no,
                         char * out,
                         size_t out_size)
{
    char name[64];
    if(!numbered_name(name, sizeof(name), frame_no, ".png.tmp")) {
        return false;
    }
    return build_path(out, out_size, encoder->temp_dir, name);
}

static bool final_path_for(const frame_encoder_t * encoder,
                           long frame_no,
                           char * out,
                           size_t out_size)
{
    char name[64];
    if(!numbered_name(name, sizeof(name), frame_no, ".png")) {
        return false;
    }
    return build_path(out, out_size, encoder->frames_dir, name);
}

static bool encode_job(const frame_encoder_t * encoder, const frame_job_t * job)
{
    char tmp_path[ENCODER_PATH_SIZE];
    char final_path[ENCODER_PATH_SIZE];
    bool ok = false;

    if(!tmp_path_for(encoder, job->frame_no, tmp_path, sizeof(tmp_path)) ||
       !final_path_for(encoder, job->frame_no, final_path,
                       sizeof(final_path))) {
        fprintf(stderr, "[engine] encoder path is too long\n");
        return false;
    }

    ok = png_writer_write_xrgb(job->pixels, encoder->width, encoder->height,
                               tmp_path) == 0;
    if(ok) {
        (void)remove(final_path);
        if(rename(tmp_path, final_path) != 0) {
            fprintf(stderr, "[engine] cannot publish %s\n", final_path);
            ok = false;
        }
    }
    if(!ok) {
        (void)remove(tmp_path);
        fprintf(stderr, "[engine] cannot encode frames/%06ld.png\n",
                job->frame_no);
    }
    return ok;
}

static void worker_main(frame_encoder_t * encoder)
{
    for(;;) {
        encoder_lock(encoder);
        while((encoder->head == NULL) && !encoder->stopping) {
            encoder_wait_work(encoder);
        }
        if(encoder->head == NULL) {
            encoder_unlock(encoder);
            break;
        }
        frame_job_t * job = encoder->head;
        encoder->head = job->next;
        if(encoder->head == NULL) {
            encoder->tail = NULL;
        }
        encoder_unlock(encoder);

        bool ok = encode_job(encoder, job);

        encoder_lock(encoder);
        if(!ok) {
            encoder->failed = true;
        }
        if(encoder->pending_jobs > 0) {
            encoder->pending_jobs--;
        }
        if(encoder->pending_bytes >= job->bytes) {
            encoder->pending_bytes -= job->bytes;
        }
        else {
            encoder->pending_bytes = 0u;
        }
        encoder_signal_progress(encoder);
        encoder_unlock(encoder);
        free(job->pixels);
        free(job);
    }
}

#ifdef _WIN32
static DWORD WINAPI worker_entry(LPVOID argument)
{
    worker_main(argument);
    return 0u;
}
#else
static void * worker_entry(void * argument)
{
    worker_main(argument);
    return NULL;
}
#endif

static bool init_sync(frame_encoder_t * encoder)
{
#ifdef _WIN32
    InitializeCriticalSection(&encoder->lock);
    encoder->work_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    encoder->progress_event = CreateEventW(NULL, FALSE, FALSE, NULL);
    if((encoder->work_event == NULL) || (encoder->progress_event == NULL)) {
        if(encoder->work_event != NULL) {
            (void)CloseHandle(encoder->work_event);
        }
        if(encoder->progress_event != NULL) {
            (void)CloseHandle(encoder->progress_event);
        }
        DeleteCriticalSection(&encoder->lock);
        return false;
    }
    return true;
#else
    if(pthread_mutex_init(&encoder->lock, NULL) != 0) {
        return false;
    }
    if(pthread_cond_init(&encoder->work_cond, NULL) != 0) {
        (void)pthread_mutex_destroy(&encoder->lock);
        return false;
    }
    if(pthread_cond_init(&encoder->progress_cond, NULL) != 0) {
        (void)pthread_cond_destroy(&encoder->work_cond);
        (void)pthread_mutex_destroy(&encoder->lock);
        return false;
    }
    return true;
#endif
}

static void destroy_sync(frame_encoder_t * encoder)
{
#ifdef _WIN32
    for(long i = 0; i < encoder->worker_count; i++) {
        if(encoder->threads[i] != NULL) {
            (void)CloseHandle(encoder->threads[i]);
        }
    }
    (void)CloseHandle(encoder->work_event);
    (void)CloseHandle(encoder->progress_event);
    DeleteCriticalSection(&encoder->lock);
#else
    (void)pthread_cond_destroy(&encoder->progress_cond);
    (void)pthread_cond_destroy(&encoder->work_cond);
    (void)pthread_mutex_destroy(&encoder->lock);
#endif
}

static bool start_workers(frame_encoder_t * encoder)
{
    for(long i = 0; i < FRAME_ENCODER_WORKERS; i++) {
#ifdef _WIN32
        encoder->threads[i] = CreateThread(NULL, 0, worker_entry, encoder, 0,
                                           NULL);
        if(encoder->threads[i] == NULL) {
            return false;
        }
#else
        if(pthread_create(&encoder->threads[i], NULL, worker_entry, encoder)
           != 0) {
            return false;
        }
#endif
        encoder->worker_count++;
    }
    return true;
}

static void join_workers(frame_encoder_t * encoder)
{
    for(long i = 0; i < encoder->worker_count; i++) {
#ifdef _WIN32
        (void)WaitForSingleObject(encoder->threads[i], INFINITE);
#else
        (void)pthread_join(encoder->threads[i], NULL);
#endif
    }
}

static void rollback_bytes(frame_encoder_t * encoder, uint64_t bytes)
{
    encoder_lock(encoder);
    if(encoder->pending_bytes >= bytes) {
        encoder->pending_bytes -= bytes;
    }
    encoder_signal_progress(encoder);
    encoder_unlock(encoder);
}

frame_encoder_t * frame_encoder_start(const char * session_dir,
                                      uint32_t width,
                                      uint32_t height,
                                      uint64_t byte_budget)
{
    if((session_dir == NULL) || (width == 0u) || (height == 0u) ||
       (byte_budget == 0u)) {
        return NULL;
    }
    uint64_t pixels = (uint64_t)width * (uint64_t)height;
    if((pixels > (UINT64_MAX / 4u)) ||
       ((pixels * 4u) > (uint64_t)SIZE_MAX)) {
        return NULL;
    }
    frame_encoder_t * encoder = (frame_encoder_t *)calloc(1u, sizeof(*encoder));
    if(encoder == NULL) {
        return NULL;
    }
    int session_len = snprintf(encoder->session_dir,
                               sizeof(encoder->session_dir), "%s", session_dir);
    int temp_len = snprintf(encoder->temp_dir, sizeof(encoder->temp_dir),
                            "%s/.encode", session_dir);
    int frames_len = snprintf(encoder->frames_dir, sizeof(encoder->frames_dir),
                              "%s/frames", session_dir);
    if((session_len <= 0) ||
       ((size_t)session_len >= sizeof(encoder->session_dir)) ||
       (temp_len <= 0) || ((size_t)temp_len >= sizeof(encoder->temp_dir)) ||
       (frames_len <= 0) ||
       ((size_t)frames_len >= sizeof(encoder->frames_dir))) {
        free(encoder);
        return NULL;
    }
    // cppcheck-suppress misra-c2012-22.10
    if((make_dir(encoder->temp_dir) != 0) && (errno != EEXIST)) {
        free(encoder);
        return NULL;
    }
    // cppcheck-suppress misra-c2012-22.10
    if((make_dir(encoder->frames_dir) != 0) && (errno != EEXIST)) {
        (void)remove_dir(encoder->temp_dir);
        free(encoder);
        return NULL;
    }
    encoder->width = width;
    encoder->height = height;
    encoder->frame_bytes = pixels * 4u;
    encoder->byte_budget = byte_budget;
    if(!init_sync(encoder)) {
        (void)remove_dir(encoder->temp_dir);
        free(encoder);
        return NULL;
    }
    if(!start_workers(encoder)) {
        encoder_lock(encoder);
        encoder->stopping = true;
        encoder_signal_work(encoder);
        encoder_unlock(encoder);
        join_workers(encoder);
        destroy_sync(encoder);
        (void)remove_dir(encoder->temp_dir);
        free(encoder);
        return NULL;
    }
    return encoder;
}

int frame_encoder_submit(frame_encoder_t * encoder,
                         long frame_no,
                         const uint8_t * xrgb)
{
    if((encoder == NULL) || (xrgb == NULL) || (frame_no <= 0)) {
        return -1;
    }
    frame_job_t * job = NULL;

    encoder_lock(encoder);
    while(!encoder->stopping && !encoder->failed &&
          (encoder->pending_bytes > 0u) &&
          ((encoder->pending_bytes + encoder->frame_bytes)
           > encoder->byte_budget)) {
        encoder_wait_progress(encoder);
    }
    if(encoder->stopping || encoder->failed) {
        encoder_unlock(encoder);
        return -1;
    }
    encoder->pending_bytes += encoder->frame_bytes;
    encoder_unlock(encoder);

    job = (frame_job_t *)malloc(sizeof(*job));
    if(job != NULL) {
        job->pixels = (uint8_t *)malloc((size_t)encoder->frame_bytes);
    }
    if((job == NULL) || (job->pixels == NULL)) {
        if(job != NULL) {
            free(job);
        }
        rollback_bytes(encoder, encoder->frame_bytes);
        return -1;
    }
    memcpy(job->pixels, xrgb, (size_t)encoder->frame_bytes);
    job->frame_no = frame_no;
    job->bytes = encoder->frame_bytes;
    job->next = NULL;

    encoder_lock(encoder);
    if(encoder->stopping || encoder->failed) {
        encoder_unlock(encoder);
        free(job->pixels);
        free(job);
        rollback_bytes(encoder, encoder->frame_bytes);
        return -1;
    }
    if(encoder->tail == NULL) {
        encoder->head = job;
    }
    else {
        encoder->tail->next = job;
    }
    encoder->tail = job;
    encoder->pending_jobs++;
    encoder_signal_work(encoder);
    encoder_unlock(encoder);
    return 0;
}

void frame_encoder_drain(frame_encoder_t * encoder)
{
    if(encoder == NULL) {
        return;
    }
    encoder_lock(encoder);
    while(encoder->pending_jobs > 0) {
        encoder_wait_progress(encoder);
    }
    encoder_unlock(encoder);
}

void frame_encoder_stop(frame_encoder_t * encoder)
{
    if(encoder == NULL) {
        return;
    }
    frame_encoder_drain(encoder);
    encoder_lock(encoder);
    encoder->stopping = true;
    encoder_signal_work(encoder);
    encoder_unlock(encoder);
    join_workers(encoder);
    (void)remove_dir(encoder->temp_dir);
    destroy_sync(encoder);
    free(encoder);
}

bool frame_encoder_failed(frame_encoder_t * encoder)
{
    if(encoder == NULL) {
        return false;
    }
    encoder_lock(encoder);
    bool failed = encoder->failed;
    encoder_unlock(encoder);
    return failed;
}
