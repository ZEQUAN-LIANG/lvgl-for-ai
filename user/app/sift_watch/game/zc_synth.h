#ifndef ZC_SYNTH_H
#define ZC_SYNTH_H

#include "zc_game.h"

#include <stdint.h>

/* Portable 16 kHz mono SFX synth.  No RTOS, no LVGL, no hardware: the SDK
 * audio thread and the PC WAV preview both use the same voices. */
void zc_synth_reset(void);
void zc_synth_play(zc_sfx_t id);
void zc_synth_fill(int16_t * out, int count);

#endif /* ZC_SYNTH_H */
