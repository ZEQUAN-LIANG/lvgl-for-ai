#ifndef ZC_GAME_H
#define ZC_GAME_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Graveyard Shift: the LVGL/RGB565 port of zombie-cannon.html.
 *
 * The game owns no LVGL objects and never allocates.  The caller supplies a
 * 16-bit framebuffer and (optionally) a second buffer for the static
 * backdrop.  Rendering is direct pixel work so the same code can run in the
 * headless LVGL host, as a standalone canvas widget, or inside sift_watch's
 * existing 390x450 canvas.
 *
 * Audio, haptics, RNG and high-score persistence are hooks.  A board without
 * a speaker simply leaves sfx == NULL; the game keeps running.  The hook
 * signatures are the stable platform seam, not a second UI layer.
 */

#define ZC_MAX_W 390
#define ZC_MAX_H 460

typedef enum {
    ZC_SFX_SHOOT = 0,
    ZC_SFX_SENTRY,
    ZC_SFX_HIT,
    ZC_SFX_DEATH,
    ZC_SFX_DEATH_BIG,
    ZC_SFX_EXPLODE,
    ZC_SFX_EXPLODE_BIG,
    ZC_SFX_HURT,
    ZC_SFX_HEAL,
    ZC_SFX_LEVEL_UP,
    ZC_SFX_WAVE,
    ZC_SFX_WAVE_BOSS,
    ZC_SFX_CLEAR,
    ZC_SFX_BOSS_SPAWN,
    ZC_SFX_BOSS_DOWN,
    ZC_SFX_LOSE,
    ZC_SFX_CLICK,
    ZC_SFX_COUNT
} zc_sfx_t;

typedef enum {
    ZC_HAPTIC_TAP = 0,
    ZC_HAPTIC_HIT,
    ZC_HAPTIC_BOSS,
    ZC_HAPTIC_LEVEL,
    ZC_HAPTIC_DEATH
} zc_haptic_t;

typedef struct {
    int32_t best_score;
    int32_t best_wave;
    uint8_t sound_on;
} zc_save_t;

typedef struct zc_hooks {
    void (*sfx)(zc_sfx_t id, void * user);
    void (*haptic)(zc_haptic_t kind, void * user);
    uint32_t (*rand)(void * user);
    bool (*load)(zc_save_t * save, void * user);
    void (*store)(const zc_save_t * save, void * user);
    void * user;
} zc_hooks_t;

typedef struct {
    int width;
    int height;
    /* Extra inset for the round-corner watch panel.  The HTML design uses 0;
     * sift_watch passes 44 so HUD and field controls stay inside the glass. */
    int safe_inset;
    /* true when the game is launched from sift_watch's app drawer.  The title
     * screen then exposes a back chevron and the end screen's secondary
     * button leaves the game instead of going to the local title. */
    bool embedded;
    bool show_scanlines;
    const zc_hooks_t * hooks;
} zc_config_t;

typedef enum {
    ZC_POINTER_DOWN = 0,
    ZC_POINTER_MOVE,
    ZC_POINTER_UP,
    ZC_POINTER_CANCEL
} zc_pointer_action_t;

/* Modes are exposed for printf evidence and for the host's back-key policy. */
enum {
    ZC_MODE_TITLE = 0,
    ZC_MODE_PLAYING,
    ZC_MODE_UPGRADE,
    ZC_MODE_PAUSED,
    ZC_MODE_ENDING,
    ZC_MODE_GAMEOVER
};

bool zc_create(uint16_t * fb, uint16_t * backdrop, const zc_config_t * cfg);
void zc_destroy(void);

/* Reset to the title screen and arm the demo.  Call when the watch enters the
 * game page; zc_leave lets the host stop forwarding input. */
void zc_enter(void);
void zc_leave(void);

void zc_tick(uint32_t now_ms, uint32_t elapsed_ms);
void zc_render(void);

void zc_pointer(zc_pointer_action_t action, int x, int y);
/* Returns true when the key was consumed.  ESC/HOME opens the pause sheet
 * while playing, and leaves the game from the title or pause exit button. */
bool zc_key(uint32_t key);

bool zc_wants_exit(void);
void zc_clear_exit(void);

bool zc_audio_on(void);
void zc_set_audio_on(bool on);

int zc_mode(void);
int zc_wave(void);
int zc_level(void);
int32_t zc_best_wave(void);
int32_t zc_best_score(void);

#ifdef __cplusplus
}
#endif

#endif /* ZC_GAME_H */
