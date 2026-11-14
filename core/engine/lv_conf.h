/**
 * @file lv_conf.h
 * Configuration for the lvgl_engine host.
 *
 * Only settings that differ from LVGL's lv_conf_internal.h defaults live here.
 * The tool owns this file; user code must not edit it.
 */

#ifndef LV_CONF_H
#define LV_CONF_H

/* CMake defines LVGL_MAJOR_8 before add_subdirectory() for the 8.x
 * builds. 8.x and 9.x share no configuration vocabulary, so each version
 * family gets its own block. */
#ifdef LVGL_MAJOR_8

/* Runtime-sized headless display (default 800x600) at 32-bit color (flush
 * copies BGRX straight into the XRGB8888 framebuffer), 16 MiB LVGL heap. */
#define LV_COLOR_DEPTH 32
#define LV_MEM_CUSTOM 0
#define LV_MEM_SIZE (16U * 1024U * 1024U)
#define LV_USE_USER_DATA 1

/* LVGL logs and user printf both end up in engine.log via stdout/stderr. */
#define LV_USE_LOG 1
#define LV_LOG_LEVEL LV_LOG_LEVEL_WARN
#define LV_LOG_PRINTF 1
#define LV_USE_ASSERT_NULL 0
#define LV_USE_ASSERT_MALLOC 0
#define LV_USE_ASSERT_STYLE 0
#define LV_USE_ASSERT_MEM_INTEGRITY 0
#define LV_USE_ASSERT_OBJ 0

#define LV_USE_LABEL 1
#define LV_USE_BTN 1
#define LV_USE_IMG 1
/* Runtime FreeType TTF loading is part of the default host engine. */
#define LV_USE_FREETYPE 1
/* 8.x lodepng backs both the reference decoder and the full-frame PNG writer;
 * LV_USE_PNG is the only switch 8.3/8.4 expose for it. */
#define LV_USE_PNG 1
#define LV_USE_FLEX 1
#define LV_USE_GRID 1

#define LV_USE_THEME_DEFAULT 1
#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_MONTSERRAT_16 1
#define LV_FONT_MONTSERRAT_20 1

#define LV_BUILD_EXAMPLES 0
#define LV_BUILD_DEMOS 0

#else /* 9.x */

/* Runtime-sized XRGB8888 headless display (default 800x600), 16 MiB LVGL
 * heap. */
#define LV_COLOR_FORMAT_DEFAULT LV_COLOR_FORMAT_XRGB8888
#define LV_USE_STDLIB_MALLOC LV_STDLIB_BUILTIN
#define LV_MEM_SIZE (16 * 1024 * 1024U)
#define LV_USE_OS LV_OS_NONE

#define LV_USE_DRAW_SW 1
#define LV_DRAW_SW_SUPPORT_XRGB8888 1
#define LV_DRAW_SW_SUPPORT_ARGB8888 1
#define LV_DRAW_SW_SUPPORT_RGB565 1
#define LV_DRAW_SW_COMPLEX 1

/* LVGL logs and user printf both end up in engine.log via stdout/stderr. */
#define LV_USE_LOG 1
#define LV_LOG_LEVEL LV_LOG_LEVEL_WARN
#define LV_LOG_PRINTF 1

/* 9.2+ adapters enable object names so hit replies carry names. LVGL 9.1 has
 * no LV_USE_OBJ_NAME switch and no name API; the adapter conditionally leaves
 * hit empty there instead of inventing names. */
#define LV_USE_OBJ_NAME 1
#define LV_USE_OBJ_ID 0

#define LV_USE_LABEL 1
#define LV_USE_BUTTON 1
#define LV_USE_IMAGE 1
#define LV_USE_LODEPNG 1
/* Runtime FreeType TTF loading is part of the default host engine. */
#define LV_USE_FREETYPE 1
#define LV_USE_FLEX 1
#define LV_USE_GRID 1

#define LV_USE_THEME_DEFAULT 1
#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_MONTSERRAT_16 1
#define LV_FONT_MONTSERRAT_20 1

#define LV_USE_SNAPSHOT 0
#define LV_USE_TEST 0
#define LV_USE_ASSERT 0

#define LV_BUILD_EXAMPLES 0
#define LV_BUILD_DEMOS 0

#endif /* LVGL_MAJOR_8 */

#endif /* LV_CONF_H */
