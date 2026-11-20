#ifndef ZC_AUDIO_H
#define ZC_AUDIO_H

#include "zc_game.h"

#include <stdbool.h>

/* Real speaker output on the Huangshan Pi build: audprc + audcodec driving the
 * on-chip DAC into the AW8155 PA. Without PA_USING_AW8155 (headless builds) all
 * of these compile to no-ops. */
bool zc_audio_start(void);
void zc_audio_set_enabled(bool on);
void zc_audio_set_muted(bool muted);
bool zc_audio_is_started(void);
void zc_audio_play(zc_sfx_t id);

#endif
