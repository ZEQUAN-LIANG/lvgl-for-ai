#ifndef ZC_PRIV_H
#define ZC_PRIV_H

#include "zc_game.h"

#include <stdbool.h>
#include <stdint.h>

#define ZC_RGB565(r, g, b) \
    ((uint16_t)((((uint16_t)(r) & 0xF8U) << 8) | (((uint16_t)(g) & 0xFCU) << 3) | ((uint16_t)(b) >> 3)))

#define ZC_INK       ZC_RGB565(8, 11, 7)
#define ZC_INK2      ZC_RGB565(14, 19, 12)
#define ZC_PANEL     ZC_RGB565(18, 24, 15)
#define ZC_PANEL2    ZC_RGB565(26, 33, 20)
#define ZC_PANEL3    ZC_RGB565(35, 44, 25)
#define ZC_OLIVE_D   ZC_RGB565(43, 52, 30)
#define ZC_OLIVE     ZC_RGB565(72, 85, 44)
#define ZC_OLIVE_L   ZC_RGB565(104, 117, 60)
#define ZC_MOSS      ZC_RGB565(140, 155, 82)
#define ZC_ACID      ZC_RGB565(195, 217, 96)
#define ZC_ACID_D    ZC_RGB565(132, 149, 60)
#define ZC_ACID_DEEP ZC_RGB565(79, 95, 38)
#define ZC_BONE      ZC_RGB565(231, 219, 172)
#define ZC_BONE_D    ZC_RGB565(184, 173, 129)
#define ZC_BONE_DD   ZC_RGB565(120, 116, 86)
#define ZC_RUST      ZC_RGB565(183, 84, 50)
#define ZC_RED       ZC_RGB565(239, 96, 65)
#define ZC_RED_D     ZC_RGB565(142, 46, 36)
#define ZC_BLOOD     ZC_RGB565(121, 37, 31)
#define ZC_BLOOD_D   ZC_RGB565(77, 24, 21)
#define ZC_GOLD      ZC_RGB565(242, 199, 97)
#define ZC_ORANGE    ZC_RGB565(237, 149, 69)
#define ZC_CYAN      ZC_RGB565(134, 217, 196)
#define ZC_WHITE     ZC_RGB565(243, 236, 205)
#define ZC_SMOKE     ZC_RGB565(42, 46, 36)
#define ZC_BLACK     ZC_RGB565(0, 0, 0)

typedef enum {
    ZC_ALIGN_LEFT = 0,
    ZC_ALIGN_CENTER,
    ZC_ALIGN_RIGHT
} zc_align_t;

typedef struct {
    uint16_t * fb;
    uint16_t * backdrop;
    int w;
    int h;
    int dy;
    int safe;
    int ox;
    int oy;
    bool embedded;
    bool scanlines;
    const zc_hooks_t * hooks;
} zc_ctx_t;

extern zc_ctx_t zc;

#endif
