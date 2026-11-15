#ifndef ZC_SYNTH_H
#define ZC_SYNTH_H

#include "zc_game.h"

#include <stdint.h>

void zc_synth_reset(void);
void zc_synth_play(zc_sfx_t id);
void zc_synth_fill(int16_t * out, int count);

#endif
