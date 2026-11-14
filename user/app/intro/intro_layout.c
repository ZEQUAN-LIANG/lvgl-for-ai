#include "intro_layout.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "idx_img_frame_grid.h"
#include "idx_img_intro_01.h"
#include "idx_img_intro_02.h"
#include "idx_img_intro_03.h"
#include "idx_img_intro_04.h"
#include "idx_img_intro_05.h"
#include "idx_img_poster.h"
#include "idx_img_watch_01.h"
#include "idx_img_watch_02.h"
#include "idx_img_watch_03.h"
#include "idx_img_watch_04.h"
#include "idx_img_watch_05.h"
#include "idx_img_watch_06.h"
#include "idx_img_watch_07.h"
#include "idx_img_watch_08.h"
#include "idx_img_web_inspector.h"

/* Generated from the browser layout at 800x600. Do not edit by hand. */
static const intro_bg_t intro_bg_overview[] = {
    {0, INTRO_ACT_NONE, INTRO_TAG_EYEBROW, 129, 28, 22, 5, 5, 0x34d399, 0x000000, 0x000000, 0x34d399, 255, 0, 0, 0, 32767, 255, 7, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 255, 36, 18, 0x0a141e, 0x000000, 0x38bdf8, 0x000000, 178, 0, 87, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 205, 274, 85, 12, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_SCREEN_LOOP, INTRO_TAG_NONE, 255, 28, 308, 128, 38, 0x38bdf8, 0x000000, 0x38bdf8, 0x000000, 255, 0, 255, 1, 6, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_SCREEN_EVIDENCE, INTRO_TAG_NONE, 255, 165, 308, 158, 38, 0x0a141e, 0x000000, 0x2c4658, 0x000000, 140, 0, 255, 1, 6, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 370, 363, 78, 0x081018, 0x000000, 0x182734, 0x000000, 153, 0, 255, 1, 9, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 371, 120, 76, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 148, 371, 1, 76, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 41, 446, 22, 2, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 149, 371, 120, 76, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 269, 371, 1, 76, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 161, 446, 22, 2, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 282, 446, 22, 2, 0xfbbf24, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 423, 55, 349, 310, 0x0b1721, 0x070d13, 0x223746, 0x000000, 255, 1, 255, 1, 12, 255, 46, 22, -30, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 434, 72, 5, 5, 0xfb7185, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 32767, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 443, 72, 5, 5, 0xfbbf24, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 32767, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 452, 72, 5, 5, 0x34d399, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 32767, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 724, 65, 37, 18, 0x0a141e, 0x000000, 0xfb7185, 0x000000, 178, 0, 97, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_LED_RED, 245, 731, 72, 5, 5, 0xfb7185, 0x000000, 0x000000, 0xfb7185, 255, 0, 0, 0, 32767, 255, 6, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 432, 92, 331, 208, 0x000000, 0x000000, 0x20394c, 0x000000, 255, 0, 255, 1, 7, 0, 0, 0, 0, NULL},
    {1, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 433, 93, 329, 206, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, (const void *)&idx_img_web_inspector},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 441, 101, 79, 19, 0x040c12, 0x000000, 0x38bdf8, 0x000000, 209, 0, 76, 1, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 663, 271, 91, 19, 0x040c12, 0x000000, 0x38bdf8, 0x000000, 209, 0, 76, 1, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 476, 136, 174, 33, 0x000000, 0x000000, 0x38bdf8, 0x000000, 0, 0, 255, 1, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 476, 128, 15, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 2, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 464, 311, 242, 4, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 2, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 464, 311, 7, 4, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 2, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 432, 326, 331, 30, 0x38bdf8, 0x000000, 0x182734, 0x000000, 10, 0, 255, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 423, 374, 349, 36, 0x081018, 0x000000, 0x182734, 0x000000, 166, 0, 255, 1, 7, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 433, 383, 69, 18, 0x0a141e, 0x000000, 0x34d399, 0x000000, 178, 0, 87, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_LED_GREEN, 255, 440, 390, 5, 5, 0x34d399, 0x000000, 0x000000, 0x34d399, 255, 0, 0, 0, 32767, 255, 6, 0, 0, NULL},
};

static const intro_seg_t intro_seg_overview_0[] = {
    {"AI-FIRST LVGL · DEVELOPMENT & VERIFICATION", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_overview_1[] = {
    {"AI writes LVGL.", INTRO_F_DISP_42},
};
static const intro_seg_t intro_seg_overview_2[] = {
    {"AI ", INTRO_F_DISP_42},
};
static const intro_seg_t intro_seg_overview_3[] = {
    {"verifies", INTRO_F_DISP_42},
};
static const intro_seg_t intro_seg_overview_4[] = {
    {" it.", INTRO_F_DISP_42},
};
static const intro_seg_t intro_seg_overview_5[] = {
    {"A real headless LVGL host with virtual input and virtual time, ", INTRO_F_BODY_13},
};
static const intro_seg_t intro_seg_overview_6[] = {
    {"frame-by-frame session evidence, a web inspector, and an ", INTRO_F_BODY_13},
};
static const intro_seg_t intro_seg_overview_7[] = {
    {"export path to SiFli hardware. The tool provides evidence; ", INTRO_F_BODY_13},
};
static const intro_seg_t intro_seg_overview_8[] = {
    {"humans set the bar.", INTRO_F_BODY_13},
};
static const intro_seg_t intro_seg_overview_9[] = {
    {"HUMAN", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_10[] = {
    {"Humans provide intent, annotations, and acceptance ", INTRO_F_BODY_11},
};
static const intro_seg_t intro_seg_overview_11[] = {
    {"criteria. The source of truth is ", INTRO_F_BODY_11},
};
static const intro_seg_t intro_seg_overview_12[] = {
    {"user/app/**/*.c", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_overview_13[] = {
    {".", INTRO_F_BODY_11},
};
static const intro_seg_t intro_seg_overview_14[] = {
    {"EXPLORE THE LOOP ", INTRO_F_MONO_9B},
};
static const intro_seg_t intro_seg_overview_15[] = {
    {"→", INTRO_F_MONO_9B},
};
static const intro_seg_t intro_seg_overview_16[] = {
    {"READ SESSION EVIDENCE ", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_overview_17[] = {
    {"↘", INTRO_F_SYMBOL_8},
};
static const intro_seg_t intro_seg_overview_18[] = {
    {"01", INTRO_F_DISP_22},
};
static const intro_seg_t intro_seg_overview_19[] = {
    {"ENGINE / SESSION", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_20[] = {
    {"1 process", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_overview_21[] = {
    {"06", INTRO_F_DISP_22},
};
static const intro_seg_t intro_seg_overview_22[] = {
    {"LVGL VERSIONS", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_23[] = {
    {"9.6 ", INTRO_F_BODY_10},
    {"→", INTRO_F_SYMBOL_10},
    {" 8.3", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_overview_24[] = {
    {"0", INTRO_F_DISP_22},
};
static const intro_seg_t intro_seg_overview_25[] = {
    {"PASS-FAIL OUTPUTS", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_26[] = {
    {"Humans decide", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_overview_27[] = {
    {"EXHIBIT A · WEB INSPECTOR", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_28[] = {
    {"REC", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_29[] = {
    {"FRAME 0001 / 0305", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_30[] = {
    {"800 × 600 · t = 0 ms", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_31[] = {
    {"A1", INTRO_F_MONO_6B},
};
static const intro_seg_t intro_seg_overview_32[] = {
    {"000001", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_33[] = {
    {"000305", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_34[] = {
    {"305 F", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_35[] = {
    {"A1 / ANNOTATION", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_36[] = {
    {"Card spacing 16/12 px ", INTRO_F_BODY_10},
    {"→", INTRO_F_SYMBOL_10},
    {" unify to 12px.", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_overview_37[] = {
    {"SESSION OK", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_38[] = {
    {"coffee", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_39[] = {
    {"305 frames", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_40[] = {
    {"800 × 600", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_overview_41[] = {
    {"HUMAN DECIDES", INTRO_F_MONO_7},
};

static const intro_text_t intro_text_overview[] = {
    {41, 19, 252, 0, intro_seg_overview_0, 1, 0x7dd3fc, 255, 2, 0},
    {28, 45, 259, 0, intro_seg_overview_1, 1, 0xe8f1f8, 255, -2, 0},
    {28, 88, 44, 0, intro_seg_overview_2, 1, 0xe8f1f8, 255, -2, 0},
    {72, 88, 125, 0, intro_seg_overview_3, 1, 0x38bdf8, 255, -2, 0},
    {198, 88, 37, 0, intro_seg_overview_4, 1, 0xe8f1f8, 255, -2, 0},
    {28, 146, 340, 0, intro_seg_overview_5, 1, 0xb4c5d2, 255, 0, 0},
    {28, 170, 329, 0, intro_seg_overview_6, 1, 0xb4c5d2, 255, 0, 0},
    {28, 194, 329, 0, intro_seg_overview_7, 1, 0xb4c5d2, 255, 0, 0},
    {28, 219, 113, 0, intro_seg_overview_8, 1, 0xb4c5d2, 255, 0, 0},
    {35, 260, 22, 0, intro_seg_overview_9, 1, 0x38bdf8, 255, 0, 0},
    {72, 256, 234, 0, intro_seg_overview_10, 1, 0x8ea3b3, 255, 0, 0},
    {72, 273, 132, 0, intro_seg_overview_11, 1, 0x8ea3b3, 255, 0, 0},
    {208, 274, 80, 0, intro_seg_overview_12, 1, 0x7dd3fc, 255, 0, 0},
    {290, 273, 3, 0, intro_seg_overview_13, 1, 0x8ea3b3, 255, 0, 0},
    {43, 322, 84, 0, intro_seg_overview_14, 1, 0x041019, 255, 0, 0},
    {135, 322, 5, 0, intro_seg_overview_15, 1, 0x041019, 255, 0, 0},
    {180, 322, 111, 0, intro_seg_overview_16, 1, 0xb4c5d2, 255, 0, 0},
    {298, 322, 9, 0, intro_seg_overview_17, 1, 0xb4c5d2, 255, 0, 0},
    {41, 381, 18, 0, intro_seg_overview_18, 1, 0xe8f1f8, 255, -1, 0},
    {41, 408, 68, 0, intro_seg_overview_19, 1, 0x6b8091, 255, 0, 0},
    {41, 422, 36, 0, intro_seg_overview_20, 1, 0x8ea3b3, 255, 0, 0},
    {161, 381, 22, 0, intro_seg_overview_21, 1, 0xe8f1f8, 255, -1, 0},
    {161, 408, 55, 0, intro_seg_overview_22, 1, 0x6b8091, 255, 0, 0},
    {161, 422, 37, 0, intro_seg_overview_23, 3, 0x8ea3b3, 255, 0, 0},
    {282, 381, 11, 0, intro_seg_overview_24, 1, 0xfbbf24, 255, -1, 0},
    {282, 408, 72, 0, intro_seg_overview_25, 1, 0x6b8091, 255, 0, 0},
    {282, 422, 61, 0, intro_seg_overview_26, 1, 0x8ea3b3, 255, 0, 0},
    {465, 70, 109, 0, intro_seg_overview_27, 1, 0x6b8091, 255, 0, 0},
    {741, 70, 13, 0, intro_seg_overview_28, 1, 0xfb7185, 255, 0, 0},
    {447, 106, 67, 0, intro_seg_overview_29, 1, 0x7dd3fc, 255, 0, 0},
    {669, 276, 79, 0, intro_seg_overview_30, 1, 0x7dd3fc, 255, 0, 0},
    {480, 129, 7, 0, intro_seg_overview_31, 1, 0x041019, 255, 0, 0},
    {434, 308, 21, 0, intro_seg_overview_32, 1, 0x6b8091, 255, 0, 0},
    {714, 308, 21, 0, intro_seg_overview_33, 1, 0x6b8091, 255, 0, 0},
    {743, 308, 18, 0, intro_seg_overview_34, 1, 0x6b8091, 255, 0, 0},
    {441, 337, 63, 0, intro_seg_overview_35, 1, 0x38bdf8, 255, 0, 0},
    {511, 335, 149, 0, intro_seg_overview_36, 3, 0xb4c5d2, 255, 0, 0},
    {450, 388, 45, 0, intro_seg_overview_37, 1, 0x34d399, 255, 0, 0},
    {508, 388, 23, 0, intro_seg_overview_38, 1, 0xb4c5d2, 255, 0, 0},
    {537, 388, 38, 0, intro_seg_overview_39, 1, 0xb4c5d2, 255, 0, 0},
    {582, 388, 35, 0, intro_seg_overview_40, 1, 0xb4c5d2, 255, 0, 0},
    {705, 388, 57, 0, intro_seg_overview_41, 1, 0xfbbf24, 255, 0, 0},
};

const intro_screen_t intro_screen_overview = {
    intro_bg_overview, 31, intro_text_overview, 42, 466
};

/* Generated from the browser layout at 800x600. Do not edit by hand. */
static const intro_bg_t intro_bg_loop[] = {
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 16, 744, 95, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 110, 744, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 54, 40, 40, 0x38bdf8, 0x000000, 0x223746, 0x000000, 13, 0, 255, 1, 7, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 522, 32, 250, 62, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 522, 32, 1, 62, 0x223746, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 292, 129, 480, 425, 0x0d1822, 0x0a121a, 0x182734, 0x000000, 255, 1, 255, 1, 12, 255, 32, 14, -24, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 293, 130, 478, 38, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 293, 167, 478, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 712, 139, 46, 18, 0x0a141e, 0x000000, 0x34d399, 0x000000, 178, 0, 87, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_LED_GREEN, 255, 719, 146, 5, 5, 0x34d399, 0x000000, 0x000000, 0x34d399, 255, 0, 0, 0, 32767, 255, 6, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 110, 62, 2, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
};

static const intro_seg_t intro_seg_loop_0[] = {
    {"02", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_loop_1[] = {
    {"THE VERIFICATION LOOP", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_loop_2[] = {
    {"One session.", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_loop_3[] = {
    {"Six handoffs.", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_loop_4[] = {
    {"Modify ", INTRO_F_BODY_12},
    {"→", INTRO_F_SYMBOL_12},
    {" build ", INTRO_F_BODY_12},
    {"→", INTRO_F_SYMBOL_12},
    {" run ", INTRO_F_BODY_12},
    {"→", INTRO_F_SYMBOL_12},
    {" collect evidence ", INTRO_F_BODY_12},
    {"→", INTRO_F_SYMBOL_12},
    {" ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_loop_5[] = {
    {"decide ", INTRO_F_BODY_12},
    {"→", INTRO_F_SYMBOL_12},
    {" fix. The tool does not hardcode app ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_loop_6[] = {
    {"names, and it does not accept on your behalf.", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_loop_7[] = {
    {"LOOP CONSOLE", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_loop_8[] = {
    {"READY", INTRO_F_MONO_7},
};

static const intro_text_t intro_text_loop[] = {
    {42, 68, 11, 0, intro_seg_loop_0, 1, 0x38bdf8, 255, 0, 0},
    {91, 17, 118, 0, intro_seg_loop_1, 1, 0x6b8091, 255, 2, 0},
    {91, 37, 142, 0, intro_seg_loop_2, 1, 0xe8f1f8, 255, -1, 0},
    {91, 66, 143, 0, intro_seg_loop_3, 1, 0xe8f1f8, 255, -1, 0},
    {537, 35, 210, 0, intro_seg_loop_4, 9, 0x8ea3b3, 255, 0, 0},
    {537, 56, 219, 0, intro_seg_loop_5, 3, 0x8ea3b3, 255, 0, 0},
    {537, 76, 221, 0, intro_seg_loop_6, 1, 0x8ea3b3, 255, 0, 0},
    {306, 143, 59, 0, intro_seg_loop_7, 1, 0x6b8091, 255, 1, 0},
    {729, 144, 22, 0, intro_seg_loop_8, 1, 0x34d399, 255, 0, 0},
};

const intro_screen_t intro_screen_loop = {
    intro_bg_loop, 11, intro_text_loop, 9, 598
};

/* Generated from the browser layout at 800x600. Do not edit by hand. */
static const intro_bg_t intro_bg_evidence[] = {
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 16, 744, 95, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 110, 744, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 54, 40, 40, 0x38bdf8, 0x000000, 0x223746, 0x000000, 13, 0, 255, 1, 7, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 522, 32, 250, 62, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 522, 32, 1, 62, 0x223746, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 149, 744, 513, 0x0d1822, 0x0a121a, 0x182734, 0x000000, 255, 1, 255, 1, 11, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 150, 742, 38, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 186, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 526, 159, 33, 18, 0x0a141e, 0x000000, 0x34d399, 0x000000, 178, 0, 87, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_LED_GREEN, 255, 533, 166, 5, 5, 0x34d399, 0x000000, 0x000000, 0x34d399, 255, 0, 0, 0, 32767, 255, 6, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 565, 159, 59, 18, 0x0a141e, 0x000000, 0x223746, 0x000000, 178, 0, 255, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 630, 159, 54, 18, 0x0a141e, 0x000000, 0x223746, 0x000000, 178, 0, 255, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 690, 159, 68, 18, 0x0a141e, 0x000000, 0x38bdf8, 0x000000, 178, 0, 87, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 187, 742, 440, 0x060b10, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 38, 196, 724, 422, 0x04080c, 0x000000, 0x182734, 0x000000, 255, 0, 255, 1, 6, 0, 0, 0, 0, NULL},
    {1, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 46, 204, 708, 406, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, (const void *)&idx_img_frame_grid},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 203, 710, 1, 0x1d3446, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 610, 710, 1, 0x1d3446, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 203, 1, 408, 0x1d3446, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 754, 203, 1, 408, 0x1d3446, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 627, 742, 34, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 627, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 94, 643, 509, 4, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 2, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 94, 643, 5, 4, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 673, 636, 85, 17, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 673, 652, 85, 1, 0x38bdf8, 0x000000, 0x000000, 0x000000, 102, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 674, 744, 267, 0x0d1822, 0x0a121a, 0x182734, 0x000000, 255, 1, 255, 1, 12, 255, 32, 14, -24, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 675, 742, 31, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 705, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 706, 742, 184, 0x050a0f, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 889, 742, 50, 0x070e14, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 889, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 953, 744, 360, 0x0d1822, 0x0a121a, 0x182734, 0x000000, 255, 1, 255, 1, 12, 255, 32, 14, -24, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 1050, 710, 163, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 1050, 710, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 1051, 710, 54, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 1104, 710, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 78, 1081, 87, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 1105, 710, 54, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 1158, 710, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 1158, 710, 54, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 1211, 710, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 1221, 710, 33, 0x38bdf8, 0x000000, 0x182734, 0x000000, 8, 0, 255, 1, 6, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 257, 1232, 34, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 357, 1232, 53, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 45, 1264, 710, 33, 0xfbbf24, 0x000000, 0xfbbf24, 0x000000, 10, 0, 76, 1, 6, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 68, 1274, 53, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 110, 62, 2, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
};

static const intro_seg_t intro_seg_evidence_0[] = {
    {"03", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_evidence_1[] = {
    {"SESSION EVIDENCE", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_evidence_2[] = {
    {"Every frame is numbered.", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_evidence_3[] = {
    {"Evidence points back.", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_evidence_4[] = {
    {"A session is not a recording. It is a replayable, ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_evidence_5[] = {
    {"citable evidence directory. Only changed frames ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_evidence_6[] = {
    {"hit disk; frame numbers stay continuous.", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_evidence_7[] = {
    {"← Scroll horizontally for the full frame sheet →", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_8[] = {
    {"SESSION 20261114-095536-1D9D", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_9[] = {
    {"OK", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_10[] = {
    {"305 FRAMES", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_11[] = {
    {"800 × 600", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_12[] = {
    {"CHANGED ONLY", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_13[] = {
    {"FRAME 000001", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_14[] = {
    {"FRAME 000305", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_15[] = {
    {"Open full image ", INTRO_F_MONO_8},
    {"↗", INTRO_F_SYMBOL_8},
};
static const intro_seg_t intro_seg_evidence_16[] = {
    {"SESSIONS/<ID>/", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_17[] = {
    {"OPEN DIRECTORY", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_18[] = {
    {"sessions/20261114-095536-1d9d/", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_19[] = {
    {"├── manifest.json          ", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_20[] = {
    {"status / app / display / frame_count", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_21[] = {
    {"├── timeline.ndjson        ", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_22[] = {
    {"input events, frame spans, marks", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_23[] = {
    {"├── frame_diffs.ndjson     ", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_24[] = {
    {"changed bboxes per frame", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_25[] = {
    {"├── frames/                ", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_26[] = {
    {"full PNGs, changed frames only", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_27[] = {
    {"├── snapshots/             ", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_28[] = {
    {"named snapshots", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_29[] = {
    {"├── engine.log             ", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_30[] = {
    {"exact state printf'd by user C", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_31[] = {
    {"├── build.log              ", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_32[] = {
    {"build commands and compiler output", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_33[] = {
    {"├── annotations.json       ", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_34[] = {
    {"human annotations (optional)", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_35[] = {
    {"└── whiteboards.json       ", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_36[] = {
    {"whiteboards (optional)", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_37[] = {
    {"CLI --JSON · LAST LINE", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_38[] = {
    {"{\"session_id\":\"20261114-095536-1d9d\",\"session_dir\":\"sessions/20261114-095536-1d9d\",\"status\":\"ok\",\"app\":\"coffee\",\"display\":{\"width\":800,\"height\":600},\"frame_count\":305,\"error\":null}", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_39[] = {
    {"HOW AI READS IT", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_evidence_40[] = {
    {"Text and coordinates first.", INTRO_F_DISP_21},
};
static const intro_seg_t intro_seg_evidence_41[] = {
    {"Images on demand.", INTRO_F_DISP_21},
};
static const intro_seg_t intro_seg_evidence_42[] = {
    {"01", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_43[] = {
    {"Read the summary", INTRO_F_BODY_11B},
};
static const intro_seg_t intro_seg_evidence_44[] = {
    {"summarize_session", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_45[] = {
    {" returns the annotations / whiteboards index and key fields.", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_evidence_46[] = {
    {"02", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_47[] = {
    {"Read text and bboxes", INTRO_F_BODY_11B},
};
static const intro_seg_t intro_seg_evidence_48[] = {
    {"Notes, ranges and coordinates first; do not open images yet.", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_evidence_49[] = {
    {"03", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_evidence_50[] = {
    {"Open images on demand", INTRO_F_BODY_11B},
};
static const intro_seg_t intro_seg_evidence_51[] = {
    {"Full frames or crops; each region keeps the raw and annotated crop.", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_evidence_52[] = {
    {"!", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_53[] = {
    {"No object tree or property reads. Exact state is ", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_evidence_54[] = {
    {"printf", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_55[] = {
    {"'d by user C into ", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_evidence_56[] = {
    {"engine.log", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_57[] = {
    {" and becomes evidence.", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_evidence_58[] = {
    {"≠", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_59[] = {
    {"status: ok", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_evidence_60[] = {
    {" is not acceptance. It only means the session ended normally.", INTRO_F_BODY_10},
};

static const intro_text_t intro_text_evidence[] = {
    {42, 68, 11, 0, intro_seg_evidence_0, 1, 0x38bdf8, 255, 0, 0},
    {91, 17, 90, 0, intro_seg_evidence_1, 1, 0x6b8091, 255, 2, 0},
    {91, 37, 289, 0, intro_seg_evidence_2, 1, 0xe8f1f8, 255, -1, 0},
    {91, 66, 240, 0, intro_seg_evidence_3, 1, 0xe8f1f8, 255, -1, 0},
    {537, 35, 218, 0, intro_seg_evidence_4, 1, 0x8ea3b3, 255, 0, 0},
    {537, 56, 233, 0, intro_seg_evidence_5, 1, 0x8ea3b3, 255, 0, 0},
    {537, 76, 197, 0, intro_seg_evidence_6, 1, 0x8ea3b3, 255, 0, 0},
    {28, 130, 205, 0, intro_seg_evidence_7, 1, 0x6b8091, 255, 0, 0},
    {42, 163, 137, 0, intro_seg_evidence_8, 1, 0x6b8091, 255, 1, 0},
    {543, 164, 9, 0, intro_seg_evidence_9, 1, 0x34d399, 255, 0, 0},
    {572, 164, 45, 0, intro_seg_evidence_10, 1, 0x8ea3b3, 255, 0, 0},
    {637, 164, 40, 0, intro_seg_evidence_11, 1, 0x8ea3b3, 255, 0, 0},
    {697, 164, 54, 0, intro_seg_evidence_12, 1, 0x38bdf8, 255, 0, 0},
    {42, 640, 43, 0, intro_seg_evidence_13, 1, 0x6b8091, 255, 0, 0},
    {612, 640, 43, 0, intro_seg_evidence_14, 1, 0x6b8091, 255, 0, 0},
    {673, 638, 85, 0, intro_seg_evidence_15, 2, 0x38bdf8, 255, 0, 0},
    {42, 685, 69, 0, intro_seg_evidence_16, 1, 0x6b8091, 255, 1, 0},
    {689, 685, 69, 0, intro_seg_evidence_17, 1, 0x6b8091, 255, 1, 0},
    {42, 721, 148, 0, intro_seg_evidence_18, 1, 0x7dd3fc, 255, 0, 0},
    {42, 737, 134, 0, intro_seg_evidence_19, 1, 0xc6d8e5, 255, 0, 0},
    {176, 737, 178, 0, intro_seg_evidence_20, 1, 0x5c7284, 255, 0, 0},
    {42, 752, 134, 0, intro_seg_evidence_21, 1, 0xc6d8e5, 255, 0, 0},
    {176, 752, 158, 0, intro_seg_evidence_22, 1, 0x5c7284, 255, 0, 0},
    {42, 768, 134, 0, intro_seg_evidence_23, 1, 0xc6d8e5, 255, 0, 0},
    {176, 768, 119, 0, intro_seg_evidence_24, 1, 0x5c7284, 255, 0, 0},
    {42, 784, 134, 0, intro_seg_evidence_25, 1, 0xc6d8e5, 255, 0, 0},
    {176, 784, 148, 0, intro_seg_evidence_26, 1, 0x5c7284, 255, 0, 0},
    {42, 800, 134, 0, intro_seg_evidence_27, 1, 0xc6d8e5, 255, 0, 0},
    {176, 800, 74, 0, intro_seg_evidence_28, 1, 0x5c7284, 255, 0, 0},
    {42, 815, 134, 0, intro_seg_evidence_29, 1, 0xc6d8e5, 255, 0, 0},
    {176, 815, 148, 0, intro_seg_evidence_30, 1, 0x5c7284, 255, 0, 0},
    {42, 831, 134, 0, intro_seg_evidence_31, 1, 0xc6d8e5, 255, 0, 0},
    {176, 831, 168, 0, intro_seg_evidence_32, 1, 0x5c7284, 255, 0, 0},
    {42, 847, 134, 0, intro_seg_evidence_33, 1, 0xc6d8e5, 255, 0, 0},
    {176, 847, 139, 0, intro_seg_evidence_34, 1, 0x5c7284, 255, 0, 0},
    {42, 863, 134, 0, intro_seg_evidence_35, 1, 0xc6d8e5, 255, 0, 0},
    {176, 863, 109, 0, intro_seg_evidence_36, 1, 0x5c7284, 255, 0, 0},
    {42, 901, 97, 0, intro_seg_evidence_37, 1, 0x38bdf8, 255, 0, 0},
    {42, 917, 841, 716, intro_seg_evidence_38, 1, 0xa9c0d0, 255, 0, 2},
    {45, 970, 82, 0, intro_seg_evidence_39, 1, 0x38bdf8, 255, 1, 0},
    {45, 993, 226, 0, intro_seg_evidence_40, 1, 0xe8f1f8, 255, -1, 0},
    {45, 1016, 172, 0, intro_seg_evidence_41, 1, 0xe8f1f8, 255, -1, 0},
    {45, 1063, 8, 0, intro_seg_evidence_42, 1, 0x38bdf8, 255, 0, 0},
    {78, 1062, 88, 0, intro_seg_evidence_43, 1, 0xe8f1f8, 255, 0, 0},
    {81, 1081, 82, 0, intro_seg_evidence_44, 1, 0x7dd3fc, 255, 0, 0},
    {165, 1080, 237, 0, intro_seg_evidence_45, 1, 0x8ea3b3, 255, 0, 0},
    {45, 1117, 8, 0, intro_seg_evidence_46, 1, 0x38bdf8, 255, 0, 0},
    {78, 1116, 102, 0, intro_seg_evidence_47, 1, 0xe8f1f8, 255, 0, 0},
    {78, 1134, 242, 0, intro_seg_evidence_48, 1, 0x8ea3b3, 255, 0, 0},
    {45, 1170, 8, 0, intro_seg_evidence_49, 1, 0x38bdf8, 255, 0, 0},
    {78, 1170, 117, 0, intro_seg_evidence_50, 1, 0xe8f1f8, 255, 0, 0},
    {78, 1188, 273, 0, intro_seg_evidence_51, 1, 0x8ea3b3, 255, 0, 0},
    {55, 1232, 5, 0, intro_seg_evidence_52, 1, 0x38bdf8, 255, 0, 0},
    {68, 1231, 189, 0, intro_seg_evidence_53, 1, 0x8ea3b3, 255, 0, 0},
    {260, 1232, 29, 0, intro_seg_evidence_54, 1, 0x7dd3fc, 255, 0, 0},
    {291, 1231, 66, 0, intro_seg_evidence_55, 1, 0x8ea3b3, 255, 0, 0},
    {360, 1232, 48, 0, intro_seg_evidence_56, 1, 0x7dd3fc, 255, 0, 0},
    {410, 1231, 96, 0, intro_seg_evidence_57, 1, 0x8ea3b3, 255, 0, 0},
    {55, 1275, 5, 0, intro_seg_evidence_58, 1, 0xfbbf24, 255, 0, 0},
    {71, 1275, 48, 0, intro_seg_evidence_59, 1, 0x7dd3fc, 255, 0, 0},
    {121, 1274, 244, 0, intro_seg_evidence_60, 1, 0x8ea3b3, 255, 0, 0},
};

const intro_screen_t intro_screen_evidence = {
    intro_bg_evidence, 48, intro_text_evidence, 61, 1329
};

/* Generated from the browser layout at 800x600. Do not edit by hand. */
static const intro_bg_t intro_bg_inspector[] = {
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 16, 744, 95, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 110, 744, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 54, 40, 40, 0x38bdf8, 0x000000, 0x223746, 0x000000, 13, 0, 255, 1, 7, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 522, 32, 250, 62, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 522, 32, 1, 62, 0x223746, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 578, 35, 88, 14, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 68, 144, 664, 576, 0x0d1822, 0x0a121a, 0x182734, 0x000000, 255, 1, 255, 1, 12, 255, 32, 14, -24, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 69, 145, 662, 38, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 69, 182, 662, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 667, 154, 51, 18, 0x0a141e, 0x000000, 0x34d399, 0x000000, 178, 0, 87, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_LED_GREEN, 255, 674, 161, 5, 5, 0x34d399, 0x000000, 0x000000, 0x34d399, 255, 0, 0, 0, 32767, 255, 6, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 69, 183, 662, 501, 0x050a0f, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 77, 191, 646, 485, 0x000000, 0x000000, 0x20394c, 0x000000, 255, 0, 255, 1, 6, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 69, 684, 662, 36, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 69, 684, 662, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 655, 693, 63, 18, 0x0a141e, 0x000000, 0x223746, 0x000000, 178, 0, 255, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 904, 744, 178, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 904, 744, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 905, 744, 59, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 963, 744, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 964, 744, 59, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 1022, 744, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 1023, 744, 59, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 1081, 744, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 1094, 71, 19, 0x0a141e, 0x000000, 0x223746, 0x000000, 153, 0, 255, 1, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 104, 1094, 71, 19, 0x0a141e, 0x000000, 0x223746, 0x000000, 153, 0, 255, 1, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 180, 1094, 68, 19, 0x0a141e, 0x000000, 0x223746, 0x000000, 153, 0, 255, 1, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 253, 1094, 78, 19, 0x0a141e, 0x000000, 0x223746, 0x000000, 153, 0, 255, 1, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 336, 1094, 68, 19, 0x0a141e, 0x000000, 0x223746, 0x000000, 153, 0, 255, 1, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 1113, 266, 58, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 1113, 2, 58, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 40, 1136, 101, 13, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 110, 62, 2, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
};

static const intro_seg_t intro_seg_inspector_0[] = {
    {"04", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_inspector_1[] = {
    {"WEB INSPECTOR", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_inspector_2[] = {
    {"Humans circle problems.", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_inspector_3[] = {
    {"AI reads coordinates.", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_inspector_4[] = {
    {"Fixed at ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_inspector_5[] = {
    {"127.0.0.1:8765", INTRO_F_MONO_11},
};
static const intro_seg_t intro_seg_inspector_6[] = {
    {". Frames come from ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_inspector_7[] = {
    {"the real runtime: live during a session, replayed ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_inspector_8[] = {
    {"from evidence after it ends.", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_inspector_9[] = {
    {"DEFAULT INTRO / RECORDED SESSION", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_10[] = {
    {"REPLAY", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_11[] = {
    {"user/app/intro", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_12[] = {
    {"·", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_13[] = {
    {"user/scenarios/intro.json", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_14[] = {
    {"REAL FRAMES", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_15[] = {
    {"LIVE OR REPLAY", INTRO_F_MONO_11},
};
static const intro_seg_t intro_seg_inspector_16[] = {
    {"Frames, not a re-render.", INTRO_F_DISP_23},
};
static const intro_seg_t intro_seg_inspector_17[] = {
    {"The web layer only does HTTP / UI adaptation. Replay ", INTRO_F_BODY_11},
};
static const intro_seg_t intro_seg_inspector_18[] = {
    {"uses Recording; live uses an independent Runtime. You ", INTRO_F_BODY_11},
};
static const intro_seg_t intro_seg_inspector_19[] = {
    {"are looking at frames drawn by LVGL — not a web ", INTRO_F_BODY_11},
};
static const intro_seg_t intro_seg_inspector_20[] = {
    {"reimplementation.", INTRO_F_BODY_11},
};
static const intro_seg_t intro_seg_inspector_21[] = {
    {"01", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_22[] = {
    {"Preview", INTRO_F_DISP_14},
};
static const intro_seg_t intro_seg_inspector_23[] = {
    {"Starts read-only. The live frame stream is observation only; it is not retained or added to evidence.", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_inspector_24[] = {
    {"02", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_25[] = {
    {"Annotation", INTRO_F_DISP_14},
};
static const intro_seg_t intro_seg_inspector_26[] = {
    {"Single frame or time range. Each region stores a bbox, the raw crop and the annotated crop.", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_inspector_27[] = {
    {"03", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_28[] = {
    {"Whiteboard", INTRO_F_DISP_14},
};
static const intro_seg_t intro_seg_inspector_29[] = {
    {"frame / range / global scopes. Text or labels are required; images and words reach AI together.", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_inspector_30[] = {
    {"annotations.json", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_31[] = {
    {"whiteboards.json", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_32[] = {
    {"timeline.ndjson", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_33[] = {
    {"frame_diffs.ndjson", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_34[] = {
    {"user/app/**/*.c", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_inspector_35[] = {
    {"No second protocol client: web, CLI and ", INTRO_F_BODY_11},
};
static const intro_seg_t intro_seg_inspector_36[] = {
    {"session_report.py", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_inspector_37[] = {
    {" share Runtime / Recording / ", INTRO_F_BODY_11},
};
static const intro_seg_t intro_seg_inspector_38[] = {
    {"summarize_session.", INTRO_F_BODY_11},
};

static const intro_text_t intro_text_inspector[] = {
    {42, 68, 11, 0, intro_seg_inspector_0, 1, 0x38bdf8, 255, 0, 0},
    {91, 17, 73, 0, intro_seg_inspector_1, 1, 0x6b8091, 255, 2, 0},
    {91, 37, 281, 0, intro_seg_inspector_2, 1, 0xe8f1f8, 255, -1, 0},
    {91, 66, 237, 0, intro_seg_inspector_3, 1, 0xe8f1f8, 255, -1, 0},
    {537, 35, 41, 0, intro_seg_inspector_4, 1, 0x8ea3b3, 255, 0, 0},
    {581, 36, 81, 0, intro_seg_inspector_5, 1, 0x7dd3fc, 255, 0, 0},
    {666, 35, 97, 0, intro_seg_inspector_6, 1, 0x8ea3b3, 255, 0, 0},
    {537, 56, 228, 0, intro_seg_inspector_7, 1, 0x8ea3b3, 255, 0, 0},
    {537, 76, 134, 0, intro_seg_inspector_8, 1, 0x8ea3b3, 255, 0, 0},
    {82, 158, 157, 0, intro_seg_inspector_9, 1, 0x6b8091, 255, 1, 0},
    {684, 159, 27, 0, intro_seg_inspector_10, 1, 0x34d399, 255, 0, 0},
    {82, 697, 50, 0, intro_seg_inspector_11, 1, 0x6b8091, 255, 0, 0},
    {138, 697, 4, 0, intro_seg_inspector_12, 1, 0x6b8091, 255, 0, 0},
    {148, 697, 89, 0, intro_seg_inspector_13, 1, 0x6b8091, 255, 0, 0},
    {662, 698, 49, 0, intro_seg_inspector_14, 1, 0x8ea3b3, 255, 0, 0},
    {28, 762, 112, 0, intro_seg_inspector_15, 1, 0x8ea3b3, 255, 2, 0},
    {28, 778, 234, 0, intro_seg_inspector_16, 1, 0xe8f1f8, 255, -1, 0},
    {28, 816, 247, 0, intro_seg_inspector_17, 1, 0x8ea3b3, 255, 0, 0},
    {28, 835, 255, 0, intro_seg_inspector_18, 1, 0x8ea3b3, 255, 0, 0},
    {28, 855, 232, 0, intro_seg_inspector_19, 1, 0x8ea3b3, 255, 0, 0},
    {28, 874, 86, 0, intro_seg_inspector_20, 1, 0x8ea3b3, 255, 0, 0},
    {28, 917, 8, 0, intro_seg_inspector_21, 1, 0x38bdf8, 255, 0, 0},
    {61, 918, 49, 0, intro_seg_inspector_22, 1, 0xe8f1f8, 255, 0, 0},
    {61, 940, 391, 0, intro_seg_inspector_23, 1, 0x8ea3b3, 255, 0, 0},
    {28, 976, 8, 0, intro_seg_inspector_24, 1, 0x38bdf8, 255, 0, 0},
    {61, 977, 66, 0, intro_seg_inspector_25, 1, 0xe8f1f8, 255, 0, 0},
    {61, 999, 369, 0, intro_seg_inspector_26, 1, 0x8ea3b3, 255, 0, 0},
    {28, 1035, 8, 0, intro_seg_inspector_27, 1, 0x38bdf8, 255, 0, 0},
    {61, 1036, 70, 0, intro_seg_inspector_28, 1, 0xe8f1f8, 255, 0, 0},
    {61, 1058, 376, 0, intro_seg_inspector_29, 1, 0x8ea3b3, 255, 0, 0},
    {35, 1099, 57, 0, intro_seg_inspector_30, 1, 0xb4c5d2, 255, 0, 0},
    {111, 1099, 57, 0, intro_seg_inspector_31, 1, 0xb4c5d2, 255, 0, 0},
    {187, 1099, 54, 0, intro_seg_inspector_32, 1, 0xb4c5d2, 255, 0, 0},
    {260, 1099, 64, 0, intro_seg_inspector_33, 1, 0xb4c5d2, 255, 0, 0},
    {343, 1099, 54, 0, intro_seg_inspector_34, 1, 0xb4c5d2, 255, 0, 0},
    {40, 1116, 184, 0, intro_seg_inspector_35, 1, 0x8ea3b3, 255, 0, 0},
    {43, 1136, 95, 0, intro_seg_inspector_36, 1, 0x7dd3fc, 255, 0, 0},
    {141, 1135, 130, 0, intro_seg_inspector_37, 1, 0x8ea3b3, 255, 0, 0},
    {40, 1155, 93, 0, intro_seg_inspector_38, 1, 0x8ea3b3, 255, 0, 0},
};

const intro_screen_t intro_screen_inspector = {
    intro_bg_inspector, 33, intro_text_inspector, 39, 1187
};

/* Generated from the browser layout at 800x600. Do not edit by hand. */
static const intro_bg_t intro_bg_versions[] = {
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 16, 744, 95, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 110, 744, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 54, 40, 40, 0x38bdf8, 0x000000, 0x223746, 0x000000, 13, 0, 255, 1, 7, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 522, 32, 250, 62, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 522, 32, 1, 62, 0x223746, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 129, 744, 464, 0x0d1822, 0x0a121a, 0x182734, 0x000000, 255, 1, 255, 1, 12, 255, 32, 14, -24, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 145, 712, 31, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 175, 712, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 365, 487, 32, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 493, 487, 32, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 512, 712, 66, 0x38bdf8, 0x000000, 0x223746, 0x000000, 6, 0, 255, 1, 6, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 134, 554, 50, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 213, 554, 69, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 286, 554, 41, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 605, 744, 556, 0x0d1822, 0x0a121a, 0x182734, 0x000000, 255, 1, 255, 1, 12, 255, 32, 14, -24, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 606, 742, 38, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 643, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 694, 615, 64, 18, 0x0a141e, 0x000000, 0x34d399, 0x000000, 178, 0, 87, 1, 4, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_LED_GREEN, 255, 701, 622, 5, 5, 0x34d399, 0x000000, 0x000000, 0x34d399, 255, 0, 0, 0, 32767, 255, 6, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 644, 742, 385, 0x060c11, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 40, 655, 205, 363, 0x000000, 0x000000, 0x223746, 0x000000, 255, 0, 255, 1, 6, 0, 0, 0, 0, NULL},
    {1, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 41, 656, 203, 361, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, (const void *)&idx_img_poster},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 47, 997, 46, 13, 0x040c12, 0x000000, 0x000000, 0x000000, 209, 0, 0, 0, 2, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 258, 706, 502, 57, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 258, 706, 502, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 258, 772, 502, 47, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 258, 772, 502, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 258, 827, 104, 17, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 258, 842, 104, 1, 0x38bdf8, 0x000000, 0x000000, 0x000000, 102, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 40, 1028, 720, 80, 0x050a0f, 0x000000, 0x182734, 0x000000, 255, 0, 255, 1, 5, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 41, 1029, 718, 26, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 41, 1055, 718, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 41, 1056, 718, 26, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 41, 1081, 718, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 40, 1116, 720, 32, 0xfbbf24, 0x000000, 0xfbbf24, 0x000000, 10, 0, 76, 1, 5, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 524, 1127, 46, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 110, 62, 2, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
};

static const intro_seg_t intro_seg_versions_0[] = {
    {"05", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_versions_1[] = {
    {"VERSIONS & HARDWARE", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_2[] = {
    {"Versions and hardware", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_versions_3[] = {
    {"both count.", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_versions_4[] = {
    {"The same user/app and the same scenario run ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_versions_5[] = {
    {"on six LVGL versions. Device apps target the 9.4 ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_versions_6[] = {
    {"baseline.", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_versions_7[] = {
    {"VERSION MATRIX", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_8[] = {
    {"06 / TARGETS", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_9[] = {
    {"ONE APP · SIX VERSIONS", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_10[] = {
    {"One source.", INTRO_F_DISP_22},
};
static const intro_seg_t intro_seg_versions_11[] = {
    {"Six targets.", INTRO_F_DISP_22},
};
static const intro_seg_t intro_seg_versions_12[] = {
    {"Cross-version comparison covers event semantics and the session file set, not pixels. ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_versions_13[] = {
    {"--lvgl", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_14[] = {
    {" wins over the scenario's ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_versions_15[] = {
    {"\"lvgl\"", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_16[] = {
    {" field.", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_versions_17[] = {
    {"PREBUILT HOST SDK", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_18[] = {
    {"Runs with only GCC: ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_versions_19[] = {
    {"--prebuilt", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_20[] = {
    {" reuses ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_versions_21[] = {
    {"sdk/<version>/", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_22[] = {
    {"; ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_versions_23[] = {
    {"--source", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_24[] = {
    {" forces CMake.", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_versions_25[] = {
    {"EXHIBIT E · HUANGSHAN PAI (SIFLI)", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_26[] = {
    {"ON DEVICE", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_27[] = {
    {"DEVICE CLIP", INTRO_F_MONO_6},
};
static const intro_seg_t intro_seg_versions_28[] = {
    {"SIFLI SF32LB52X", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_29[] = {
    {"390", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_versions_30[] = {
    {"×", INTRO_F_DISP_14},
};
static const intro_seg_t intro_seg_versions_31[] = {
    {"450", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_versions_32[] = {
    {"BOARD", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_33[] = {
    {"sf32lb52-lchspi-ulp", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_34[] = {
    {"SCREEN", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_35[] = {
    {"390 × 450", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_36[] = {
    {"SOURCE", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_37[] = {
    {"user/app/sift_watch", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_38[] = {
    {"sift_watch", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_39[] = {
    {"Real LVGL frames · 390 × 450", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_versions_40[] = {
    {"Watch hardware clip ", INTRO_F_MONO_8},
    {"↗", INTRO_F_SYMBOL_8},
};
static const intro_seg_t intro_seg_versions_41[] = {
    {"EXPORT", INTRO_F_MONO_6},
};
static const intro_seg_t intro_seg_versions_42[] = {
    {"python -I chip-adapt/sifli/export.py sift_watch --dry-run --force", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_43[] = {
    {"BUILD", INTRO_F_MONO_6},
};
static const intro_seg_t intro_seg_versions_44[] = {
    {"python -I chip-adapt/sifli/host/cli.py build --app sift_watch --actor ai --json", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_45[] = {
    {"FLASH", INTRO_F_MONO_6},
};
static const intro_seg_t intro_seg_versions_46[] = {
    {"python -I chip-adapt/sifli/host/cli.py flash --app sift_watch --actor ai --json", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_47[] = {
    {"!", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_versions_48[] = {
    {"Without a board, stop at host verification and an export dry-run. ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_versions_49[] = {
    {"Never claim the device is verified.", INTRO_F_BODY_9B},
};
static const intro_seg_t intro_seg_versions_50[] = {
    {" Shared source stays in ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_versions_51[] = {
    {"user/app/", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_versions_52[] = {
    {".", INTRO_F_BODY_9},
};

static const intro_text_t intro_text_versions[] = {
    {42, 68, 11, 0, intro_seg_versions_0, 1, 0x38bdf8, 255, 0, 0},
    {91, 17, 107, 0, intro_seg_versions_1, 1, 0x6b8091, 255, 2, 0},
    {91, 37, 260, 0, intro_seg_versions_2, 1, 0xe8f1f8, 255, -1, 0},
    {91, 66, 123, 0, intro_seg_versions_3, 1, 0xe8f1f8, 255, -1, 0},
    {537, 35, 221, 0, intro_seg_versions_4, 1, 0x8ea3b3, 255, 0, 0},
    {537, 56, 231, 0, intro_seg_versions_5, 1, 0x8ea3b3, 255, 0, 0},
    {537, 76, 43, 0, intro_seg_versions_6, 1, 0x8ea3b3, 255, 0, 0},
    {57, 155, 69, 0, intro_seg_versions_7, 1, 0x6b8091, 255, 1, 0},
    {684, 155, 59, 0, intro_seg_versions_8, 1, 0x6b8091, 255, 1, 0},
    {44, 189, 120, 0, intro_seg_versions_9, 1, 0x38bdf8, 255, 1, 0},
    {44, 212, 108, 0, intro_seg_versions_10, 1, 0xe8f1f8, 255, -1, 0},
    {44, 236, 102, 0, intro_seg_versions_11, 1, 0xe8f1f8, 255, -1, 0},
    {44, 487, 321, 0, intro_seg_versions_12, 1, 0x6b8091, 255, 0, 0},
    {368, 488, 27, 0, intro_seg_versions_13, 1, 0x7dd3fc, 255, 0, 0},
    {397, 487, 95, 0, intro_seg_versions_14, 1, 0x6b8091, 255, 0, 0},
    {495, 488, 27, 0, intro_seg_versions_15, 1, 0x7dd3fc, 255, 0, 0},
    {525, 487, 21, 0, intro_seg_versions_16, 1, 0x6b8091, 255, 0, 0},
    {56, 534, 76, 0, intro_seg_versions_17, 1, 0x38bdf8, 255, 0, 0},
    {56, 554, 78, 0, intro_seg_versions_18, 1, 0x8ea3b3, 255, 0, 0},
    {136, 555, 46, 0, intro_seg_versions_19, 1, 0x7dd3fc, 255, 0, 0},
    {184, 554, 29, 0, intro_seg_versions_20, 1, 0x8ea3b3, 255, 0, 0},
    {215, 555, 64, 0, intro_seg_versions_21, 1, 0x7dd3fc, 255, 0, 0},
    {281, 554, 4, 0, intro_seg_versions_22, 1, 0x8ea3b3, 255, 0, 0},
    {288, 555, 36, 0, intro_seg_versions_23, 1, 0x7dd3fc, 255, 0, 0},
    {327, 554, 56, 0, intro_seg_versions_24, 1, 0x8ea3b3, 255, 0, 0},
    {42, 619, 162, 0, intro_seg_versions_25, 1, 0x6b8091, 255, 1, 0},
    {711, 620, 40, 0, intro_seg_versions_26, 1, 0x34d399, 255, 0, 0},
    {51, 1000, 38, 0, intro_seg_versions_27, 1, 0x7dd3fc, 255, 0, 0},
    {258, 656, 67, 0, intro_seg_versions_28, 1, 0x38bdf8, 255, 0, 0},
    {258, 670, 39, 0, intro_seg_versions_29, 1, 0xe8f1f8, 255, -1, 0},
    {298, 678, 5, 0, intro_seg_versions_30, 1, 0x38bdf8, 255, -1, 0},
    {304, 670, 41, 0, intro_seg_versions_31, 1, 0xe8f1f8, 255, -1, 0},
    {258, 717, 20, 0, intro_seg_versions_32, 1, 0x6b8091, 255, 0, 0},
    {682, 716, 78, 0, intro_seg_versions_33, 1, 0xb4c5d2, 255, 0, 0},
    {258, 734, 25, 0, intro_seg_versions_34, 1, 0x6b8091, 255, 0, 0},
    {723, 733, 37, 0, intro_seg_versions_35, 1, 0xb4c5d2, 255, 0, 0},
    {258, 752, 25, 0, intro_seg_versions_36, 1, 0x6b8091, 255, 0, 0},
    {682, 751, 78, 0, intro_seg_versions_37, 1, 0xb4c5d2, 255, 0, 0},
    {298, 790, 36, 0, intro_seg_versions_38, 1, 0xb4c5d2, 255, 0, 0},
    {298, 800, 100, 0, intro_seg_versions_39, 1, 0x6b8091, 255, 0, 0},
    {258, 829, 104, 0, intro_seg_versions_40, 2, 0x38bdf8, 255, 0, 0},
    {50, 1037, 23, 0, intro_seg_versions_41, 1, 0x38bdf8, 255, 0, 0},
    {100, 1037, 268, 0, intro_seg_versions_42, 1, 0xa9c0d0, 255, 0, 0},
    {50, 1064, 19, 0, intro_seg_versions_43, 1, 0x38bdf8, 255, 0, 0},
    {100, 1064, 326, 0, intro_seg_versions_44, 1, 0xa9c0d0, 255, 0, 0},
    {50, 1090, 19, 0, intro_seg_versions_45, 1, 0x38bdf8, 255, 0, 0},
    {100, 1090, 326, 0, intro_seg_versions_46, 1, 0xa9c0d0, 255, 0, 0},
    {50, 1127, 5, 0, intro_seg_versions_47, 1, 0xfbbf24, 255, 0, 0},
    {62, 1126, 245, 0, intro_seg_versions_48, 1, 0xe8c990, 255, 0, 0},
    {307, 1126, 129, 0, intro_seg_versions_49, 1, 0xfbbf24, 255, 0, 0},
    {436, 1126, 88, 0, intro_seg_versions_50, 1, 0xe8c990, 255, 0, 0},
    {526, 1127, 41, 0, intro_seg_versions_51, 1, 0x7dd3fc, 255, 0, 0},
    {570, 1126, 2, 0, intro_seg_versions_52, 1, 0xe8c990, 255, 0, 0},
};

const intro_screen_t intro_screen_versions = {
    intro_bg_versions, 37, intro_text_versions, 53, 1177
};

/* Generated from the browser layout at 800x600. Do not edit by hand. */
static const intro_bg_t intro_bg_start[] = {
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 16, 744, 66, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 81, 744, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 25, 40, 40, 0x38bdf8, 0x000000, 0x223746, 0x000000, 13, 0, 255, 1, 7, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 522, 24, 250, 41, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 522, 24, 1, 41, 0x223746, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 618, 27, 70, 14, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 706, 48, 59, 14, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 100, 744, 285, 0x050a0f, 0x000000, 0x223746, 0x000000, 255, 0, 255, 1, 10, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 101, 742, 29, 0x0a121a, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 129, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 40, 112, 5, 5, 0xfb7185, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 32767, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 49, 112, 5, 5, 0xfbbf24, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 32767, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 58, 112, 5, 5, 0x34d399, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 32767, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 133, 742, 45, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 176, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 153, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 177, 742, 45, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 221, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 153, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 222, 742, 45, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 265, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 153, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 266, 742, 45, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 310, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 153, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 357, 742, 26, 0x070e14, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 357, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 396, 744, 247, 0x0d1822, 0x0a121a, 0x182734, 0x000000, 255, 1, 255, 1, 12, 255, 32, 14, -24, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 478, 354, 39, 0x081018, 0x000000, 0x182734, 0x000000, 128, 0, 255, 1, 5, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 402, 478, 354, 39, 0x081018, 0x000000, 0x182734, 0x000000, 128, 0, 255, 1, 5, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 522, 354, 39, 0x081018, 0x000000, 0x182734, 0x000000, 128, 0, 255, 1, 5, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 402, 522, 354, 39, 0x081018, 0x000000, 0x182734, 0x000000, 128, 0, 255, 1, 5, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 567, 354, 39, 0x081018, 0x000000, 0x182734, 0x000000, 128, 0, 255, 1, 5, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 402, 567, 354, 39, 0x081018, 0x000000, 0x182734, 0x000000, 128, 0, 255, 1, 5, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 204, 615, 19, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 655, 744, 175, 0x0d1822, 0x0a121a, 0x182734, 0x000000, 255, 1, 255, 1, 12, 255, 32, 14, -24, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 229, 740, 68, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 316, 740, 48, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 438, 740, 77, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 760, 712, 24, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 760, 712, 1, 0x223746, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 143, 770, 82, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 44, 797, 124, 17, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 813, 124, 1, 0x38bdf8, 0x000000, 0x000000, 0x000000, 102, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 842, 744, 386, 0x0d1822, 0x0a121a, 0x182734, 0x000000, 255, 1, 255, 1, 12, 255, 32, 14, -24, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 843, 742, 31, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 29, 873, 742, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 876, 356, 116, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 399, 876, 1, 116, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 218, 943, 50, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 101, 957, 37, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 144, 957, 78, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 478, 943, 32, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 425, 957, 41, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 992, 356, 103, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 992, 356, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 399, 992, 1, 103, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 400, 992, 356, 103, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 400, 992, 356, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 475, 1060, 41, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 587, 1060, 32, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 1095, 356, 117, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 44, 1095, 356, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 399, 1095, 1, 117, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 400, 1095, 356, 117, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 400, 1095, 356, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 601, 1163, 60, 11, 0x38bdf8, 0x000000, 0x000000, 0x000000, 20, 0, 0, 0, 3, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 1242, 744, 83, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 1242, 744, 1, 0x182734, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 28, 1289, 27, 15, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 73, 1289, 31, 15, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 122, 1289, 40, 15, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 179, 1289, 44, 15, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 242, 1289, 53, 15, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 313, 1289, 40, 15, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 370, 1289, 22, 15, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_LOG, INTRO_TAG_NONE, 255, 411, 1289, 34, 15, 0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
    {0, INTRO_ACT_NONE, INTRO_TAG_NONE, 255, 28, 81, 62, 2, 0x38bdf8, 0x000000, 0x000000, 0x000000, 255, 0, 0, 0, 0, 0, 0, 0, 0, NULL},
};

static const intro_seg_t intro_seg_start_0[] = {
    {"06", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_start_1[] = {
    {"QUICK START", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_2[] = {
    {"From zero to the first frame.", INTRO_F_DISP_27},
};
static const intro_seg_t intro_seg_start_3[] = {
    {"Python ≥ 3.9, no ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_start_4[] = {
    {"pip install", INTRO_F_MONO_11},
};
static const intro_seg_t intro_seg_start_5[] = {
    {". Run every ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_start_6[] = {
    {"command from the repo root with ", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_start_7[] = {
    {"python -I", INTRO_F_MONO_11},
};
static const intro_seg_t intro_seg_start_8[] = {
    {".", INTRO_F_BODY_12},
};
static const intro_seg_t intro_seg_start_9[] = {
    {"lvgl-for-agent — bash", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_10[] = {
    {"SELECT TO COPY", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_11[] = {
    {"01", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_12[] = {
    {"# clone and enter the repository", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_13[] = {
    {"git clone https://gitee.com/liang-zequan/lvgl-for-ai.git lvgl-for-agent && cd lvgl-for-agent", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_start_14[] = {
    {"02", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_15[] = {
    {"# fetch LVGL 9.6; default source=auto tries codeload, then the Gitee mirror", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_16[] = {
    {"python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root .", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_start_17[] = {
    {"03", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_18[] = {
    {"# fetch PNG encoder dependencies (zlib / libpng)", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_19[] = {
    {"python -I core/tools/fetch_png.py --repo-root .", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_start_20[] = {
    {"04", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_21[] = {
    {"# run a scenario; the first run builds the engine", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_22[] = {
    {"python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_start_23[] = {
    {"05", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_24[] = {
    {"# open the web inspector: live preview, replay, annotations, whiteboards", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_25[] = {
    {"python -I core/web.py --open", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_start_26[] = {
    {"python -I · no pip install", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_27[] = {
    {"First build usually takes a few minutes", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_28[] = {
    {"REQUIREMENTS", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_29[] = {
    {"You need", INTRO_F_DISP_20},
};
static const intro_seg_t intro_seg_start_30[] = {
    {"PYTHON", INTRO_F_MONO_6},
};
static const intro_seg_t intro_seg_start_31[] = {
    {"≥ 3.9 · no pip", INTRO_F_BODY_9B},
};
static const intro_seg_t intro_seg_start_32[] = {
    {"GCC", INTRO_F_MONO_6},
};
static const intro_seg_t intro_seg_start_33[] = {
    {"MinGW-w64 64-bit", INTRO_F_BODY_9B},
};
static const intro_seg_t intro_seg_start_34[] = {
    {"CMAKE", INTRO_F_MONO_6},
};
static const intro_seg_t intro_seg_start_35[] = {
    {"≥ 3.20 · source build", INTRO_F_BODY_9B},
};
static const intro_seg_t intro_seg_start_36[] = {
    {"NINJA", INTRO_F_MONO_6},
};
static const intro_seg_t intro_seg_start_37[] = {
    {"source build", INTRO_F_BODY_9B},
};
static const intro_seg_t intro_seg_start_38[] = {
    {"CURL", INTRO_F_MONO_6},
};
static const intro_seg_t intro_seg_start_39[] = {
    {"source download", INTRO_F_BODY_9B},
};
static const intro_seg_t intro_seg_start_40[] = {
    {"DISK", INTRO_F_MONO_6},
};
static const intro_seg_t intro_seg_start_41[] = {
    {"~1 GB free", INTRO_F_BODY_9B},
};
static const intro_seg_t intro_seg_start_42[] = {
    {"Windows: MSYS2 UCRT64 recommended; ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_43[] = {
    {"gcc", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_44[] = {
    {" must be on PATH.", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_45[] = {
    {"HAND IT TO AI", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_start_46[] = {
    {"Give the repo to AI.", INTRO_F_DISP_23},
};
static const intro_seg_t intro_seg_start_47[] = {
    {"Claude Code, Cursor or another harness reads ", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_start_48[] = {
    {"core/SKILL.md", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_start_49[] = {
    {" and ", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_start_50[] = {
    {"CLAUDE.md", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_start_51[] = {
    {", then writes from ", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_start_52[] = {
    {"user/app/**/*.c", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_start_53[] = {
    {".", INTRO_F_BODY_10},
};
static const intro_seg_t intro_seg_start_54[] = {
    {"Claude Code skill: ", INTRO_F_MONO_10},
};
static const intro_seg_t intro_seg_start_55[] = {
    {"lvgl-verify-loop", INTRO_F_MONO_9},
};
static const intro_seg_t intro_seg_start_56[] = {
    {"Open the entry contract ", INTRO_F_MONO_8},
    {"↗", INTRO_F_SYMBOL_8},
};
static const intro_seg_t intro_seg_start_57[] = {
    {"LVGL PORT NOTES", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_58[] = {
    {"INTERACTIONS & MOTION", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_59[] = {
    {"01", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_60[] = {
    {"Screens", INTRO_F_DISP_14},
};
static const intro_seg_t intro_seg_start_61[] = {
    {"Six tab panels map to six LVGL screens or one ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_62[] = {
    {"lv_tabview", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_63[] = {
    {". Switching uses a 220 ms fade ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_64[] = {
    {"+ 8 px slide via ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_65[] = {
    {"lv_anim", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_66[] = {
    {" / ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_67[] = {
    {"lv_scr_load_anim", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_68[] = {
    {". At 800 × 600 the overview tightens to ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_69[] = {
    {"two compact columns; long screens scroll.", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_70[] = {
    {"02", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_71[] = {
    {"Loop", INTRO_F_DISP_14},
};
static const intro_seg_t intro_seg_start_72[] = {
    {"The gauge is one ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_73[] = {
    {"lv_arc", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_74[] = {
    {". Step changes animate its value over 300 ms. Auto-play is a 2600 ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_75[] = {
    {"ms ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_76[] = {
    {"lv_timer", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_77[] = {
    {"; pressing any step stops it.", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_78[] = {
    {"03", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_79[] = {
    {"Motion", INTRO_F_DISP_14},
};
static const intro_seg_t intro_seg_start_80[] = {
    {"Only opacity, small position changes, color and arc/bar value. No blur, parallax, scroll-", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_81[] = {
    {"triggered effects or hover-only information.", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_82[] = {
    {"04", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_83[] = {
    {"Media", INTRO_F_DISP_14},
};
static const intro_seg_t intro_seg_start_84[] = {
    {"Screenshots are ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_85[] = {
    {"lv_image", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_86[] = {
    {"; the intro demo is ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_87[] = {
    {"lv_gif", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_88[] = {
    {". The hardware clip is a poster + ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_89[] = {
    {"desktop link; on device, keep the still or a GIF.", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_90[] = {
    {"05", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_91[] = {
    {"Controls", INTRO_F_DISP_14},
};
static const intro_seg_t intro_seg_start_92[] = {
    {"Tabs and buttons have visible selected and pressed states, with touch targets of at least ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_93[] = {
    {"38 px. Keypad / encoder can follow the tab order. Text selection / copy and the hardware ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_94[] = {
    {"video link are web-only; on device, commands are display-only.", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_95[] = {
    {"06", INTRO_F_MONO_7},
};
static const intro_seg_t intro_seg_start_96[] = {
    {"Type", INTRO_F_DISP_14},
};
static const intro_seg_t intro_seg_start_97[] = {
    {"One UI family plus one mono family; convert with ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_98[] = {
    {"lv_font_conv", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_99[] = {
    {". Keep the display sizes ", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_100[] = {
    {"and line lengths. Arrows and status glyphs need glyph coverage or small drawn shapes.", INTRO_F_BODY_9},
};
static const intro_seg_t intro_seg_start_101[] = {
    {"AI writes. AI verifies. ", INTRO_F_DISP_22},
};
static const intro_seg_t intro_seg_start_102[] = {
    {"Humans decide.", INTRO_F_DISP_22},
};
static const intro_seg_t intro_seg_start_103[] = {
    {"README", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_104[] = {
    {"CONTEXT", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_105[] = {
    {"App guide", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_106[] = {
    {"Tool usage", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_107[] = {
    {"App variants", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_108[] = {
    {"Scenarios", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_109[] = {
    {"SiFli", INTRO_F_MONO_8},
};
static const intro_seg_t intro_seg_start_110[] = {
    {"Gitee ", INTRO_F_MONO_8},
    {"↗", INTRO_F_SYMBOL_8},
};
static const intro_seg_t intro_seg_start_111[] = {
    {"MIT LICENSE · PYTHON ≥ 3.9 · HEADLESS HOST · NO PASS/FAIL OUTPUT", INTRO_F_MONO_7},
};

static const intro_text_t intro_text_start[] = {
    {42, 38, 11, 0, intro_seg_start_0, 1, 0x38bdf8, 255, 0, 0},
    {91, 17, 62, 0, intro_seg_start_1, 1, 0x6b8091, 255, 2, 0},
    {91, 37, 316, 0, intro_seg_start_2, 1, 0xe8f1f8, 255, -1, 0},
    {537, 27, 81, 0, intro_seg_start_3, 1, 0x8ea3b3, 255, 0, 0},
    {621, 28, 64, 0, intro_seg_start_4, 1, 0x7dd3fc, 255, 0, 0},
    {688, 27, 54, 0, intro_seg_start_5, 1, 0x8ea3b3, 255, 0, 0},
    {537, 47, 169, 0, intro_seg_start_6, 1, 0x8ea3b3, 255, 0, 0},
    {709, 48, 52, 0, intro_seg_start_7, 1, 0x7dd3fc, 255, 0, 0},
    {765, 47, 3, 0, intro_seg_start_8, 1, 0x8ea3b3, 255, 0, 0},
    {71, 110, 90, 0, intro_seg_start_9, 1, 0x6b8091, 255, 0, 0},
    {705, 110, 55, 0, intro_seg_start_10, 1, 0x6b8091, 255, 0, 0},
    {40, 144, 8, 0, intro_seg_start_11, 1, 0x6b8091, 255, 0, 0},
    {74, 142, 123, 0, intro_seg_start_12, 1, 0x6e8b9e, 255, 0, 0},
    {74, 155, 481, 0, intro_seg_start_13, 1, 0xcfe0ec, 255, 0, 0},
    {40, 188, 8, 0, intro_seg_start_14, 1, 0x6b8091, 255, 0, 0},
    {74, 186, 289, 0, intro_seg_start_15, 1, 0x6e8b9e, 255, 0, 0},
    {74, 199, 324, 0, intro_seg_start_16, 1, 0xcfe0ec, 255, 0, 0},
    {40, 233, 8, 0, intro_seg_start_17, 1, 0x6b8091, 255, 0, 0},
    {74, 231, 185, 0, intro_seg_start_18, 1, 0x6e8b9e, 255, 0, 0},
    {74, 244, 246, 0, intro_seg_start_19, 1, 0xcfe0ec, 255, 0, 0},
    {40, 277, 8, 0, intro_seg_start_20, 1, 0x6b8091, 255, 0, 0},
    {74, 275, 189, 0, intro_seg_start_21, 1, 0x6e8b9e, 255, 0, 0},
    {74, 288, 376, 0, intro_seg_start_22, 1, 0xcfe0ec, 255, 0, 0},
    {40, 322, 8, 0, intro_seg_start_23, 1, 0x6b8091, 255, 0, 0},
    {74, 320, 277, 0, intro_seg_start_24, 1, 0x6e8b9e, 255, 0, 0},
    {74, 333, 146, 0, intro_seg_start_25, 1, 0xcfe0ec, 255, 0, 0},
    {40, 366, 93, 0, intro_seg_start_26, 1, 0x6b8091, 255, 0, 0},
    {621, 366, 139, 0, intro_seg_start_27, 1, 0x6b8091, 255, 0, 0},
    {44, 412, 66, 0, intro_seg_start_28, 1, 0x38bdf8, 255, 1, 0},
    {44, 441, 76, 0, intro_seg_start_29, 1, 0xe8f1f8, 255, 0, 0},
    {52, 486, 23, 0, intro_seg_start_30, 1, 0x6b8091, 255, 0, 0},
    {52, 498, 48, 0, intro_seg_start_31, 1, 0xb4c5d2, 255, 0, 0},
    {410, 486, 11, 0, intro_seg_start_32, 1, 0x6b8091, 255, 0, 0},
    {410, 498, 72, 0, intro_seg_start_33, 1, 0xb4c5d2, 255, 0, 0},
    {52, 530, 19, 0, intro_seg_start_34, 1, 0x6b8091, 255, 0, 0},
    {52, 543, 75, 0, intro_seg_start_35, 1, 0xb4c5d2, 255, 0, 0},
    {410, 530, 19, 0, intro_seg_start_36, 1, 0x6b8091, 255, 0, 0},
    {410, 543, 47, 0, intro_seg_start_37, 1, 0xb4c5d2, 255, 0, 0},
    {52, 575, 15, 0, intro_seg_start_38, 1, 0x6b8091, 255, 0, 0},
    {52, 587, 66, 0, intro_seg_start_39, 1, 0xb4c5d2, 255, 0, 0},
    {410, 575, 15, 0, intro_seg_start_40, 1, 0x6b8091, 255, 0, 0},
    {410, 587, 38, 0, intro_seg_start_41, 1, 0xb4c5d2, 255, 0, 0},
    {44, 615, 160, 0, intro_seg_start_42, 1, 0x6b8091, 255, 0, 0},
    {207, 616, 14, 0, intro_seg_start_43, 1, 0x7dd3fc, 255, 0, 0},
    {223, 615, 69, 0, intro_seg_start_44, 1, 0x6b8091, 255, 0, 0},
    {44, 672, 90, 0, intro_seg_start_45, 1, 0x8ea3b3, 255, 2, 0},
    {44, 700, 181, 0, intro_seg_start_46, 1, 0xe8f1f8, 255, -1, 0},
    {44, 739, 185, 0, intro_seg_start_47, 1, 0x8ea3b3, 255, 0, 0},
    {231, 740, 62, 0, intro_seg_start_48, 1, 0x7dd3fc, 255, 0, 0},
    {297, 739, 19, 0, intro_seg_start_49, 1, 0x8ea3b3, 255, 0, 0},
    {318, 740, 43, 0, intro_seg_start_50, 1, 0x7dd3fc, 255, 0, 0},
    {364, 739, 74, 0, intro_seg_start_51, 1, 0x8ea3b3, 255, 0, 0},
    {441, 740, 72, 0, intro_seg_start_52, 1, 0x7dd3fc, 255, 0, 0},
    {515, 739, 2, 0, intro_seg_start_53, 1, 0x8ea3b3, 255, 0, 0},
    {44, 770, 99, 0, intro_seg_start_54, 1, 0x8ea3b3, 255, 0, 0},
    {146, 771, 77, 0, intro_seg_start_55, 1, 0x7dd3fc, 255, 0, 0},
    {44, 799, 124, 0, intro_seg_start_56, 2, 0x38bdf8, 255, 0, 0},
    {42, 853, 73, 0, intro_seg_start_57, 1, 0x6b8091, 255, 1, 0},
    {655, 853, 103, 0, intro_seg_start_58, 1, 0x6b8091, 255, 1, 0},
    {44, 897, 7, 0, intro_seg_start_59, 1, 0x38bdf8, 255, 0, 0},
    {44, 918, 51, 0, intro_seg_start_60, 1, 0xe8f1f8, 255, 0, 0},
    {44, 942, 174, 0, intro_seg_start_61, 1, 0x8ea3b3, 255, 0, 0},
    {221, 943, 46, 0, intro_seg_start_62, 1, 0x7dd3fc, 255, 0, 0},
    {269, 942, 114, 0, intro_seg_start_63, 1, 0x8ea3b3, 255, 0, 0},
    {44, 956, 57, 0, intro_seg_start_64, 1, 0x8ea3b3, 255, 0, 0},
    {103, 957, 32, 0, intro_seg_start_65, 1, 0x7dd3fc, 255, 0, 0},
    {138, 956, 6, 0, intro_seg_start_66, 1, 0x8ea3b3, 255, 0, 0},
    {146, 957, 73, 0, intro_seg_start_67, 1, 0x7dd3fc, 255, 0, 0},
    {222, 956, 148, 0, intro_seg_start_68, 1, 0x8ea3b3, 255, 0, 0},
    {44, 971, 161, 0, intro_seg_start_69, 1, 0x8ea3b3, 255, 0, 0},
    {412, 897, 7, 0, intro_seg_start_70, 1, 0x38bdf8, 255, 0, 0},
    {412, 918, 30, 0, intro_seg_start_71, 1, 0xe8f1f8, 255, 0, 0},
    {412, 942, 66, 0, intro_seg_start_72, 1, 0x8ea3b3, 255, 0, 0},
    {480, 943, 27, 0, intro_seg_start_73, 1, 0x7dd3fc, 255, 0, 0},
    {510, 942, 245, 0, intro_seg_start_74, 1, 0x8ea3b3, 255, 0, 0},
    {412, 956, 13, 0, intro_seg_start_75, 1, 0x8ea3b3, 255, 0, 0},
    {428, 957, 36, 0, intro_seg_start_76, 1, 0x7dd3fc, 255, 0, 0},
    {466, 956, 102, 0, intro_seg_start_77, 1, 0x8ea3b3, 255, 0, 0},
    {44, 1014, 7, 0, intro_seg_start_78, 1, 0x38bdf8, 255, 0, 0},
    {44, 1036, 41, 0, intro_seg_start_79, 1, 0xe8f1f8, 255, 0, 0},
    {44, 1060, 321, 0, intro_seg_start_80, 1, 0x8ea3b3, 255, 0, 0},
    {44, 1074, 165, 0, intro_seg_start_81, 1, 0x8ea3b3, 255, 0, 0},
    {412, 1014, 7, 0, intro_seg_start_82, 1, 0x38bdf8, 255, 0, 0},
    {412, 1036, 36, 0, intro_seg_start_83, 1, 0xe8f1f8, 255, 0, 0},
    {412, 1060, 63, 0, intro_seg_start_84, 1, 0x8ea3b3, 255, 0, 0},
    {477, 1061, 36, 0, intro_seg_start_85, 1, 0x7dd3fc, 255, 0, 0},
    {516, 1060, 71, 0, intro_seg_start_86, 1, 0x8ea3b3, 255, 0, 0},
    {589, 1061, 27, 0, intro_seg_start_87, 1, 0x7dd3fc, 255, 0, 0},
    {619, 1060, 119, 0, intro_seg_start_88, 1, 0x8ea3b3, 255, 0, 0},
    {412, 1074, 173, 0, intro_seg_start_89, 1, 0x8ea3b3, 255, 0, 0},
    {44, 1117, 7, 0, intro_seg_start_90, 1, 0x38bdf8, 255, 0, 0},
    {44, 1139, 52, 0, intro_seg_start_91, 1, 0xe8f1f8, 255, 0, 0},
    {44, 1163, 332, 0, intro_seg_start_92, 1, 0x8ea3b3, 255, 0, 0},
    {44, 1177, 336, 0, intro_seg_start_93, 1, 0x8ea3b3, 255, 0, 0},
    {44, 1191, 237, 0, intro_seg_start_94, 1, 0x8ea3b3, 255, 0, 0},
    {412, 1117, 7, 0, intro_seg_start_95, 1, 0x38bdf8, 255, 0, 0},
    {412, 1139, 28, 0, intro_seg_start_96, 1, 0xe8f1f8, 255, 0, 0},
    {412, 1163, 189, 0, intro_seg_start_97, 1, 0x8ea3b3, 255, 0, 0},
    {604, 1164, 55, 0, intro_seg_start_98, 1, 0x7dd3fc, 255, 0, 0},
    {661, 1163, 87, 0, intro_seg_start_99, 1, 0x8ea3b3, 255, 0, 0},
    {412, 1177, 330, 0, intro_seg_start_100, 1, 0x8ea3b3, 255, 0, 0},
    {28, 1257, 192, 0, intro_seg_start_101, 1, 0xe8f1f8, 255, -1, 0},
    {220, 1257, 145, 0, intro_seg_start_102, 1, 0x38bdf8, 255, -1, 0},
    {28, 1290, 27, 0, intro_seg_start_103, 1, 0x8ea3b3, 255, 0, 0},
    {73, 1290, 31, 0, intro_seg_start_104, 1, 0x8ea3b3, 255, 0, 0},
    {122, 1290, 40, 0, intro_seg_start_105, 1, 0x8ea3b3, 255, 0, 0},
    {179, 1290, 44, 0, intro_seg_start_106, 1, 0x8ea3b3, 255, 0, 0},
    {242, 1290, 53, 0, intro_seg_start_107, 1, 0x8ea3b3, 255, 0, 0},
    {313, 1290, 40, 0, intro_seg_start_108, 1, 0x8ea3b3, 255, 0, 0},
    {370, 1290, 22, 0, intro_seg_start_109, 1, 0x8ea3b3, 255, 0, 0},
    {411, 1290, 34, 0, intro_seg_start_110, 2, 0x8ea3b3, 255, 0, 0},
    {28, 1315, 254, 0, intro_seg_start_111, 1, 0x6b8091, 255, 0, 0},
};

const intro_screen_t intro_screen_start = {
    intro_bg_start, 74, intro_text_start, 112, 1341
};

const lv_image_dsc_t * const intro_frames[5] = {
    &idx_img_intro_01, &idx_img_intro_02, &idx_img_intro_03,
    &idx_img_intro_04, &idx_img_intro_05,
};

const lv_image_dsc_t * const intro_watch_frames[8] = {
    &idx_img_watch_01, &idx_img_watch_02, &idx_img_watch_03,
    &idx_img_watch_04, &idx_img_watch_05, &idx_img_watch_06,
    &idx_img_watch_07, &idx_img_watch_08,
};

#endif /* LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4 */
