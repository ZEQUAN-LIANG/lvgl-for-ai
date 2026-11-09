/**
 * @file frame_encoder.h
 * Background PNG encoding: raw staging plus one FIFO worker.
 */

#ifndef FRAME_ENCODER_H
#define FRAME_ENCODER_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// cppcheck-suppress misra-c2012-2.5
#define FRAME_ENCODER_BUDGET_BYTES ((uint64_t)1u << 30)

typedef struct frame_encoder frame_encoder_t;

frame_encoder_t * frame_encoder_start(const char * session_dir,
                                      uint32_t width,
                                      uint32_t height,
                                      uint64_t byte_budget);

int frame_encoder_submit(frame_encoder_t * encoder,
                         long frame_no,
                         const uint8_t * xrgb);

void frame_encoder_drain(frame_encoder_t * encoder);

void frame_encoder_stop(frame_encoder_t * encoder);

bool frame_encoder_failed(frame_encoder_t * encoder);

long frame_encoder_pending(frame_encoder_t * encoder);

#ifdef __cplusplus
}
#endif

#endif /* FRAME_ENCODER_H */
