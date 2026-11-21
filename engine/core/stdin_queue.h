#ifndef STDIN_QUEUE_H
#define STDIN_QUEUE_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct stdin_queue stdin_queue_t;

stdin_queue_t * stdin_queue_start(void);

int stdin_queue_wait(stdin_queue_t * queue, unsigned timeout_ms);

char * stdin_queue_pop(stdin_queue_t * queue, bool * eof);

void stdin_queue_free(stdin_queue_t * queue);

#ifdef __cplusplus
}
#endif

#endif
