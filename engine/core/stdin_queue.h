/**
 * Line reader for the window main loop: a thread turns stdin into a queue the
 * window thread drains between message pumps, so window mode can keep handling
 * Win32 messages while waiting for protocol lines. Headless mode keeps using
 * blocking ``fgets`` directly.
 */

#ifndef STDIN_QUEUE_H
#define STDIN_QUEUE_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct stdin_queue stdin_queue_t;

/**
 * Start the reader thread. Returns NULL when the platform cannot provide one
 * (window mode is unavailable there anyway).
 */
stdin_queue_t * stdin_queue_start(void);

/**
 * Wait until a line is queued, EOF is reached, or ``timeout_ms`` elapses.
 * Returns 1 for data, 0 for timeout and -1 for EOF with an empty queue.
 */
int stdin_queue_wait(stdin_queue_t * queue, unsigned timeout_ms);

/**
 * Pop one line, or NULL when the queue is empty. The caller owns the string.
 * ``*eof`` reports that stdin closed (it may still have lines queued).
 */
char * stdin_queue_pop(stdin_queue_t * queue, bool * eof);

void stdin_queue_free(stdin_queue_t * queue);

#ifdef __cplusplus
}
#endif

#endif
