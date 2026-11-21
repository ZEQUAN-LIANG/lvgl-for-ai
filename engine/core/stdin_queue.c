#include "stdin_queue.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <windows.h>

typedef struct stdin_node {
    char * line;
    struct stdin_node * next;
} stdin_node_t;

struct stdin_queue {
    CRITICAL_SECTION lock;
    HANDLE data_event;
    HANDLE thread;
    stdin_node_t * head;
    stdin_node_t * tail;
    bool eof;
};

static DWORD WINAPI stdin_reader(LPVOID parameter)
{
    stdin_queue_t * queue = (stdin_queue_t *)parameter;
    char buffer[1024];

    while(fgets(buffer, sizeof(buffer), stdin) != NULL) {
        size_t length = strlen(buffer);
        stdin_node_t * node = (stdin_node_t *)malloc(sizeof(*node));
        if(node == NULL) continue;
        node->line = (char *)malloc(length + 1u);
        if(node->line == NULL) {
            free(node);
            continue;
        }
        memcpy(node->line, buffer, length + 1u);
        node->next = NULL;

        EnterCriticalSection(&queue->lock);
        if(queue->tail == NULL) {
            queue->head = node;
        }
        else {
            queue->tail->next = node;
        }
        queue->tail = node;
        LeaveCriticalSection(&queue->lock);
        SetEvent(queue->data_event);
    }

    EnterCriticalSection(&queue->lock);
    queue->eof = true;
    LeaveCriticalSection(&queue->lock);
    SetEvent(queue->data_event);
    return 0;
}

stdin_queue_t * stdin_queue_start(void)
{
    stdin_queue_t * queue = (stdin_queue_t *)calloc(1, sizeof(*queue));
    if(queue == NULL) return NULL;

    InitializeCriticalSection(&queue->lock);
    queue->data_event = CreateEventW(NULL, FALSE, FALSE, NULL);
    if(queue->data_event == NULL) {
        DeleteCriticalSection(&queue->lock);
        free(queue);
        return NULL;
    }
    queue->thread = CreateThread(NULL, 0, stdin_reader, queue, 0, NULL);
    if(queue->thread == NULL) {
        CloseHandle(queue->data_event);
        DeleteCriticalSection(&queue->lock);
        free(queue);
        return NULL;
    }
    return queue;
}

int stdin_queue_wait(stdin_queue_t * queue, unsigned timeout_ms)
{
    if(queue == NULL) return -1;
    for(;;) {
        EnterCriticalSection(&queue->lock);
        bool has_line = queue->head != NULL;
        bool eof = queue->eof;
        LeaveCriticalSection(&queue->lock);
        if(has_line) return 1;
        if(eof) return -1;

        DWORD waited = WaitForSingleObject(queue->data_event, timeout_ms);
        if(waited == WAIT_TIMEOUT) return 0;
    }
}

char * stdin_queue_pop(stdin_queue_t * queue, bool * eof)
{
    if(eof != NULL) *eof = false;
    if(queue == NULL) return NULL;

    EnterCriticalSection(&queue->lock);
    stdin_node_t * node = queue->head;
    if(node != NULL) {
        queue->head = node->next;
        if(queue->head == NULL) queue->tail = NULL;
    }
    if(eof != NULL) *eof = queue->eof;
    LeaveCriticalSection(&queue->lock);

    if(node == NULL) return NULL;
    char * line = node->line;
    free(node);
    return line;
}

void stdin_queue_free(stdin_queue_t * queue)
{
    if(queue == NULL) return;

    EnterCriticalSection(&queue->lock);
    bool finished = queue->eof;
    LeaveCriticalSection(&queue->lock);
    if(!finished) return;

    WaitForSingleObject(queue->thread, 1000);
    CloseHandle(queue->thread);
    CloseHandle(queue->data_event);

    stdin_node_t * node = queue->head;
    while(node != NULL) {
        stdin_node_t * next = node->next;
        free(node->line);
        free(node);
        node = next;
    }
    DeleteCriticalSection(&queue->lock);
    free(queue);
}

#else

struct stdin_queue {
    int unused;
};

stdin_queue_t * stdin_queue_start(void)
{
    return NULL;
}

int stdin_queue_wait(stdin_queue_t * queue, unsigned timeout_ms)
{
    (void)queue;
    (void)timeout_ms;
    return -1;
}

char * stdin_queue_pop(stdin_queue_t * queue, bool * eof)
{
    (void)queue;
    if(eof != NULL) *eof = true;
    return NULL;
}

void stdin_queue_free(stdin_queue_t * queue)
{
    (void)queue;
}

#endif
