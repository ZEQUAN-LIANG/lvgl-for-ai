#ifndef INTRO_LAYOUT_H
#define INTRO_LAYOUT_H

#include "intro_ui.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

extern const intro_screen_t intro_screen_overview;
extern const intro_screen_t intro_screen_loop;
extern const intro_screen_t intro_screen_evidence;
extern const intro_screen_t intro_screen_inspector;
extern const intro_screen_t intro_screen_versions;
extern const intro_screen_t intro_screen_start;

extern const lv_image_dsc_t * const intro_frames[5];
extern const lv_image_dsc_t * const intro_watch_frames[8];

#endif
#endif
