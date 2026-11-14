#ifndef INTRO_LAYOUT_H
#define INTRO_LAYOUT_H

#include "intro_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

extern const idx_screen_t idx_screen_overview;
extern const idx_screen_t idx_screen_loop;
extern const idx_screen_t idx_screen_evidence;
extern const idx_screen_t idx_screen_inspector;
extern const idx_screen_t idx_screen_versions;
extern const idx_screen_t idx_screen_start;

extern const lv_image_dsc_t * const idx_intro_frames[5];
extern const lv_image_dsc_t * const idx_watch_frames[8];

#endif
#endif /* INTRO_LAYOUT_H */
