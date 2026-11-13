#ifndef ZC_AUDIO_H
#define ZC_AUDIO_H

#include "zc_game.h"

#include <stdbool.h>

/* Real speaker output for the Huangshan Pi build.
 *
 * On the SiFli SDK build this opens audprc + audcodec, drives the on-chip DAC
 * into the AW8155 speaker amplifier, and mixes the game's procedural SFX in a
 * small RT-Thread audio thread.  Headless builds (and any board without
 * PA_USING_AW8155) compile to no-ops so the game remains portable.
 */
bool zc_audio_start(void);
void zc_audio_set_enabled(bool on);
void zc_audio_set_muted(bool muted);
bool zc_audio_is_started(void);
void zc_audio_play(zc_sfx_t id);

#endif /* ZC_AUDIO_H */
