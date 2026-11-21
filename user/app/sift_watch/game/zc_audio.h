#ifndef ZC_AUDIO_H
#define ZC_AUDIO_H

#include "zc_game.h"

#include <stdbool.h>

bool zc_audio_start(void);
void zc_audio_set_enabled(bool on);
void zc_audio_set_muted(bool muted);
bool zc_audio_is_started(void);
void zc_audio_play(zc_sfx_t id);

#endif
