#include "zc_game.h"

#include "zc_art.h"
#include "zc_gfx.h"
#include "zc_priv.h"

#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define ZC_TAU 6.2831853f
#define ZC_HUD_H 48
#define ZC_FIELD_TOP 51
#define ZC_HORIZON 116

#define ZC_MAX_ENEMIES 64
#define ZC_MAX_SHELLS 24
#define ZC_MAX_PARTICLES 240
#define ZC_MAX_BLASTS 16
#define ZC_MAX_FIRES 8
#define ZC_MAX_DECALS 20
#define ZC_MAX_TRACERS 8
#define ZC_MAX_FLOATERS 12
#define ZC_MAX_WAVE 64
#define ZC_MAX_SENTRIES 2
#define ZC_MAX_MOTES 22

enum { E_WALKER = 0, E_RUNNER, E_BRUTE, E_BOSS };

enum {
    UPG_RAPID = 0,
    UPG_DAMAGE,
    UPG_TWIN,
    UPG_CRYO,
    UPG_FIRE,
    UPG_SENTRY,
    UPG_CRIT,
    UPG_REINFORCE,
    UPG_REPAIR,
    UPG_COUNT
};

typedef struct {
    bool active;
    bool dead;
    uint8_t type;
    float x;
    float base_x;
    float y;
    int hp;
    int max_hp;
    float speed;
    float radius;
    int xp;
    int score;
    float anim;
    float phase;
    float wobble;
    float wobble_speed;
    float hit_flash;
    float slow_t;
    float slow_amount;
    bool attacking;
    float attack_timer;
    float attack_pulse;
    float stop_y;
} enemy_t;

typedef struct {
    bool active;
    float sx;
    float sy;
    float tx;
    float ty;
    float t;
    float dur;
    float arc;
    uint16_t color;
} shell_t;

typedef struct {
    bool active;
    float x;
    float y;
    float vx;
    float vy;
    float life;
    float max_life;
    float gravity;
    uint16_t color;
    uint8_t size;
} particle_t;

typedef struct {
    bool active;
    float x;
    float y;
    float t;
    float dur;
    float radius;
    bool crit;
} blast_t;

typedef struct {
    bool active;
    float x;
    float y;
    float t;
    float max_t;
    float tick;
    float radius;
    int damage;
    float seed;
} fire_t;

typedef struct {
    bool active;
    float x;
    float y;
    float size;
    uint16_t color;
    bool scorch;
    uint32_t seed;
} decal_t;

typedef struct {
    bool active;
    float x1;
    float y1;
    float x2;
    float y2;
    float t;
    float max_t;
} tracer_t;

typedef struct {
    bool active;
    char text[20];
    float x;
    float y;
    float life;
    float max_life;
    uint16_t color;
    uint8_t scale;
} floater_t;

typedef struct {
    bool active;
    float x;
    float y;
    float angle;
    float target_angle;
    float cd;
    float flash;
} sentry_t;

typedef struct {
    uint8_t type;
    float at;
} wave_item_t;

typedef struct {
    const char * name;
    int max;
    uint16_t accent;
} upgrade_def_t;

static const upgrade_def_t upgrade_defs[UPG_COUNT] = {
    {"速射机匣", 8, ZC_ACID},
    {"高爆弹头", 99, ZC_ORANGE},
    {"双联炮管", 1, ZC_GOLD},
    {"低温弹药", 6, ZC_CYAN},
    {"燃烧弹", 99, ZC_ORANGE},
    {"自动哨戒", 99, ZC_ACID},
    {"空尖弹", 99, ZC_RED},
    {"加固工事", 3, ZC_BONE},
    {"战地维修", 99, ZC_ACID}
};

static const char * const wave_flavor[8] = {
    "尸潮没有尽头",
    "它们在加速变异",
    "防线撑住",
    "黑暗里还有更多",
    "弹药比希望充足",
    "别让它靠近",
    "听见了吗",
    "它们从不休息"
};

typedef struct {
    int mode;
    float t;
    int width;
    int height;
    int dy;
    int safe;
    bool embedded;
    bool scanlines;
    int sound_on;
    bool exit_requested;

    int wave_index;
    wave_item_t wave_queue[ZC_MAX_WAVE];
    int wave_count;
    int wave_cursor;
    float wave_clock;
    float wave_grace;
    float wave_intermission;
    float wave_clear_timer;
    bool wave_active;

    int level;
    int xp;
    int xp_need;
    float display_xp;
    int pending_upgrades;
    float upgrade_delay;
    float upgrade_overlay_t;
    int upgrade_choices[3];
    int upgrade_choice_count;

    int base_hp;
    int base_max_hp;
    float base_flash;

    int kills;
    int score;
    int shots;
    float run_start;
    float run_time;
    bool new_best;
    int best_score;
    int best_wave;

    enemy_t enemies[ZC_MAX_ENEMIES];
    shell_t shells[ZC_MAX_SHELLS];
    particle_t particles[ZC_MAX_PARTICLES];
    int particle_head;
    blast_t blasts[ZC_MAX_BLASTS];
    int blast_head;
    fire_t fires[ZC_MAX_FIRES];
    decal_t decals[ZC_MAX_DECALS];
    int decal_head;
    tracer_t tracers[ZC_MAX_TRACERS];
    int tracer_head;
    floater_t floaters[ZC_MAX_FLOATERS];
    int floater_head;
    sentry_t sentries[ZC_MAX_SENTRIES];
    enemy_t * boss;

    int upg[UPG_COUNT];

    float aim_angle;
    float target_angle;
    float fire_timer;
    float recoil;
    float muzzle_flash;
    bool input_active;
    float input_x;
    float input_y;
    bool aim_valid;
    float aim_x;
    float aim_y;
    bool aim_snapped;

    float hint_timer;
    bool banner_active;
    char banner_title[40];
    char banner_sub[56];
    char banner_eng[32];
    uint16_t banner_color;
    char banner_kind[12];
    float banner_t;
    float banner_max_t;

    bool toast_active;
    char toast_text[40];
    char toast_sub[96];
    float toast_t;
    float toast_max_t;

    bool ending_lose;
    float ending_timer;
    float ending_t;
    float end_overlay_t;

    float shake;
    int shake_x;
    int shake_y;
    float flash_red;
    float flash_white;

    bool ai_mode;
    float ai_timer;
    float ai_idle;
} zc_state_t;

static zc_state_t S;
static zc_config_t g_cfg;
static zc_hooks_t g_hooks;
static bool g_created;
static uint32_t g_rand_state = 0x51F7A11DU;


static uint32_t rng_raw(void)
{
    if(g_hooks.rand != NULL) return g_hooks.rand(g_hooks.user);
    uint32_t x = g_rand_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    g_rand_state = x;
    return x;
}

static void rng_seed(uint32_t seed)
{
    g_rand_state = seed ? seed : 0x51F7A11DU;
}

static float frand(float a, float b)
{
    return a + ((float)(rng_raw() >> 8) / 16777216.0f) * (b - a);
}

static int irand(int a, int b)
{
    if(b <= a) return a;
    return a + (int)(rng_raw() % (uint32_t)(b - a + 1));
}

static float clampf(float v, float a, float b)
{
    return v < a ? a : v > b ? b : v;
}

static int clampi(int v, int a, int b)
{
    return v < a ? a : v > b ? b : v;
}

static float angle_lerp(float a, float b, float t)
{
    float d = fmodf(b - a + (float)M_PI, ZC_TAU);
    if(d < 0) d += ZC_TAU;
    d -= (float)M_PI;
    return a + d * t;
}

static void pad_n(int v, int minimum, char * out)
{
    char tmp[16];
    int n = 0;
    if(v < 0) v = 0;
    do {
        tmp[n++] = (char)('0' + v % 10);
        v /= 10;
    } while(v > 0 && n < 15);
    while(n < minimum) tmp[n++] = '0';
    for(int i = 0; i < n; i++) out[i] = tmp[n - 1 - i];
    out[n] = '\0';
}

static void pad2(int v, char * out)
{
    pad_n(v, 2, out);
}

static void pad5(int v, char * out)
{
    pad_n(v, 5, out);
}

static const char * fmt1(float v, char * buf, size_t n)
{
    int tenths = (int)(v * 10.0f + 0.5f);
    snprintf(buf, n, "%d.%d", tenths / 10, tenths % 10);
    return buf;
}

static int field_base_line(void)
{
    return 402 + S.dy;
}

static int field_pivot_y(void)
{
    return 404 + S.dy;
}

static void sfx(zc_sfx_t id)
{
    if(!S.sound_on) return;
    if(g_hooks.sfx != NULL) g_hooks.sfx(id, g_hooks.user);
}

static void haptic(zc_haptic_t kind)
{
    if(g_hooks.haptic != NULL) g_hooks.haptic(kind, g_hooks.user);
}

static void save_store(void)
{
    if(g_hooks.store == NULL) return;
    zc_save_t save;
    save.best_score = S.best_score;
    save.best_wave = S.best_wave;
    save.sound_on = (uint8_t)(S.sound_on ? 1 : 0);
    g_hooks.store(&save, g_hooks.user);
}


static float hp_scale_for(int wave)
{
    return powf(1.17f, (float)(wave > 1 ? wave - 1 : 0));
}

static float cryo_slow_at(int lv)
{
    if(lv <= 0) return 0.0f;
    float v = 0.30f + (float)(lv - 1) * 0.06f;
    return v > 0.65f ? 0.65f : v;
}

static float cryo_duration_at(int lv)
{
    return lv <= 0 ? 0.0f : 1.8f + (float)lv * 0.13f;
}

static float crit_chance_at(int lv)
{
    if(lv <= 0) return 0.0f;
    float v = 0.20f + (float)(lv - 1) * 0.15f;
    return v > 0.65f ? 0.65f : v;
}

static float crit_mult_at(int lv)
{
    return 2.0f + (float)(lv > 4 ? lv - 4 : 0) * 0.4f;
}

static int fire_damage_at(int lv)
{
    return 1 + lv;
}

static float fire_duration_at(int lv)
{
    float v = 2.1f + (float)lv * 0.35f;
    return v > 8.0f ? 8.0f : v;
}

static int fire_radius_at(int lv)
{
    int v = 18 + lv * 2;
    return v > 46 ? 46 : v;
}

static int sentry_count_at(int lv)
{
    return lv <= 0 ? 0 : lv > 2 ? 2 : lv;
}

static int sentry_damage_at(int lv)
{
    return 1 + (lv > 2 ? (lv - 2) / 2 : 0);
}

static float sentry_interval_at(int lv)
{
    float v = 1.45f - (float)(lv > 1 ? lv - 1 : 0) * 0.08f;
    return v < 0.42f ? 0.42f : v;
}

static int repair_amount_at(int lv)
{
    return 2 + lv / 3;
}

static float interval_for(bool manual)
{
    float base = manual ? 0.38f : 0.64f;
    return fmaxf(0.13f, base * powf(0.87f, (float)S.upg[UPG_RAPID]));
}


static void add_particle(float x, float y, float vx, float vy, float life,
                         uint16_t color, int size, float gravity)
{
    int slot = S.particle_head;
    S.particle_head = (S.particle_head + 1) % ZC_MAX_PARTICLES;
    particle_t * p = &S.particles[slot];
    p->active = true;
    p->x = x;
    p->y = y;
    p->vx = vx;
    p->vy = vy;
    p->life = life;
    p->max_life = life;
    p->color = color;
    p->size = (uint8_t)(size < 1 ? 1 : size);
    p->gravity = gravity;
}

static void add_floater(const char * text, float x, float y, uint16_t color, int scale)
{
    int slot = S.floater_head;
    S.floater_head = (S.floater_head + 1) % ZC_MAX_FLOATERS;
    floater_t * f = &S.floaters[slot];
    f->active = true;
    snprintf(f->text, sizeof(f->text), "%s", text);
    f->x = x;
    f->y = y;
    f->life = 0.72f;
    f->max_life = 0.72f;
    f->color = color;
    f->scale = (uint8_t)(scale < 1 ? 1 : scale);
}

static void add_decal(float x, float y, float size, uint16_t color, bool scorch)
{
    if(scorch && frand(0.0f, 1.0f) > 0.45f) return;
    int slot = S.decal_head;
    S.decal_head = (S.decal_head + 1) % ZC_MAX_DECALS;
    decal_t * d = &S.decals[slot];
    d->active = true;
    d->x = x;
    d->y = y;
    d->size = size;
    d->color = color;
    d->scorch = scorch;
    d->seed = rng_raw();
}

static void add_blast(float x, float y, float radius, bool crit)
{
    int slot = -1;
    for(int i = 0; i < ZC_MAX_BLASTS; i++) {
        if(!S.blasts[i].active) {
            slot = i;
            break;
        }
    }
    if(slot < 0) {
        slot = S.blast_head;
        S.blast_head = (S.blast_head + 1) % ZC_MAX_BLASTS;
    }
    blast_t * b = &S.blasts[slot];
    b->active = true;
    b->x = x;
    b->y = y;
    b->t = 0.0f;
    b->dur = 0.28f;
    b->radius = radius;
    b->crit = crit;
    S.shake = fmaxf(S.shake, 2.2f + radius * 0.026f);
    sfx(radius > 36.0f ? ZC_SFX_EXPLODE_BIG : ZC_SFX_EXPLODE);
    add_decal(x, y, radius * 0.7f, ZC_RGB565(17, 19, 12), true);
    int count = (int)(12.0f + radius * 0.28f);
    for(int i = 0; i < count; i++) {
        float a = frand(0.0f, ZC_TAU);
        float sp = frand(30.0f, 130.0f);
        uint16_t col;
        if((float)i < (float)count * 0.55f) {
            col = frand(0.0f, 1.0f) > 0.5f ? ZC_GOLD : ZC_ORANGE;
        }
        else {
            col = frand(0.0f, 1.0f) > 0.6f ? ZC_BONE_D : ZC_SMOKE;
        }
        add_particle(x + cosf(a) * frand(0.0f, radius * 0.35f),
                     y + sinf(a) * frand(0.0f, radius * 0.35f),
                     cosf(a) * sp, sinf(a) * sp - 20.0f,
                     frand(0.2f, 0.6f), col, irand(1, 3), 60.0f);
    }
    if(S.upg[UPG_CRYO] > 0) {
        for(int i = 0; i < 10; i++) {
            float a = frand(0.0f, ZC_TAU);
            add_particle(x, y, cosf(a) * frand(18.0f, 70.0f),
                         sinf(a) * frand(18.0f, 70.0f) - 15.0f,
                         frand(0.25f, 0.55f), i % 2 ? ZC_CYAN : ZC_BONE, 1, 20.0f);
        }
    }
}


static zc_sprite_def_t const * sprite_for(int type)
{
    return zc_art_sprite(type);
}

static void enemy_center(const enemy_t * e, float * cx, float * cy)
{
    const zc_sprite_def_t * def = sprite_for(e->type);
    *cx = e->x;
    *cy = e->y - (float)(def->h * def->scale) * 0.48f;
}

static enemy_t * pick_auto_target(void)
{
    enemy_t * best = NULL;
    float best_key = -1.0e9f;
    for(int i = 0; i < ZC_MAX_ENEMIES; i++) {
        enemy_t * e = &S.enemies[i];
        if(!e->active || e->dead) continue;
        float key = e->y + (e->attacking ? 60.0f : 0.0f) + (e->type == E_BOSS ? 20.0f : 0.0f);
        if(key > best_key) {
            best_key = key;
            best = e;
        }
    }
    return best;
}

static void resolve_aim(float raw_x, float raw_y)
{
    float x = clampf(raw_x, 12.0f, (float)S.width - 12.0f);
    float y = clampf(raw_y, (float)ZC_HUD_H + 8.0f, (float)field_base_line() - 6.0f);
    enemy_t * nearest = NULL;
    float nearest_d = 1.0e9f;
    float snap = 54.0f;
    for(int i = 0; i < ZC_MAX_ENEMIES; i++) {
        enemy_t * e = &S.enemies[i];
        if(!e->active || e->dead) continue;
        float cx;
        float cy;
        enemy_center(e, &cx, &cy);
        float dx = x - cx;
        float dy = y - cy;
        float d = dx * dx + dy * dy;
        if(d < nearest_d && d < snap * snap) {
            nearest_d = d;
            nearest = e;
        }
    }
    if(nearest != NULL) {
        float cx;
        float cy;
        enemy_center(nearest, &cx, &cy);
        S.aim_x = cx;
        S.aim_y = cy;
        S.aim_snapped = true;
    }
    else {
        S.aim_x = x;
        S.aim_y = y;
        S.aim_snapped = false;
    }
    S.aim_valid = true;
}


static void heal_base(int amount)
{
    int before = S.base_hp;
    S.base_hp = clampi(S.base_hp + amount, 0, S.base_max_hp);
    if(S.base_hp > before) {
        S.base_flash = 0.2f;
        for(int i = 0; i < 10; i++) {
            add_particle(frand(130.0f, 260.0f), frand(388.0f + (float)S.dy, 410.0f + (float)S.dy),
                         frand(-16.0f, 16.0f), frand(-38.0f, -12.0f), frand(0.35f, 0.8f),
                         i % 2 ? ZC_ACID : ZC_BONE, 1, -20.0f);
        }
        sfx(ZC_SFX_HEAL);
    }
}

static void add_xp(int amount)
{
    if(amount <= 0) return;
    S.xp += amount;
    while(S.xp >= S.xp_need) {
        S.xp -= S.xp_need;
        S.level++;
        S.xp_need = 6 + (S.level - 1) * 3;
        S.pending_upgrades++;
    }
    if(S.pending_upgrades > 0 && S.upgrade_delay <= 0.0f) S.upgrade_delay = 0.16f;
}

static void set_banner(const char * title, const char * sub, const char * eng, uint16_t color,
                       const char * kind, float time)
{
    S.banner_active = true;
    snprintf(S.banner_title, sizeof(S.banner_title), "%s", title);
    snprintf(S.banner_sub, sizeof(S.banner_sub), "%s", sub);
    snprintf(S.banner_eng, sizeof(S.banner_eng), "%s", eng);
    snprintf(S.banner_kind, sizeof(S.banner_kind), "%s", kind);
    S.banner_color = color;
    S.banner_t = time;
    S.banner_max_t = time;
}

static void start_ending(void)
{
    if(S.mode == ZC_MODE_ENDING || S.mode == ZC_MODE_GAMEOVER) return;
    S.mode = ZC_MODE_ENDING;
    S.ending_lose = true;
    S.ending_t = 0.0f;
    S.ending_timer = 1.45f;
    S.input_active = false;
    S.aim_valid = false;
    S.run_time = fmaxf(0.0f, S.t - S.run_start);
    sfx(ZC_SFX_LOSE);
    S.flash_red = 0.65f;
    haptic(ZC_HAPTIC_DEATH);
    for(int i = 0; i < 36; i++) {
        add_particle(frand(110.0f, 280.0f), frand(380.0f + (float)S.dy, 435.0f + (float)S.dy),
                     frand(-120.0f, 120.0f), frand(-170.0f, -20.0f), frand(0.4f, 1.1f),
                     i % 3 ? ZC_RUST : ZC_SMOKE, irand(1, 4), 120.0f);
    }
    if(S.score > S.best_score) {
        S.new_best = true;
        S.best_score = S.score;
    }
    if(S.wave_index > S.best_wave) {
        S.new_best = true;
        S.best_wave = S.wave_index;
    }
    save_store();
}

static void damage_base(int amount)
{
    if(S.mode != ZC_MODE_PLAYING) return;
    S.base_hp = S.base_hp - amount > 0 ? S.base_hp - amount : 0;
    S.base_flash = 0.5f;
    S.flash_red = fmaxf(S.flash_red, 0.42f);
    S.shake = fmaxf(S.shake, 5.0f);
    sfx(ZC_SFX_HURT);
    haptic(ZC_HAPTIC_HIT);
    for(int i = 0; i < 16; i++) {
        add_particle(frand(70.0f, 320.0f), frand(392.0f + (float)S.dy, 414.0f + (float)S.dy),
                     frand(-70.0f, 70.0f), frand(-90.0f, -20.0f), frand(0.3f, 0.7f),
                     i % 2 ? ZC_RUST : ZC_BONE_D, irand(1, 3), 160.0f);
    }
    if(S.base_hp <= 0) start_ending();
}

static void kill_enemy(enemy_t * e, bool crit)
{
    (void)crit;
    if(e == NULL || e->dead) return;
    e->dead = true;
    e->active = false;
    S.kills++;
    S.score += e->score;
    add_xp(e->xp);
    if(e->type == E_BOSS) {
        S.boss = NULL;
        add_blast(e->x, e->y - 20.0f, 62.0f, true);
        S.flash_white = fmaxf(S.flash_white, 0.55f);
        S.shake = fmaxf(S.shake, 11.0f);
        sfx(ZC_SFX_BOSS_DOWN);
        haptic(ZC_HAPTIC_BOSS);
        add_decal(e->x, e->y - 2.0f, 44.0f, ZC_RGB565(12, 14, 8), true);
        for(int i = 0; i < 45; i++) {
            add_particle(e->x + frand(-24.0f, 24.0f), e->y - frand(0.0f, 50.0f),
                         frand(-140.0f, 140.0f), frand(-150.0f, 30.0f), frand(0.4f, 1.2f),
                         i % 3 == 0 ? ZC_GOLD : i % 3 == 1 ? ZC_RED : ZC_SMOKE,
                         irand(1, 4), 160.0f);
        }
        set_banner("屠宰者已消灭", "感染体信号正在消失", "TARGET DOWN", ZC_GOLD, "bossdown", 2.3f);
        add_floater("+600", e->x, e->y - 60.0f, ZC_GOLD, 2);
    }
    else {
        int blood = e->type == E_BRUTE ? 22 : 11;
        for(int i = 0; i < blood; i++) {
            add_particle(e->x + frand(-7.0f, 7.0f), e->y - frand(6.0f, 26.0f),
                         frand(-70.0f, 70.0f), frand(-110.0f, -10.0f), frand(0.25f, 0.8f),
                         i % 3 ? ZC_BLOOD : ZC_RUST, irand(1, 3), 180.0f);
        }
        add_decal(e->x, e->y - 1.0f, e->type == E_BRUTE ? 20.0f : 11.0f,
                  ZC_RGB565(76, 24, 20), false);
        sfx(e->type == E_BRUTE ? ZC_SFX_DEATH_BIG : ZC_SFX_DEATH);
    }
}

static void damage_enemy(enemy_t * e, float amount, bool crit, bool slow,
                         float slow_amount, float slow_duration)
{
    if(e == NULL || e->dead) return;
    e->hp -= (int)amount;
    e->hit_flash = fmaxf(e->hit_flash, 0.09f);
    if(e->slow_t > 0.0f) {
        e->slow_amount = fmaxf(e->slow_amount, slow ? slow_amount : 0.0f);
    }
    if(slow) {
        e->slow_t = fmaxf(e->slow_t, slow_duration);
        e->slow_amount = fmaxf(e->slow_amount, slow_amount);
    }
    if(crit || amount >= 2.0f) {
        char buf[20];
        if(crit) snprintf(buf, sizeof(buf), "CRIT %d", (int)lroundf(amount));
        else snprintf(buf, sizeof(buf), "%d", (int)lroundf(amount));
        add_floater(buf, e->x, e->y - 26.0f, crit ? ZC_RED : ZC_BONE, crit ? 2 : 1);
    }
    int hit_count = (int)fminf(7.0f, 2.0f + ceilf(amount));
    for(int i = 0; i < hit_count; i++) {
        add_particle(e->x + frand(-5.0f, 5.0f), e->y - frand(8.0f, 22.0f),
                     frand(-35.0f, 35.0f), frand(-60.0f, 5.0f), frand(0.15f, 0.45f),
                     i % 3 ? ZC_BLOOD : ZC_BONE_D, irand(1, 2), 140.0f);
    }
    if(e->hp <= 0) kill_enemy(e, crit);
}

static void muzzle_point(float offset, float extra_recoil, float * mx, float * my)
{
    float len = 39.0f - S.recoil * 6.0f - extra_recoil;
    float a = S.aim_angle + offset;
    *mx = 195.0f + cosf(a) * len;
    *my = (float)field_pivot_y() + sinf(a) * len;
}

static void fire_at(float target_x, float target_y, bool manual)
{
    float offs[2];
    int off_count;
    if(S.upg[UPG_TWIN] > 0) {
        offs[0] = -4.0f * (float)M_PI / 180.0f;
        offs[1] = 4.0f * (float)M_PI / 180.0f;
        off_count = 2;
    }
    else {
        offs[0] = 0.0f;
        off_count = 1;
    }
    for(int i = 0; i < off_count; i++) {
        float mx;
        float my;
        muzzle_point(offs[i], 0.0f, &mx, &my);
        float jx = off_count > 1 ? (i == 0 ? -9.0f : 9.0f) : frand(-2.5f, 2.5f);
        float jy = frand(-3.0f, 3.0f);
        float dx = target_x + jx - mx;
        float dy = target_y + jy - my;
        float dist = sqrtf(dx * dx + dy * dy);
        int slot = -1;
        for(int k = 0; k < ZC_MAX_SHELLS; k++) {
            if(!S.shells[k].active) {
                slot = k;
                break;
            }
        }
        if(slot < 0) slot = 0;
        shell_t * s = &S.shells[slot];
        s->active = true;
        s->sx = mx;
        s->sy = my;
        s->tx = target_x + jx;
        s->ty = target_y + jy;
        s->t = 0.0f;
        s->dur = clampf(dist / 580.0f, 0.11f, 0.28f);
        s->arc = 12.0f + dist * 0.05f;
        s->color = S.upg[UPG_CRYO] > 0 ? ZC_CYAN : ZC_GOLD;
    }
    S.shots++;
    S.fire_timer = interval_for(manual);
    S.recoil = 1.0f;
    S.muzzle_flash = 0.085f;
    S.shake = fmaxf(S.shake, 1.2f);
    int n = S.upg[UPG_TWIN] > 0 ? 8 : 5;
    for(int i = 0; i < n; i++) {
        float mx;
        float my;
        muzzle_point(0.0f, 0.0f, &mx, &my);
        add_particle(mx, my, frand(-45.0f, 45.0f), frand(-55.0f, 5.0f),
                     frand(0.12f, 0.28f), i % 2 ? ZC_GOLD : ZC_ORANGE, irand(1, 2), 20.0f);
    }
    sfx(ZC_SFX_SHOOT);
}

static void add_fire_patch(float x, float y)
{
    int slot = -1;
    for(int i = 0; i < ZC_MAX_FIRES; i++) {
        if(!S.fires[i].active) {
            slot = i;
            break;
        }
    }
    if(slot < 0) {
        for(int i = 0; i < ZC_MAX_FIRES - 1; i++) S.fires[i] = S.fires[i + 1];
        slot = ZC_MAX_FIRES - 1;
    }
    fire_t * f = &S.fires[slot];
    f->active = true;
    f->x = x;
    f->y = y;
    f->t = fire_duration_at(S.upg[UPG_FIRE]);
    f->max_t = f->t;
    f->tick = 0.12f;
    f->radius = (float)fire_radius_at(S.upg[UPG_FIRE]);
    f->damage = fire_damage_at(S.upg[UPG_FIRE]);
    f->seed = frand(0.0f, 99.0f);
}

static void detonate(shell_t * s)
{
    float radius = fminf(66.0f, 25.0f + (float)S.upg[UPG_DAMAGE] * 4.0f);
    float chance = crit_chance_at(S.upg[UPG_CRIT]);
    bool crit = frand(0.0f, 1.0f) < chance;
    float damage = (1.0f + (float)S.upg[UPG_DAMAGE]) * (crit ? crit_mult_at(S.upg[UPG_CRIT]) : 1.0f);
    float slow = cryo_slow_at(S.upg[UPG_CRYO]);
    float slow_t = cryo_duration_at(S.upg[UPG_CRYO]);
    for(int i = 0; i < ZC_MAX_ENEMIES; i++) {
        enemy_t * e = &S.enemies[i];
        if(!e->active || e->dead) continue;
        float cx;
        float cy;
        enemy_center(e, &cx, &cy);
        float dx = cx - s->tx;
        float dy = cy - s->ty;
        float reach = radius + e->radius * 0.55f;
        if(dx * dx + dy * dy <= reach * reach) {
            damage_enemy(e, damage, crit, S.upg[UPG_CRYO] > 0, slow, slow_t);
        }
    }
    add_blast(s->tx, s->ty, radius, crit);
    if(S.upg[UPG_FIRE] > 0) add_fire_patch(s->tx, s->ty);
}


static void wave_composition(int n, int * walker, int * runner, int * brute, int * boss)
{
    *walker = 7 + n;
    if(*walker > 24) *walker = 24;
    *runner = n >= 2 ? 2 + (int)((float)n * 0.8f) : 0;
    if(*runner > 14) *runner = 14;
    *brute = n >= 4 ? 1 + (int)((float)(n - 4) * 0.6f) : 0;
    if(*brute > 6) *brute = 6;
    *boss = (n % 5) == 0 ? 1 : 0;
}

static void begin_wave(int n)
{
    S.wave_index = n;
    S.wave_count = 0;
    S.wave_cursor = 0;
    S.wave_clock = 0.0f;
    S.wave_grace = 1.9f;
    S.wave_clear_timer = 0.0f;
    S.wave_intermission = 0.0f;
    S.wave_active = true;
    for(int i = 0; i < ZC_MAX_DECALS; i++) S.decals[i].active = false;
    for(int i = 0; i < ZC_MAX_FIRES; i++) S.fires[i].active = false;

    int walker;
    int runner;
    int brute;
    int boss;
    wave_composition(n, &walker, &runner, &brute, &boss);
    int bag[ZC_MAX_WAVE];
    int count = 0;
    for(int i = 0; i < walker && count < ZC_MAX_WAVE; i++) bag[count++] = E_WALKER;
    for(int i = 0; i < runner && count < ZC_MAX_WAVE; i++) bag[count++] = E_RUNNER;
    for(int i = 0; i < brute && count < ZC_MAX_WAVE; i++) bag[count++] = E_BRUTE;
    for(int i = 0; i < boss && count < ZC_MAX_WAVE; i++) bag[count++] = E_BOSS;
    for(int i = count - 1; i > 0; i--) {
        int j = irand(0, i);
        int tmp = bag[i];
        bag[i] = bag[j];
        bag[j] = tmp;
    }
    for(int i = 0; i < count; i++) {
        if(bag[i] == E_BOSS) {
            int dest = (int)((float)(count - 1) * 0.58f);
            for(int k = i; k < dest; k++) bag[k] = bag[k + 1];
            bag[dest] = E_BOSS;
            break;
        }
    }
    float gap = 1.12f - (float)n * 0.032f;
    if(gap < 0.36f) gap = 0.36f;
    float clock = 0.2f;
    for(int i = 0; i < count; i++) {
        if(bag[i] == E_BOSS) clock += 1.4f;
        S.wave_queue[S.wave_count].type = (uint8_t)bag[i];
        S.wave_queue[S.wave_count].at = clock;
        S.wave_count++;
        clock += gap * frand(0.8f, 1.24f);
        if(bag[i] == E_BOSS) clock += 0.9f;
    }

    bool boss_wave = (n % 5) == 0;
    char title[40];
    char eng[32];
    snprintf(title, sizeof(title), "第 %d 波", n);
    if(boss_wave) snprintf(eng, sizeof(eng), "BOSS WAVE");
    else snprintf(eng, sizeof(eng), "WAVE %02d", n);
    set_banner(title, boss_wave ? "屠宰者正在接近" : wave_flavor[(n - 1) & 7],
               eng, boss_wave ? ZC_RED : ZC_ACID, boss_wave ? "final" : "wave",
               boss_wave ? 2.4f : 2.0f);
    sfx(boss_wave ? ZC_SFX_WAVE_BOSS : ZC_SFX_WAVE);
}

static void finish_wave(void)
{
    if(!S.wave_active) return;
    S.wave_active = false;
    int bonus = 90 + S.wave_index * 50;
    S.score += bonus;
    int before = S.base_hp;
    S.base_hp = clampi(S.base_hp + 1, 0, S.base_max_hp);
    bool healed = S.base_hp > before;
    if(healed) {
        S.base_flash = 0.28f;
        for(int i = 0; i < 12; i++) {
            add_particle(frand(140.0f, 250.0f), frand(390.0f + (float)S.dy, 420.0f + (float)S.dy),
                         frand(-25.0f, 25.0f), frand(-50.0f, -12.0f), frand(0.35f, 0.8f),
                         i % 2 ? ZC_ACID : ZC_BONE, 1, -25.0f);
        }
    }
    char sub[56];
    if(healed) snprintf(sub, sizeof(sub), "防线修复 +1 · 补给 +%d", bonus);
    else snprintf(sub, sizeof(sub), "补给 +%d", bonus);
    char eng[32];
    snprintf(eng, sizeof(eng), "WAVE %02d CLEAR", S.wave_index);
    set_banner("区域肃清", sub, eng, ZC_ACID, "clear", 2.0f);
    sfx(ZC_SFX_CLEAR);
    S.wave_intermission = fmaxf(1.6f, 3.0f - (float)S.wave_index * 0.04f);
}

static void spawn_enemy(int type)
{
    float hp_scale = hp_scale_for(S.wave_index);
    int hp;
    float speed;
    float radius;
    int xp;
    if(type == E_WALKER) {
        hp = (int)lroundf(2.0f * hp_scale);
        if(hp < 2) hp = 2;
        speed = 15.0f + fminf(15.0f, (float)S.wave_index * 0.9f);
        radius = 10.0f;
        xp = 1 + (S.wave_index > 1 ? (S.wave_index - 1) / 4 : 0);
    }
    else if(type == E_RUNNER) {
        hp = (int)lroundf(1.6f * hp_scale);
        if(hp < 1) hp = 1;
        speed = 26.0f + fminf(20.0f, (float)S.wave_index * 1.5f);
        radius = 9.0f;
        xp = 1 + (S.wave_index > 1 ? (S.wave_index - 1) / 4 : 0);
    }
    else if(type == E_BRUTE) {
        hp = (int)lroundf(6.5f * hp_scale);
        if(hp < 6) hp = 6;
        speed = 9.0f + fminf(9.0f, (float)S.wave_index * 0.4f);
        radius = 16.0f;
        xp = 3 + (S.wave_index > 1 ? (S.wave_index - 1) / 2 : 0);
    }
    else {
        hp = (int)lroundf(55.0f * powf(1.19f, (float)(S.wave_index > 5 ? S.wave_index - 5 : 0)));
        if(hp < 60) hp = 60;
        speed = 6.0f + fminf(3.5f, (float)S.wave_index * 0.07f);
        radius = 27.0f;
        xp = 10 + S.wave_index;
    }
    bool is_boss = type == E_BOSS;
    float base_x = is_boss ? 195.0f : frand(34.0f, (float)S.width - 34.0f);
    int slot = -1;
    for(int i = 0; i < ZC_MAX_ENEMIES; i++) {
        if(!S.enemies[i].active) {
            slot = i;
            break;
        }
    }
    if(slot < 0) return;
    enemy_t * e = &S.enemies[slot];
    memset(e, 0, sizeof(*e));
    e->active = true;
    e->type = (uint8_t)type;
    e->x = base_x;
    e->base_x = base_x;
    e->y = (float)ZC_HORIZON + frand(2.0f, 8.0f);
    e->hp = hp;
    e->max_hp = hp;
    e->speed = speed;
    e->radius = radius;
    e->xp = xp;
    e->score = (int)lroundf((float)(type == E_WALKER ? 10 : type == E_RUNNER ? 13 : type == E_BRUTE ? 38 : 600) *
                            (1.0f + (float)(S.wave_index > 1 ? S.wave_index - 1 : 0) * 0.12f));
    e->anim = frand(0.0f, 5.0f);
    e->phase = frand(0.0f, ZC_TAU);
    e->wobble = is_boss ? 0.0f : (type == E_RUNNER ? 7.5f : type == E_WALKER ? 3.2f : 1.2f) * frand(0.7f, 1.2f);
    e->wobble_speed = (type == E_RUNNER ? 2.4f : type == E_WALKER ? 1.6f : 0.8f) * frand(0.8f, 1.2f);
    e->hit_flash = 0.0f;
    e->slow_t = 0.0f;
    e->slow_amount = 0.0f;
    e->attacking = false;
    e->stop_y = (float)field_base_line() + (is_boss ? -2.0f : 0.0f);
    if(is_boss) {
        S.boss = e;
        set_banner("屠宰者", "大型感染体接近", "WARNING", ZC_RED, "boss", 1.8f);
        sfx(ZC_SFX_BOSS_SPAWN);
        S.flash_red = 0.25f;
        S.shake = fmaxf(S.shake, 4.0f);
        haptic(ZC_HAPTIC_BOSS);
        for(int i = 0; i < 24; i++) {
            add_particle(e->x + frand(-24.0f, 24.0f), (float)ZC_HORIZON + frand(4.0f, 30.0f),
                         frand(-30.0f, 30.0f), frand(-30.0f, 8.0f), frand(0.4f, 1.1f),
                         i % 3 ? ZC_SMOKE : ZC_RED, irand(1, 3), 30.0f);
        }
    }
    else {
        for(int i = 0; i < 4; i++) {
            add_particle(e->x + frand(-8.0f, 8.0f), e->y - 8.0f,
                         frand(-8.0f, 8.0f), frand(-8.0f, 5.0f), frand(0.2f, 0.5f),
                         ZC_SMOKE, 1, 0.0f);
        }
    }
}


static void upgrade_desc(int key, char * out, size_t n)
{
    char f1[16];
    switch(key) {
    case UPG_RAPID:
        snprintf(out, n, "射击间隔再缩短 13%%");
        break;
    case UPG_DAMAGE:
        snprintf(out, n, "炮弹伤害 +1，爆风 +4");
        break;
    case UPG_TWIN:
        snprintf(out, n, "每轮齐射追加一发炮弹");
        break;
    case UPG_CRYO: {
        int lv = S.upg[UPG_CRYO] + 1;
        int pct = (int)lroundf(cryo_slow_at(lv) * 100.0f);
        snprintf(out, n, "减速 %d%%，持续 %s 秒", pct,
                 fmt1(cryo_duration_at(lv), f1, sizeof(f1)));
        break;
    }
    case UPG_FIRE: {
        int lv = S.upg[UPG_FIRE] + 1;
        snprintf(out, n, "火海每跳伤害提升至 %d，持续 %s 秒",
                 fire_damage_at(lv), fmt1(fire_duration_at(lv), f1, sizeof(f1)));
        break;
    }
    case UPG_SENTRY:
        if(S.upg[UPG_SENTRY] < 1) snprintf(out, n, "部署一门自动索敌的哨戒炮");
        else if(S.upg[UPG_SENTRY] < 2) snprintf(out, n, "再部署一门哨戒炮");
        else snprintf(out, n, "哨戒炮伤害与射速提升");
        break;
    case UPG_CRIT: {
        int lv = S.upg[UPG_CRIT] + 1;
        if(lv <= 4) snprintf(out, n, "暴击率提升至 %d%%", (int)lroundf(crit_chance_at(lv) * 100.0f));
        else snprintf(out, n, "暴击伤害提升至 %s 倍", fmt1(crit_mult_at(lv), f1, sizeof(f1)));
        break;
    }
    case UPG_REINFORCE:
        snprintf(out, n, "防线耐久上限 +1，并修复 1 点");
        break;
    case UPG_REPAIR:
        snprintf(out, n, "立刻修复 %d 点防线耐久", repair_amount_at(S.upg[UPG_REPAIR]));
        break;
    default:
        out[0] = '\0';
        break;
    }
}

static void sync_sentries(void)
{
    int wanted = sentry_count_at(S.upg[UPG_SENTRY]);
    for(int i = 0; i < ZC_MAX_SENTRIES; i++) {
        if(i >= wanted) S.sentries[i].active = false;
    }
    static const int xs[2] = {93, 297};
    for(int i = 0; i < wanted && i < ZC_MAX_SENTRIES; i++) {
        if(S.sentries[i].active) continue;
        sentry_t * s = &S.sentries[i];
        s->active = true;
        s->x = (float)xs[i];
        s->y = 416.0f + (float)S.dy;
        s->angle = -1.5707963f;
        s->target_angle = -1.5707963f;
        s->cd = 0.55f + (float)i * 0.3f;
        s->flash = 0.0f;
    }
}

static int roll_upgrade_choices(void)
{
    int pool[UPG_COUNT];
    int n = 0;
    for(int key = 0; key < UPG_COUNT; key++) {
        if(key == UPG_REPAIR) {
            if(S.base_hp < S.base_max_hp) pool[n++] = key;
            continue;
        }
        if(S.upg[key] < upgrade_defs[key].max) pool[n++] = key;
    }
    for(int i = n - 1; i > 0; i--) {
        int j = irand(0, i);
        int tmp = pool[i];
        pool[i] = pool[j];
        pool[j] = tmp;
    }
    int picks = n < 3 ? n : 3;
    for(int i = 0; i < picks; i++) S.upgrade_choices[i] = pool[i];
    S.upgrade_choice_count = picks;
    if(S.base_hp <= 2) {
        int emergency = -1;
        for(int i = 0; i < n; i++) {
            if(pool[i] == UPG_REPAIR || pool[i] == UPG_REINFORCE) {
                emergency = pool[i];
                break;
            }
        }
        if(emergency >= 0) {
            bool found = false;
            for(int i = 0; i < picks; i++) {
                if(S.upgrade_choices[i] == emergency) found = true;
            }
            if(!found) {
                if(picks >= 3) S.upgrade_choices[2] = emergency;
                else if(picks < 3) S.upgrade_choices[picks++] = emergency;
                S.upgrade_choice_count = picks;
            }
        }
    }
    return picks;
}

static int ai_pick_upgrade(void)
{
    if(S.upgrade_choice_count <= 0) return -1;
    return S.upgrade_choices[rng_raw() % (uint32_t)S.upgrade_choice_count];
}

static void open_upgrade(void)
{
    if(S.mode != ZC_MODE_PLAYING) return;
    if(roll_upgrade_choices() <= 0) return;
    S.input_active = false;
    S.aim_valid = false;
    S.mode = ZC_MODE_UPGRADE;
    S.upgrade_overlay_t = 0.0f;
    S.ai_timer = 0.0f;
    S.hint_timer = 0.0f;
    S.flash_white = fmaxf(S.flash_white, 0.22f);
    sfx(ZC_SFX_LEVEL_UP);
    haptic(ZC_HAPTIC_LEVEL);
}

static void choose_upgrade(int key)
{
    if(S.mode != ZC_MODE_UPGRADE) return;
    if(key < 0 || key >= UPG_COUNT) return;
    char applied[80];
    char f1[16];
    if(key == UPG_REPAIR) {
        int amount = repair_amount_at(S.upg[UPG_REPAIR]);
        snprintf(applied, sizeof(applied), "修复 %d 点防线耐久", amount);
        S.upg[UPG_REPAIR] = S.upg[UPG_REPAIR] + 1 > upgrade_defs[key].max ? upgrade_defs[key].max : S.upg[UPG_REPAIR] + 1;
        heal_base(amount);
    }
    else {
        upgrade_desc(key, applied, sizeof(applied));
        S.upg[key] = S.upg[key] + 1 > upgrade_defs[key].max ? upgrade_defs[key].max : S.upg[key] + 1;
        if(key == UPG_REINFORCE) {
            S.base_max_hp = S.base_max_hp + 1 > 9 ? 9 : S.base_max_hp + 1;
            S.base_hp = clampi(S.base_hp + 1, 0, S.base_max_hp);
            S.base_flash = 0.3f;
            for(int i = 0; i < 14; i++) {
                add_particle(frand(120.0f, 270.0f), frand(396.0f + (float)S.dy, 430.0f + (float)S.dy),
                             frand(-30.0f, 30.0f), frand(-55.0f, -10.0f), frand(0.3f, 0.8f),
                             i % 2 ? ZC_BONE : ZC_ACID, irand(1, 2), 70.0f);
            }
        }
        if(key == UPG_SENTRY) sync_sentries();
    }
    (void)f1;
    S.toast_active = true;
    if(S.ai_mode) snprintf(S.toast_text, sizeof(S.toast_text), "AI · 已装配 · %s", upgrade_defs[key].name);
    else snprintf(S.toast_text, sizeof(S.toast_text), "已装配 · %s", upgrade_defs[key].name);
    snprintf(S.toast_sub, sizeof(S.toast_sub), "%s", applied);
    S.toast_t = 1.9f;
    S.toast_max_t = 1.9f;
    S.upgrade_choice_count = 0;
    S.mode = ZC_MODE_PLAYING;
    S.upgrade_delay = S.pending_upgrades > 0 ? 0.55f : 0.0f;
    S.fire_timer = 0.2f;
    S.flash_white = fmaxf(S.flash_white, 0.16f);
    sfx(ZC_SFX_CLICK);
}


static void update_aim_and_fire(float dt)
{
    S.recoil *= expf(-dt * 15.0f);
    S.muzzle_flash = fmaxf(0.0f, S.muzzle_flash - dt);
    S.fire_timer = fmaxf(0.0f, S.fire_timer - dt);

    if(S.input_active) {
        resolve_aim(S.input_x, S.input_y);
    }
    else {
        enemy_t * target = pick_auto_target();
        if(target != NULL) {
            float cx;
            float cy;
            enemy_center(target, &cx, &cy);
            S.aim_x = cx;
            S.aim_y = cy;
            S.aim_valid = true;
            S.aim_snapped = false;
        }
        else {
            S.aim_valid = false;
        }
    }

    if(S.aim_valid) {
        S.target_angle = clampf(atan2f(S.aim_y - (float)field_pivot_y(), S.aim_x - 195.0f),
                                -(float)M_PI + 0.17f, -0.17f);
    }
    else {
        S.target_angle = -(float)M_PI * 0.5f;
    }
    S.aim_angle = angle_lerp(S.aim_angle, S.target_angle, 1.0f - expf(-dt * 16.0f));

    if(S.aim_valid && S.fire_timer <= 0.0f) {
        if(S.input_active) fire_at(S.aim_x, S.aim_y, true);
        else if(pick_auto_target() != NULL) fire_at(S.aim_x, S.aim_y, false);
    }
}

static void update_wave(float dt)
{
    if(S.wave_intermission > 0.0f) {
        S.wave_intermission -= dt;
        if(S.wave_intermission <= 0.0f) begin_wave(S.wave_index + 1);
        return;
    }
    if(!S.wave_active) return;
    S.wave_clock += dt;
    if(S.wave_grace > 0.0f) S.wave_grace -= dt;
    else {
        while(S.wave_cursor < S.wave_count && S.wave_queue[S.wave_cursor].at <= S.wave_clock) {
            spawn_enemy(S.wave_queue[S.wave_cursor].type);
            S.wave_cursor++;
        }
    }
    int alive = 0;
    for(int i = 0; i < ZC_MAX_ENEMIES; i++) {
        if(S.enemies[i].active && !S.enemies[i].dead) alive++;
    }
    if(S.wave_cursor >= S.wave_count && alive == 0 && S.wave_grace <= 0.0f) {
        S.wave_clear_timer += dt;
        if(S.wave_clear_timer > 0.55f) finish_wave();
    }
    else {
        S.wave_clear_timer = 0.0f;
    }
}

static void update_enemies(float dt)
{
    for(int i = 0; i < ZC_MAX_ENEMIES; i++) {
        enemy_t * e = &S.enemies[i];
        if(!e->active || e->dead) continue;
        e->anim += dt * (e->slow_t > 0.0f ? 0.55f : 1.0f);
        e->hit_flash = fmaxf(0.0f, e->hit_flash - dt);
        e->attack_pulse = fmaxf(0.0f, e->attack_pulse - dt);
        if(e->slow_t > 0.0f) e->slow_t = fmaxf(0.0f, e->slow_t - dt);

        if(e->attacking) {
            e->attack_timer -= dt;
            if(e->attack_timer <= 0.0f) {
                e->attack_timer = e->type == E_BOSS ? 1.05f : 1.45f;
                e->attack_pulse = 0.28f;
                damage_base(1);
                if(S.mode != ZC_MODE_PLAYING) return;
            }
            continue;
        }
        float slow_factor = e->slow_t > 0.0f ? 1.0f - e->slow_amount : 1.0f;
        e->y += e->speed * slow_factor * dt;
        if(e->wobble != 0.0f) {
            e->x = clampf(e->base_x + sinf(e->anim * e->wobble_speed + e->phase) * e->wobble,
                          22.0f, (float)S.width - 22.0f);
        }
        if(e->y >= e->stop_y) {
            e->y = e->stop_y;
            if(e->type == E_BRUTE || e->type == E_BOSS) {
                e->attacking = true;
                e->attack_timer = e->type == E_BOSS ? 0.55f : 0.8f;
                e->attack_pulse = 0.3f;
                S.shake = fmaxf(S.shake, e->type == E_BOSS ? 5.0f : 3.0f);
            }
            else {
                e->dead = true;
                e->active = false;
                for(int j = 0; j < 12; j++) {
                    add_particle(e->x + frand(-8.0f, 8.0f), e->y - frand(2.0f, 18.0f),
                                 frand(-55.0f, 55.0f), frand(-80.0f, -5.0f), frand(0.25f, 0.65f),
                                 j % 3 ? ZC_BLOOD : ZC_BONE_D, irand(1, 2), 160.0f);
                }
                add_decal(e->x, e->y, 12.0f, ZC_RGB565(80, 25, 20), false);
                S.base_flash = 0.45f;
                damage_base(1);
                if(S.mode != ZC_MODE_PLAYING) return;
            }
        }
    }
}

static void update_sentries(float dt)
{
    int wanted = sentry_count_at(S.upg[UPG_SENTRY]);
    if(wanted <= 0) return;
    for(int i = 0; i < wanted && i < ZC_MAX_SENTRIES; i++) {
        sentry_t * s = &S.sentries[i];
        if(!s->active) continue;
        s->cd -= dt;
        s->flash = fmaxf(0.0f, s->flash - dt);
        enemy_t * target = NULL;
        float best_d = 1.0e9f;
        float tx = 0.0f;
        float ty = 0.0f;
        for(int k = 0; k < ZC_MAX_ENEMIES; k++) {
            enemy_t * e = &S.enemies[k];
            if(!e->active || e->dead) continue;
            float cx;
            float cy;
            enemy_center(e, &cx, &cy);
            float dx = cx - s->x;
            float dy = cy - (s->y - 14.0f);
            float d = dx * dx + dy * dy;
            if(d < best_d) {
                best_d = d;
                target = e;
                tx = cx;
                ty = cy;
            }
        }
        if(target != NULL) {
            s->target_angle = clampf(atan2f(ty - (s->y - 12.0f), tx - s->x),
                                     -(float)M_PI + 0.12f, -0.12f);
            s->angle = angle_lerp(s->angle, s->target_angle, 1.0f - expf(-dt * 12.0f));
            if(s->cd <= 0.0f) {
                s->cd = sentry_interval_at(S.upg[UPG_SENTRY]);
                s->flash = 0.08f;
                float mx = s->x + cosf(s->angle) * 15.0f;
                float my = s->y - 12.0f + sinf(s->angle) * 15.0f;
                int slot = S.tracer_head;
                S.tracer_head = (S.tracer_head + 1) % ZC_MAX_TRACERS;
                S.tracers[slot].active = true;
                S.tracers[slot].x1 = mx;
                S.tracers[slot].y1 = my;
                S.tracers[slot].x2 = tx;
                S.tracers[slot].y2 = ty;
                S.tracers[slot].t = 0.1f;
                S.tracers[slot].max_t = 0.1f;
                for(int j = 0; j < 3; j++) {
                    add_particle(mx, my, frand(-25.0f, 25.0f), frand(-30.0f, 5.0f),
                                 frand(0.1f, 0.22f), ZC_GOLD, 1, 20.0f);
                }
                damage_enemy(target, (float)sentry_damage_at(S.upg[UPG_SENTRY]), false, false, 0.0f, 0.0f);
                sfx(ZC_SFX_SENTRY);
            }
        }
        else {
            s->angle = angle_lerp(s->angle, -1.5707963f, 1.0f - expf(-dt * 3.0f));
        }
    }
}

static void update_shells(float dt)
{
    for(int i = 0; i < ZC_MAX_SHELLS; i++) {
        shell_t * s = &S.shells[i];
        if(!s->active) continue;
        s->t += dt / s->dur;
        if(s->t >= 1.0f) {
            s->active = false;
            detonate(s);
        }
    }
}

static void update_fires(float dt)
{
    for(int i = 0; i < ZC_MAX_FIRES; i++) {
        fire_t * f = &S.fires[i];
        if(!f->active) continue;
        f->t -= dt;
        f->tick -= dt;
        if(f->tick <= 0.0f) {
            f->tick = 0.38f;
            for(int k = 0; k < ZC_MAX_ENEMIES; k++) {
                enemy_t * e = &S.enemies[k];
                if(!e->active || e->dead) continue;
                float cx;
                float cy;
                enemy_center(e, &cx, &cy);
                float dx = cx - f->x;
                float dy = cy - f->y;
                float reach = f->radius + e->radius * 0.35f;
                if(dx * dx + dy * dy <= reach * reach) {
                    damage_enemy(e, (float)(f->damage > 0 ? f->damage : 1), false, false, 0.0f, 0.0f);
                }
            }
            for(int j = 0; j < 2; j++) {
                add_particle(f->x + frand(-f->radius * 0.5f, f->radius * 0.5f), f->y - 2.0f,
                             frand(-4.0f, 4.0f), frand(-32.0f, -12.0f), frand(0.2f, 0.5f),
                             j ? ZC_ORANGE : ZC_GOLD, 1, -25.0f);
            }
        }
        if(f->t <= 0.0f) f->active = false;
    }
}

static void update_effects(float dt)
{
    for(int i = 0; i < ZC_MAX_PARTICLES; i++) {
        particle_t * p = &S.particles[i];
        if(!p->active) continue;
        p->life -= dt;
        p->x += p->vx * dt;
        p->y += p->vy * dt;
        p->vy += p->gravity * dt;
        p->vx *= 0.985f;
        if(p->life <= 0.0f) p->active = false;
    }
    for(int i = 0; i < ZC_MAX_BLASTS; i++) {
        blast_t * b = &S.blasts[i];
        if(!b->active) continue;
        b->t += dt;
        if(b->t >= b->dur) b->active = false;
    }
    for(int i = 0; i < ZC_MAX_TRACERS; i++) {
        tracer_t * t = &S.tracers[i];
        if(!t->active) continue;
        t->t -= dt;
        if(t->t <= 0.0f) t->active = false;
    }
    for(int i = 0; i < ZC_MAX_FLOATERS; i++) {
        floater_t * f = &S.floaters[i];
        if(!f->active) continue;
        f->life -= dt;
        f->y -= dt * 20.0f;
        if(f->life <= 0.0f) f->active = false;
    }
    S.shake *= expf(-dt * 8.5f);
    if(S.shake < 0.08f) S.shake = 0.0f;
    if(S.shake > 0.0f) {
        S.shake_x = (int)lroundf(frand(-S.shake, S.shake));
        S.shake_y = (int)lroundf(frand(-S.shake, S.shake));
    }
    else {
        S.shake_x = 0;
        S.shake_y = 0;
    }
    S.flash_red = fmaxf(0.0f, S.flash_red - dt * 2.1f);
    S.flash_white = fmaxf(0.0f, S.flash_white - dt * 2.8f);
    S.base_flash = fmaxf(0.0f, S.base_flash - dt);
    if(S.banner_active) {
        S.banner_t -= dt;
        if(S.banner_t <= 0.0f) S.banner_active = false;
    }
    if(S.toast_active) {
        S.toast_t -= dt;
        if(S.toast_t <= 0.0f) S.toast_active = false;
    }
}

static void update_game(float dt)
{
    S.run_time = fmaxf(0.0f, S.t - S.run_start);
    if(S.input_active) S.ai_idle = 0.0f;
    else {
        S.ai_idle += dt;
        if(S.ai_idle >= 10.0f) S.ai_mode = true;
    }
    float target_xp = clampf((float)S.xp / (float)S.xp_need, 0.0f, 1.0f);
    S.display_xp += (target_xp - S.display_xp) * (1.0f - expf(-dt * 9.0f));
    S.hint_timer = fmaxf(0.0f, S.hint_timer - dt);
    update_aim_and_fire(dt);
    update_wave(dt);
    if(S.mode != ZC_MODE_PLAYING) {
        update_effects(dt);
        return;
    }
    update_enemies(dt);
    if(S.mode != ZC_MODE_PLAYING) {
        update_effects(dt);
        return;
    }
    update_sentries(dt);
    update_shells(dt);
    update_fires(dt);
    update_effects(dt);
    for(int i = 0; i < ZC_MAX_ENEMIES; i++) {
        if(S.enemies[i].dead) S.enemies[i].active = false;
    }
    if(S.boss != NULL && S.boss->dead) S.boss = NULL;
    if(S.mode != ZC_MODE_PLAYING) return;
    if(S.pending_upgrades > 0) {
        S.upgrade_delay -= dt;
        if(S.upgrade_delay <= 0.0f) {
            S.pending_upgrades--;
            open_upgrade();
        }
    }
}


static float ease_out_cubic(float t)
{
    t = clampf(t, 0.0f, 1.0f);
    float u = 1.0f - t;
    return 1.0f - u * u * u;
}

static uint32_t mix32(uint32_t x)
{
    x ^= x >> 16;
    x *= 0x7FEB352DU;
    x ^= x >> 15;
    x *= 0x846CA68BU;
    x ^= x >> 16;
    return x;
}

static float local_rand(uint32_t * state)
{
    *state = mix32(*state + 0x9E3779B9U);
    return (float)(*state >> 8) / 16777216.0f;
}

static void ui_recta(int x, int y, int w, int h, uint16_t color, uint8_t alpha)
{
    if(alpha >= 250) zc_rect_world(x, y, w, h, color);
    else zc_blend_rect_world(x, y, w, h, color, alpha);
}

static void draw_heart_icon(int x, int y, bool filled, int scale, bool flash)
{
    zc_heart(x, y, filled, scale, flash);
}

static void draw_speaker_button(int cx, int cy, bool on)
{
    int x = cx - 8;
    int y = cy - 8;
    zc_blend_rect(x, y, 16, 16, ZC_RGB565(14, 20, 11), 184);
    zc_outline(x, y, 16, 16, 1, ZC_RGB565(131, 145, 78));
    zc_rect(x + 3, y + 6, 3, 4, ZC_BONE_D);
    zc_rect(x + 6, y + 4, 2, 8, ZC_BONE_D);
    zc_rect(x + 8, y + 3, 1, 10, ZC_BONE_D);
    if(on) {
        zc_rect(x + 10, y + 5, 1, 6, ZC_ACID);
        zc_rect(x + 12, y + 3, 1, 10, ZC_ACID_D);
        zc_rect(x + 11, y + 4, 1, 1, ZC_ACID_D);
        zc_rect(x + 11, y + 11, 1, 1, ZC_ACID_D);
    }
    else {
        zc_rect(x + 10, y + 4, 1, 1, ZC_RED_D);
        zc_rect(x + 11, y + 5, 1, 1, ZC_RED_D);
        zc_rect(x + 12, y + 6, 1, 1, ZC_RED);
        zc_rect(x + 10, y + 11, 1, 1, ZC_RED_D);
        zc_rect(x + 11, y + 10, 1, 1, ZC_RED_D);
        zc_rect(x + 12, y + 9, 1, 1, ZC_RED);
    }
}

static void draw_back_chevron(int x, int y)
{
    for(int i = 0; i < 7; i++) {
        int dx = 8 - (i < 4 ? i * 2 : (6 - i) * 2);
        zc_rect(x + dx, y + i * 2, 2, 2, ZC_ACID);
    }
}

static void draw_decals(void)
{
    for(int i = 0; i < ZC_MAX_DECALS; i++) {
        decal_t * d = &S.decals[i];
        if(!d->active) continue;
        uint32_t rng = d->seed ? d->seed : 1U;
        if(d->scorch) {
            zc_blend_circle((int)d->x + zc.ox, (int)d->y + zc.oy, (int)d->size,
                            ZC_RGB565(10, 12, 7), 82);
            for(int k = 0; k < 5; k++) {
                uint16_t col = k % 2 ? ZC_RGB565(43, 26, 14) : ZC_RGB565(22, 19, 9);
                int x = (int)(d->x + (local_rand(&rng) * 2.0f - 1.0f) * d->size) + zc.ox;
                int y = (int)(d->y + (local_rand(&rng) * 2.0f - 1.0f) * d->size * 0.45f) + zc.oy;
                zc_rect(x, y, 2 + (int)(local_rand(&rng) * 3.0f), 1, col);
            }
        }
        else {
            int count = 5 + (int)(d->size / 4.0f);
            for(int k = 0; k < count; k++) {
                float a = local_rand(&rng) * ZC_TAU;
                float r = sqrtf(local_rand(&rng)) * d->size;
                uint16_t col = k % 3 == 0 ? ZC_RGB565(94, 33, 27) : d->color;
                int x = (int)(d->x + cosf(a) * r) + zc.ox;
                int y = (int)(d->y + sinf(a) * r * 0.48f) + zc.oy;
                zc_blend_rect(x, y, 1 + (int)(local_rand(&rng) * 3.0f),
                              1 + (int)(local_rand(&rng) * 2.0f), col, 107);
            }
        }
    }
}

static void draw_fires(void)
{
    for(int i = 0; i < ZC_MAX_FIRES; i++) {
        fire_t * f = &S.fires[i];
        if(!f->active) continue;
        float fade = clampf(f->t / 0.45f, 0.0f, 1.0f);
        uint8_t a = (uint8_t)(fade * 255.0f);
        zc_blend_circle((int)f->x + zc.ox, (int)f->y + 2 + zc.oy, (int)f->radius + 2,
                        ZC_RGB565(18, 12, 7), (uint8_t)(fade * 128.0f));
        for(int k = 0; k < 4; k++) {
            float fx = f->x + ((float)k - 1.5f) * (f->radius * 0.38f);
            float phase = S.t * 12.0f + (float)k * 2.1f + f->seed;
            float h = 7.0f + sinf(phase) * 3.0f + (float)(k % 2) * 3.0f;
            zc_blend_rect_world((int)(fx - 3.0f), (int)(f->y - h * 0.3f), 7,
                                (int)fmaxf(3.0f, h * 0.8f), ZC_RGB565(90, 46, 22), a);
            zc_blend_rect_world((int)(fx - 2.0f), (int)(f->y - h * 0.55f), 4,
                                (int)fmaxf(2.0f, h * 0.75f), k % 2 ? ZC_ORANGE : ZC_RGB565(207, 106, 43), a);
            zc_blend_rect_world((int)(fx - 1.0f), (int)(f->y - h * 0.8f), 2,
                                (int)fmaxf(2.0f, h * 0.55f), ZC_GOLD, a);
        }
        for(int k = 0; k < 3; k++) {
            int ex = (int)(f->x + frand(-f->radius, f->radius));
            zc_blend_rect_world(ex, (int)(f->y - frand(4.0f, 20.0f) - fmodf(S.t * 12.0f, 6.0f)),
                                1, 1, ZC_ORANGE, a);
        }
    }
}

static void draw_enemy(const enemy_t * e)
{
    if(e->dead || !e->active) return;
    const zc_sprite_def_t * def = sprite_for(e->type);
    float fps = e->type == E_RUNNER ? 5.2f : e->type == E_BRUTE ? 2.3f : e->type == E_BOSS ? 2.0f : 3.4f;
    int frame = ((int)(e->anim * fps + e->phase)) & 1;
    float lunge = e->attacking ? sinf(e->anim * 22.0f) * 1.5f : 0.0f;
    float bob = sinf(e->anim * 4.0f + e->phase) * (e->type == E_BOSS ? 1.2f : 0.8f);
    int fw = def->w * def->scale;
    int fh = def->h * def->scale;
    int x = (int)lroundf(e->x + lunge - (float)fw * 0.5f);
    int y = (int)lroundf(e->y - (float)fh + bob);
    uint8_t alpha = (uint8_t)(clampf((e->y - 106.0f) / 17.0f, 0.28f, 1.0f) * 255.0f);

    int sw = (int)((float)fw * (e->type == E_BOSS ? 0.5f : 0.34f));
    zc_blend_rect_world((int)e->x - sw / 2, (int)e->y - 2, sw, 3, ZC_BLACK, 97);
    if(e->type == E_BOSS) {
        float glow = 0.08f + 0.035f * sinf(S.t * 4.2f);
        zc_blend_circle((int)e->x + zc.ox, (int)e->y - 5 + zc.oy, 36,
                        ZC_RGB565(212, 54, 38), (uint8_t)(glow * 255.0f));
    }
    if(e->slow_t > 0.0f) {
        zc_blend_circle((int)e->x + zc.ox, (int)e->y - 5 + zc.oy,
                        (int)fmaxf(13.0f, (float)fw * 0.36f), ZC_RGB565(120, 225, 211), 64);
        int spark = ((int)(S.t * 10.0f)) & 3;
        for(int i = 0; i < 3; i++) {
            int sx = (int)(e->x + sinf(S.t * 2.0f + (float)i * 2.1f) * (float)fw * 0.35f);
            int sy = (int)(e->y - 5.0f - cosf(S.t * 3.0f + (float)i) * 10.0f);
            zc_blend_rect_world(sx, sy, 1, 1, i == spark % 3 ? ZC_CYAN : ZC_RGB565(134, 217, 196), 140);
        }
    }
    zc_art_sprite_draw(e->type, frame, x, y, e->hit_flash > 0.0f ? 1 : 0, alpha);
    if(e->type == E_BOSS) {
        float core = 0.5f + 0.5f * sinf(S.t * 5.0f);
        zc_blend_rect_world((int)e->x - 1, (int)(e->y - (float)fh * 0.55f), 3, 3,
                            ZC_RGB565(255, 92, 56), (uint8_t)((0.25f + core * 0.45f) * 255.0f));
    }
    if(e->type == E_BRUTE && e->hp < e->max_hp) {
        int bw = fw - 8;
        int bx = (int)e->x - bw / 2;
        int by = (int)e->y - fh - 6;
        zc_blend_rect_world(bx, by, bw, 3, ZC_RGB565(6, 8, 5), 204);
        zc_rect_world(bx + 1, by + 1,
                      (int)((float)(bw - 2) * clampf((float)e->hp / (float)e->max_hp, 0.0f, 1.0f)),
                      1, ZC_RED);
    }
    if(e->attacking && sinf(e->anim * 18.0f) > 0.3f) {
        zc_blend_rect_world((int)e->x - 12, (int)e->y - 24, 2, 1, ZC_RED, 178);
        zc_blend_rect_world((int)e->x + 10, (int)e->y - 20, 2, 1, ZC_RED, 178);
    }
}

static void draw_shells(void)
{
    for(int i = 0; i < ZC_MAX_SHELLS; i++) {
        shell_t * s = &S.shells[i];
        if(!s->active) continue;
        float p = clampf(s->t, 0.0f, 1.0f);
        float gx = s->sx + (s->tx - s->sx) * p;
        float gy = s->sy + (s->ty - s->sy) * p;
        float arc = sinf(p * (float)M_PI) * s->arc;
        int x = (int)lroundf(gx);
        int y = (int)lroundf(gy - arc);
        zc_blend_rect_world(x - 2, (int)gy, 5, 1, ZC_RGB565(5, 7, 5), 82);
        for(int k = 1; k <= 3; k++) {
            float pp = clampf(p - (float)k * 0.035f, 0.0f, 1.0f);
            int tx = (int)lroundf(s->sx + (s->tx - s->sx) * pp);
            int ty = (int)lroundf(s->sy + (s->ty - s->sy) * pp - sinf(pp * (float)M_PI) * s->arc);
            zc_blend_rect_world(tx, ty, 1, 1, k == 1 ? s->color : ZC_ORANGE, 140);
        }
        zc_rect_world(x - 3, y - 3, 6, 6, ZC_INK);
        zc_rect_world(x - 2, y - 2, 4, 4, s->color);
        zc_rect_world(x - 1, y - 1, 2, 2, ZC_WHITE);
    }
}

static void draw_blasts(void)
{
    for(int i = 0; i < ZC_MAX_BLASTS; i++) {
        blast_t * b = &S.blasts[i];
        if(!b->active) continue;
        float p = clampf(b->t / b->dur, 0.0f, 1.0f);
        float r = b->radius * ease_out_cubic(p);
        float alpha = 1.0f - p;
        zc_blend_circle((int)b->x + zc.ox, (int)b->y + zc.oy, (int)fmaxf(2.0f, r),
                        b->crit ? ZC_RGB565(163, 47, 37) : ZC_RGB565(60, 36, 19),
                        (uint8_t)(alpha * 0.7f * 255.0f));
        zc_blend_circle((int)b->x + zc.ox, (int)b->y + zc.oy, (int)fmaxf(1.0f, r * 0.72f),
                        b->crit ? ZC_RED : ZC_ORANGE, (uint8_t)(alpha * 0.8f * 255.0f));
        zc_blend_circle((int)b->x + zc.ox, (int)b->y + zc.oy, (int)fmaxf(1.0f, r * 0.38f),
                        ZC_GOLD, (uint8_t)(alpha * 255.0f));
        if(r > 3.0f) {
            zc_blend_circle((int)b->x + zc.ox, (int)b->y + zc.oy, (int)fmaxf(1.0f, r * 0.16f),
                            ZC_RGB565(255, 246, 207), (uint8_t)(alpha * 0.8f * 255.0f));
        }
        for(int k = 0; k < 18; k++) {
            float a = (float)k / 18.0f * ZC_TAU + p * 0.5f;
            zc_blend_rect_world((int)(b->x + cosf(a) * r), (int)(b->y + sinf(a) * r * 0.72f),
                                2, 1, k % 3 == 0 ? ZC_BONE : ZC_ORANGE,
                                (uint8_t)(alpha * 0.55f * 255.0f));
        }
    }
}

static void draw_particles(void)
{
    for(int i = 0; i < ZC_MAX_PARTICLES; i++) {
        particle_t * p = &S.particles[i];
        if(!p->active) continue;
        float a = clampf(p->life / p->max_life, 0.0f, 1.0f);
        ui_recta((int)p->x, (int)p->y, p->size, p->size, p->color, (uint8_t)(a * 255.0f));
    }
}

static void draw_tracers(void)
{
    for(int i = 0; i < ZC_MAX_TRACERS; i++) {
        tracer_t * t = &S.tracers[i];
        if(!t->active) continue;
        zc_line_world((int)t->x1, (int)t->y1, (int)t->x2, (int)t->y2, 1, ZC_GOLD);
        zc_rect_world((int)t->x2 - 1, (int)t->y2 - 1, 2, 2, ZC_WHITE);
    }
}

static void draw_floaters(void)
{
    for(int i = 0; i < ZC_MAX_FLOATERS; i++) {
        floater_t * f = &S.floaters[i];
        if(!f->active) continue;
        zc_text(f->text, (int)f->x + zc.ox, (int)f->y + zc.oy, f->scale, f->color,
                ZC_ALIGN_CENTER, f->scale);
    }
}

static void draw_sentries(void)
{
    for(int i = 0; i < ZC_MAX_SENTRIES; i++) {
        sentry_t * s = &S.sentries[i];
        if(!s->active) continue;
        int x = (int)lroundf(s->x);
        int y = (int)lroundf(s->y);
        zc_rect_world(x - 13, y - 2, 26, 5, ZC_RGB565(36, 42, 25));
        zc_rect_world(x - 10, y - 6, 20, 5, ZC_RGB565(17, 22, 13));
        zc_rect_world(x - 7, y + 3, 14, 2, ZC_RGB565(11, 14, 8));
        zc_rect_world(x - 2, y - 1, 4, 8, ZC_RGB565(61, 69, 41));
        zc_rect_world(x - 8, y - 12, 16, 8, ZC_RGB565(10, 13, 8));
        zc_rect_world(x - 6, y - 10, 12, 5, ZC_RGB565(75, 86, 51));
        zc_rect_world(x - 4, y - 10, 4, 2, ZC_RGB565(114, 125, 75));
        float mx = (float)x + cosf(s->angle) * 15.0f;
        float my = (float)(y - 8) + sinf(s->angle) * 15.0f;
        zc_line_world(x, y - 8, (int)lroundf(mx), (int)lroundf(my), 4, ZC_RGB565(10, 13, 8));
        zc_line_world(x, y - 8, (int)lroundf(mx), (int)lroundf(my), 2, ZC_RGB565(138, 141, 93));
        if(s->flash > 0.0f) {
            zc_rect_world((int)lroundf(mx) - 2, (int)lroundf(my) - 2, 4, 4, ZC_GOLD);
            zc_rect_world((int)lroundf(mx) - 1, (int)lroundf(my) - 1, 2, 2, ZC_WHITE);
        }
        zc_rect_world(x + 4, y - 6, 2, 2, sinf(S.t * 4.0f + s->x) > 0.0f ? ZC_ACID : ZC_ACID_DEEP);
    }
}

static void draw_muzzle_flash(void)
{
    if(S.muzzle_flash <= 0.0f) return;
    float a = clampf(S.muzzle_flash / 0.085f, 0.0f, 1.0f);
    float offs[2];
    int count;
    if(S.upg[UPG_TWIN] > 0) {
        offs[0] = -4.0f * (float)M_PI / 180.0f;
        offs[1] = 4.0f * (float)M_PI / 180.0f;
        count = 2;
    }
    else {
        offs[0] = 0.0f;
        count = 1;
    }
    for(int i = 0; i < count; i++) {
        float mx;
        float my;
        muzzle_point(offs[i], 0.0f, &mx, &my);
        int x = (int)lroundf(mx);
        int y = (int)lroundf(my);
        zc_blend_circle(x + zc.ox, y + zc.oy, 13, ZC_ORANGE, (uint8_t)(a * 0.16f * 255.0f));
        zc_blend_rect_world(x - 5, y - 1, 10, 2, ZC_GOLD, (uint8_t)(a * 255.0f));
        zc_blend_rect_world(x - 1, y - 5, 2, 10, ZC_GOLD, (uint8_t)(a * 255.0f));
        zc_blend_rect_world(x - 2, y - 2, 4, 4, ZC_WHITE, (uint8_t)(a * 255.0f));
        zc_blend_rect_world(x - 4, y - 4, 2, 2, ZC_ORANGE, (uint8_t)(a * 255.0f));
        zc_blend_rect_world(x + 2, y + 2, 2, 2, ZC_ORANGE, (uint8_t)(a * 255.0f));
    }
}

static void draw_reticle(void)
{
    if(!S.aim_valid || S.mode != ZC_MODE_PLAYING) return;
    bool manual = S.input_active;
    int x = (int)lroundf(S.aim_x) + zc.ox;
    int y = (int)lroundf(S.aim_y) + zc.oy;
    uint8_t alpha = manual ? 242 : 77;
    uint16_t col = S.aim_snapped ? ZC_ACID : ZC_BONE_D;
    int r = manual ? 13 : 10;
    int arm = manual ? 5 : 3;
    zc_blend_rect(x - r, y - r, arm, 1, col, alpha);
    zc_blend_rect(x - r, y - r, 1, arm, col, alpha);
    zc_blend_rect(x + r - arm, y - r, arm, 1, col, alpha);
    zc_blend_rect(x + r - 1, y - r, 1, arm, col, alpha);
    zc_blend_rect(x - r, y + r, arm, 1, col, alpha);
    zc_blend_rect(x - r, y + r - arm + 1, 1, arm, col, alpha);
    zc_blend_rect(x + r - arm, y + r, arm, 1, col, alpha);
    zc_blend_rect(x + r - 1, y + r - arm + 1, 1, arm, col, alpha);
    if(manual) {
        float blink = 0.55f + 0.45f * sinf(S.t * 8.0f);
        zc_blend_rect(x - 1, y - 1, 2, 2, col, (uint8_t)(alpha * blink));
        for(int i = 0; i < 4; i++) {
            float a = S.t * 1.6f + (float)i * (float)M_PI * 0.5f;
            zc_blend_rect((int)lroundf((float)x + cosf(a) * 18.0f),
                          (int)lroundf((float)y + sinf(a) * 18.0f), 2, 2, col,
                          (uint8_t)(alpha * 0.45f));
        }
    }
}


static void draw_hud(void)
{
    int w = S.width;
    int shift = S.safe ? 10 : 0;
    int right = w - 14 - shift;

    zc_rect(0, 0, w, 4, ZC_RGB565(8, 11, 7));
    int xp_w = (int)lroundf((float)(w - 2) * clampf(S.display_xp, 0.0f, 1.0f));
    zc_rect(0, 0, xp_w, 4, ZC_RGB565(86, 103, 43));
    zc_rect(0, 1, xp_w, 2, ZC_ACID_D);
    if(xp_w > 0) zc_rect(xp_w > 2 ? xp_w - 2 : 0, 0, 2, 4, ZC_ACID);
    for(int x = 13; x < w; x += 26) zc_blend_rect(x, 0, 1, 4, ZC_RGB565(4, 7, 4), 140);

    zc_rect(0, 4, w, 42, ZC_RGB565(15, 21, 13));
    zc_rect(0, 4, w, 1, ZC_RGB565(27, 36, 20));
    for(int y = 8; y < 45; y += 4) zc_blend_rect(0, y, w, 1, ZC_RGB565(95, 109, 63), 9);
    zc_rect(0, 45, w, 1, ZC_RGB565(62, 73, 42));
    zc_rect(0, 46, w, 2, ZC_RGB565(7, 10, 6));
    int rivets[4][2] = {{5, 8}, {w - 7, 8}, {5, 39}, {w - 7, 39}};
    for(int i = 0; i < 4; i++) {
        zc_rect(rivets[i][0], rivets[i][1], 2, 2, ZC_RGB565(79, 89, 57));
        zc_rect(rivets[i][0], rivets[i][1], 1, 1, ZC_RGB565(152, 161, 103));
    }
    zc_rect(127, 7, 1, 35, ZC_RGB565(30, 39, 23));
    zc_rect(258, 7, 1, 35, ZC_RGB565(30, 39, 23));

    zc_rect(11 + shift, 11, 2, 24, ZC_OLIVE);
    zc_text("LV", 17 + shift, 11, 1, ZC_BONE_DD, ZC_ALIGN_LEFT, 1);
    char num[16];
    pad2(S.level, num);
    zc_text(num, 30 + shift, 7, 2, ZC_BONE, ZC_ALIGN_LEFT, 2);
    zc_rect(16 + shift, 30, 86, 5, ZC_RGB565(5, 8, 5));
    zc_outline(16 + shift, 30, 86, 5, 1, ZC_RGB565(45, 54, 33));
    int bar_w = (int)lroundf(82.0f * clampf(S.display_xp, 0.0f, 1.0f));
    if(bar_w > 0) {
        zc_rect(18 + shift, 32, bar_w, 1, ZC_ACID_D);
        zc_rect(18 + shift, 32, bar_w < 70 ? bar_w : 70, 1, ZC_ACID);
    }
    for(int i = 1; i < 4; i++) zc_rect(16 + shift + i * 21, 31, 1, 3, ZC_RGB565(21, 27, 16));

    char wave_title[40];
    snprintf(wave_title, sizeof(wave_title), "第 %d 波", S.wave_index > 0 ? S.wave_index : 1);
    zc_cn_text(wave_title, 192, 6, 12, ZC_BONE, ZC_ALIGN_CENTER, true);
    int cycle = ((S.wave_index > 0 ? S.wave_index : 1) - 1) % 5 + 1;
    int total_pips = 5;
    int gap = 4;
    int pip_w = 9;
    int start_x = 192 - (total_pips * pip_w + (total_pips - 1) * gap) / 2;
    for(int i = 0; i < total_pips; i++) {
        bool active = i < cycle;
        bool current = i == cycle - 1;
        bool boss_pip = i == total_pips - 1;
        uint16_t col = ZC_RGB565(37, 45, 28);
        if(boss_pip && active) col = current ? ZC_RED : ZC_RED_D;
        else if(current) col = ZC_ACID;
        else if(active) col = ZC_OLIVE_L;
        int px = start_x + i * (pip_w + gap);
        zc_rect(px, 29, pip_w, 4, col);
        if(current) zc_rect(px, 29, pip_w, 1, boss_pip ? ZC_RGB565(255, 178, 138) : ZC_WHITE);
        if(boss_pip && !active) {
            zc_blend_rect(px, 28, pip_w, 1, ZC_RGB565(142, 46, 36), 115);
            zc_blend_rect(px, 33, pip_w, 1, ZC_RGB565(142, 46, 36), 115);
        }
    }

    zc_cn_text("防线", right, 5, 9, ZC_BONE_DD, ZC_ALIGN_RIGHT, false);
    int hearts = S.base_max_hp;
    int heart_w = 12;
    int total_heart_w = hearts * heart_w - 2;
    int hx = right - total_heart_w;
    bool heart_flash = S.base_flash > 0.0f && (((int)(S.t * 32.0f)) & 1) == 0;
    for(int i = 0; i < hearts; i++) {
        int jitter = heart_flash ? (int)lroundf(sinf(S.t * 70.0f + (float)i)) : 0;
        draw_heart_icon(hx + i * heart_w + jitter, 19, i < S.base_hp, 2,
                        heart_flash && i >= S.base_hp - 1);
    }
    char score_buf[32];
    char score_num[16];
    pad5(S.score, score_num);
    snprintf(score_buf, sizeof(score_buf), "SCORE %s", score_num);
    zc_text(score_buf, right, 36, 1, ZC_BONE_DD, ZC_ALIGN_RIGHT, 1);

    uint16_t skull = ZC_RGB565(139, 147, 96);
    zc_rect(16, 39, 4, 3, skull);
    zc_rect(17, 37, 2, 2, skull);
    zc_rect(16, 41, 1, 1, skull);
    zc_rect(19, 41, 1, 1, skull);
    char kills[20];
    snprintf(kills, sizeof(kills), "x%d", S.kills);
    zc_text(kills, 24, 37, 1, ZC_BONE_DD, ZC_ALIGN_LEFT, 1);

    if(S.ai_mode) {
        zc_blend_rect(176, 35, 38, 10, ZC_RGB565(10, 14, 8), 210);
        zc_outline(176, 35, 38, 10, 1, ZC_ACID_D);
        zc_text("AI", 195, 37, 1, ZC_ACID, ZC_ALIGN_CENTER, 1);
    }
}

static void draw_boss_bar(void)
{
    if(S.boss == NULL || S.boss->dead || !S.boss->active) return;
    if(S.mode == ZC_MODE_TITLE || S.mode == ZC_MODE_GAMEOVER) return;
    float ratio = clampf((float)S.boss->hp / (float)S.boss->max_hp, 0.0f, 1.0f);
    float pulse = 0.45f + 0.55f * sinf(S.t * 5.5f);
    int px = S.safe ? 24 : 14;
    int py = 52;
    int pw = S.width - px * 2;
    int ph = 21;
    zc_blend_rect(px, py, pw, ph, ZC_RGB565(8, 11, 7), 222);
    zc_outline(px, py, pw, ph, 1, pulse > 0.6f ? ZC_RGB565(129, 51, 42) : ZC_RGB565(86, 39, 31));
    zc_blend_rect(px + 1, py + 1, pw - 2, 1, ZC_RGB565(221, 94, 67), 36);
    zc_text("BOSS", 22 + (S.safe ? 10 : 0), py + 7, 1, ZC_RED, ZC_ALIGN_LEFT, 1);
    zc_cn_text("屠宰者", 52 + (S.safe ? 10 : 0), py + 3, 10, ZC_BONE_D, ZC_ALIGN_LEFT, false);
    int bx = 99 + (S.safe ? 10 : 0);
    int bw = pw - (bx - px) - 8;
    zc_rect(bx, py + 7, bw, 7, ZC_RGB565(5, 8, 6));
    zc_outline(bx, py + 7, bw, 7, 1, ZC_RGB565(57, 36, 31));
    int fw = (int)lroundf((float)(bw - 2) * ratio);
    if(fw > 0) {
        zc_rect(bx + 1, py + 8, fw, 5, ZC_RED_D);
        zc_rect(bx + 1, py + 8, fw, 2, ZC_RED);
    }
    for(int i = 1; i < 8; i++) zc_blend_rect(bx + i * 33, py + 8, 1, 5, ZC_RGB565(10, 8, 6), 82);
}


static void draw_banner(void)
{
    if(!S.banner_active) return;
    float elapsed = 1.0f - clampf(S.banner_t / S.banner_max_t, 0.0f, 1.0f);
    float alpha = fminf(clampf(elapsed * 6.0f, 0.0f, 1.0f), clampf(S.banner_t / 0.28f, 0.0f, 1.0f));
    if(alpha <= 0.01f) return;
    int top_base = strcmp(S.banner_kind, "boss") == 0 ? 82 : 140;
    int top = top_base + (int)lroundf((1.0f - ease_out_cubic(clampf(elapsed * 4.5f, 0.0f, 1.0f))) * -12.0f);
    zc_blend_rect(0, top, S.width, 68, ZC_RGB565(5, 8, 5), (uint8_t)(alpha * 209.0f));
    zc_rect(0, top + 2, S.width, 1, S.banner_color);
    zc_blend_rect(0, top + 65, S.width, 1, ZC_RGB565(201, 198, 135), 71);
    for(int i = 0; i < 9; i++) {
        uint16_t c = i % 2 ? S.banner_color : ZC_OLIVE_D;
        zc_rect(6 + i * 7, top + 9, 4, 2, c);
        zc_rect(S.width - 10 - i * 7, top + 9, 4, 2, c);
    }
    zc_text(S.banner_eng, 195, top + 12, 1, S.banner_color, ZC_ALIGN_CENTER, 2);
    zc_cn_text(S.banner_title, 195, top + 22, 21, ZC_BONE, ZC_ALIGN_CENTER, true);
    zc_cn_text(S.banner_sub, 195, top + 50, 10, ZC_BONE_D, ZC_ALIGN_CENTER, false);
    zc_rect(28 + (int)lroundf(sinf(elapsed * 31.0f) * 9.0f), top + 30, 7, 1, S.banner_color);
    zc_rect(345 + (int)lroundf(cosf(elapsed * 23.0f) * 8.0f), top + 42, 10, 1, S.banner_color);
}

static void draw_toast(void)
{
    if(!S.toast_active) return;
    float a = fminf(clampf(S.toast_t / 0.35f, 0.0f, 1.0f),
                    clampf((S.toast_max_t - S.toast_t) * 8.0f, 0.0f, 1.0f));
    int y = S.banner_active ? 334 : 80;
    int cnw = zc_cn_width(S.toast_text, 12);
    int w = cnw + 32;
    if(w < 180) w = 180;
    if(w > 320) w = 320;
    int x = 195 - w / 2;
    zc_blend_rect(x, y, w, 31, ZC_RGB565(9, 13, 8), (uint8_t)(a * 230.0f));
    zc_outline(x, y, w, 31, 1, ZC_RGB565(163, 177, 93));
    zc_cn_text(S.toast_text, 195, y + 4, 12, ZC_ACID, ZC_ALIGN_CENTER, false);
    zc_cn_text(S.toast_sub, 195, y + 19, 8, ZC_BONE_D, ZC_ALIGN_CENTER, false);
}

static void draw_hint(void)
{
    if(S.mode != ZC_MODE_PLAYING || S.hint_timer <= 0.0f || S.toast_active) return;
    float a = clampf(S.hint_timer / 0.65f, 0.0f, 1.0f);
    int w = 256;
    int x = 195 - w / 2;
    int y = 330;
    zc_blend_rect(x, y, w, 27, ZC_RGB565(7, 11, 7), (uint8_t)(a * 0.96f * 255.0f));
    zc_outline(x, y, w, 27, 1, ZC_RGB565(135, 149, 78));
    zc_rect(x + 12, y + 10, 9, 1, ZC_ACID_D);
    zc_rect(x + 16, y + 6, 1, 9, ZC_ACID_D);
    zc_blend_rect(x + 14, y + 8, 5, 5, ZC_ACID, 56);
    zc_cn_text("按住战场瞄准 · 松手自动开火", 195, y + 7, 11, ZC_BONE_D, ZC_ALIGN_CENTER, false);
    uint16_t blink = sinf(S.t * 4.0f) > 0.0f ? ZC_ACID : ZC_ACID_DEEP;
    zc_rect(x + 230, y + 13, 3, 3, blink);
}

static const char * const upgrade_icons[UPG_COUNT][12] = {
    {"............", "......XX....", ".....XXX....", "....XXXX....", "...XXXXXX...", "..XXX.XXX...",
     ".....XXX....", "....XXXX....", "...XXX......", "..XXX.......", ".XXX........", "............"},
    {".....XX.....", "..X..XX..X..", "...X.XX.X...", "....XXXX....", ".XXXXXXXXXX.", "XXXXXXXXXXXX",
     ".XXXXXXXXXX.", "....XXXX....", "...X.XX.X...", "..X..XX..X..", ".....XX.....", "............"},
    {"...X....X...", "..XXX..XXX..", ".XXXX..XXXX.", "..XXX..XXX..", "...X....X...", "...X....X...",
     "..XXX..XXX..", "...X....X...", "...X....X...", "............", "............", "............"},
    {".....X......", ".....X......", "..X..X..X...", "...X.X.X....", "....XXX.....", ".XXXXXXXXX..",
     "....XXX.....", "...X.X.X....", "..X..X..X...", ".....X......", ".....X......", "............"},
    {".....X......", "....XXX.....", "...XXXX.....", "..XXXXXX....", "..XX.XXX....", ".XXX.XXXX...",
     ".XX...XXX...", ".XX...XXX...", "..XX.XXXX...", "...XXXXX....", "....XXX.....", "............"},
    {"....XXXX....", "...X....X...", "..X......X..", "..XXXXXXXX..", ".....XX.....", ".....XX.....",
     "..XXXXXXXX..", "..X.XXXX.X..", "...X....X...", "............", "............", "............"},
    {"....XXXX....", "..XX....XX..", ".X........X.", ".X...XX...X.", "X...XXXX...X", "X..XXXXXX..X",
     "X...XXXX...X", ".X...XX...X.", ".X........X.", "..XX....XX..", "....XXXX....", "............"},
    {"..XXXXXXXX..", "..X......X..", "..X..XX..X..", "..X.XXXX.X..", "..X..XX..X..", "..X......X..",
     "...X....X...", "...X....X...", "....X..X....", ".....XX.....", "............", "............"},
    {"....XXXX....", "....XXXX....", "....XXXX....", ".XXXXXXXXXX.", ".XXXXXXXXXX.", ".XXXXXXXXXX.",
     "....XXXX....", "....XXXX....", "....XXXX....", "............", "............", "............"}
};

static void draw_upgrade_icon(int key, int cx, int cy, uint16_t color)
{
    const char * const * pat = upgrade_icons[key];
    int s = 3;
    int ox = cx - 18;
    int oy = cy - 18;
    for(int y = 0; y < 12; y++) {
        for(int x = 0; x < 12; x++) {
            if(pat[y][x] != 'X') continue;
            zc_rect(ox + x * s + 2, oy + y * s + 2, s, s, ZC_RGB565(4, 7, 4));
        }
    }
    for(int y = 0; y < 12; y++) {
        for(int x = 0; x < 12; x++) {
            if(pat[y][x] == 'X') zc_rect(ox + x * s, oy + y * s, s, s, color);
        }
    }
    for(int y = 0; y < 5; y++) {
        for(int x = 0; x < 5; x++) {
            if(pat[y][x] == 'X') {
                zc_blend_rect(ox + x * s, oy + y * s, s, s, ZC_WHITE, 140);
                break;
            }
        }
    }
}

static const int card_y[3] = {100, 200, 300};
static const int card_x = 22;
static const int card_w = 346;
static const int card_h = 92;

static void draw_upgrade_overlay(void)
{
    zc_blend_rect(0, 0, S.width, S.height, ZC_RGB565(4, 7, 4), 199);
    for(int y = 0; y < S.height; y += 5) zc_blend_rect(0, y, S.width, 1, ZC_BLACK, 20);
    for(int i = 0; i < 9; i++) {
        int x = 30 + i * 45 + (int)lroundf(sinf(S.t * 0.2f + (float)i) * 4.0f);
        zc_blend_rect(x, 0, 1 + (i % 3), S.height, ZC_ACID, 9);
    }
    zc_text("FIELD MODIFICATION", 195, 31, 1, ZC_BONE_DD, ZC_ALIGN_CENTER, 2);
    zc_cn_text("选择一项改装", 195, 45, 20, ZC_BONE, ZC_ALIGN_CENTER, true);
    zc_cn_text("战斗暂停 · 点击卡片装配", 195, 74, 10, ZC_BONE_DD, ZC_ALIGN_CENTER, false);
    char lv[16];
    snprintf(lv, sizeof(lv), "LV %02d", S.level);
    zc_text(lv, 370, 31, 1, ZC_ACID, ZC_ALIGN_RIGHT, 1);
    if(!S.ai_mode && S.ai_timer > 2.0f) {
        char ai[16];
        snprintf(ai, sizeof(ai), "AI %d", (int)ceilf(6.0f - S.ai_timer));
        zc_text(ai, 370, 45, 1, ZC_ACID, ZC_ALIGN_RIGHT, 1);
    }
    zc_blend_rect(22, 89, 346, 1, ZC_RGB565(157, 170, 92), 64);
    zc_blend_rect(22, 405, 346, 1, ZC_RGB565(157, 170, 92), 64);

    for(int i = 0; i < S.upgrade_choice_count; i++) {
        int key = S.upgrade_choices[i];
        const upgrade_def_t * def = &upgrade_defs[key];
        float anim = clampf((S.upgrade_overlay_t - (float)i * 0.07f) / 0.42f, 0.0f, 1.0f);
        if(anim <= 0.02f) continue;
        int x = card_x;
        int y = card_y[i] + (int)lroundf((1.0f - ease_out_cubic(anim)) * 20.0f);
        int w = card_w;
        int h = card_h;
        zc_blend_rect(x + 3, y + 4, w, h, ZC_BLACK, 115);
        zc_chamfer_panel(x, y, w, h, ZC_RGB565(20, 27, 15), ZC_RGB565(109, 121, 68), 6, ZC_RGB565(13, 18, 11));
        zc_rect(x + 2, y + 10, 3, h - 20, def->accent);
        zc_rect(x + 12, y + 18, 54, 54, ZC_RGB565(8, 12, 7));
        zc_outline(x + 12, y + 18, 54, 54, 1, def->accent);
        for(int k = 0; k < 4; k++) {
            zc_blend_rect(x + 16 + k * 10, y + 22, 5, 1, ZC_RGB565(170, 181, 110), 26);
            zc_blend_rect(x + 16 + k * 10, y + 68, 5, 1, ZC_RGB565(170, 181, 110), 26);
        }
        draw_upgrade_icon(key, x + 39, y + 45, def->accent);
        zc_cn_text(def->name, x + 80, y + 13, 15, ZC_BONE, ZC_ALIGN_LEFT, true);
        char desc[96];
        upgrade_desc(key, desc, sizeof(desc));
        zc_cn_text(desc, x + 80, y + 38, 11, ZC_BONE_D, ZC_ALIGN_LEFT, false);
        zc_blend_rect(x + 80, y + 57, 154, 1, ZC_RGB565(160, 169, 103), 31);
        if(key == UPG_REPAIR) {
            zc_cn_text("紧急抢修 · 立即生效", x + 80, y + 65, 9, ZC_ACID_D, ZC_ALIGN_LEFT, false);
        }
        else if(def->max > 4) {
            char stock[24];
            if(S.upg[key] > 0) snprintf(stock, sizeof(stock), "已装 %d", S.upg[key]);
            else snprintf(stock, sizeof(stock), "NEW");
            zc_cn_text(stock, x + w - 17, y + 15, 9, def->accent, ZC_ALIGN_RIGHT, false);
        }
        else {
            int max = def->max < 4 ? def->max : 4;
            for(int p = 0; p < max; p++) {
                int px = x + w - 18 - (max - p) * 8;
                zc_rect(px, y + 17, 5, 5, p < S.upg[key] ? def->accent : ZC_RGB565(37, 46, 27));
                if(p >= S.upg[key]) zc_outline(px, y + 17, 5, 5, 1, ZC_RGB565(74, 85, 48));
            }
        }
        zc_text("TAP", x + w - 14, y + h - 17, 1, ZC_BONE_DD, ZC_ALIGN_RIGHT, 1);
    }
    zc_cn_text("点击卡片装配 · 战斗继续", 195, 414, 10, ZC_BONE_DD, ZC_ALIGN_CENTER, false);
}

static void draw_action_button(int x, int y, int w, int h, const char * label,
                               const char * sub, bool primary, uint16_t accent)
{
    zc_blend_rect(x + 2, y + 4, w, h, ZC_BLACK, 128);
    zc_chamfer_panel(x, y, w, h, primary ? ZC_RGB565(26, 35, 18) : ZC_RGB565(18, 24, 14),
                     primary ? accent : ZC_RGB565(89, 102, 59), 5,
                     primary ? ZC_RGB565(16, 22, 13) : ZC_RGB565(11, 15, 10));
    if(primary) {
        for(int i = 0; i < 4; i++) {
            zc_rect(x + 8 + i * 5, y + 6, 3, 2, ZC_ACID_DEEP);
            zc_rect(x + w - 11 - i * 5, y + 6, 3, 2, ZC_ACID_DEEP);
        }
        zc_cn_text(label, x + w / 2, y + 8, 17, ZC_BONE, ZC_ALIGN_CENTER, true);
        if(sub != NULL && sub[0] != '\0') zc_text(sub, x + w / 2, y + 34, 1, accent, ZC_ALIGN_CENTER, 2);
    }
    else {
        zc_cn_text(label, x + w / 2, y + 8, 12, ZC_BONE_D, ZC_ALIGN_CENTER, false);
    }
}

static void format_time_text(float seconds, char * out, size_t n)
{
    int sec = (int)fmaxf(0.0f, floorf(seconds));
    snprintf(out, n, "%02d:%02d", sec / 60, sec % 60);
}

static void draw_end_overlay(void)
{
    float fade = clampf(S.end_overlay_t * 4.0f, 0.0f, 1.0f);
    if(fade <= 0.02f) return;
    uint16_t accent = ZC_RED;
    zc_blend_rect(0, 0, S.width, S.height, ZC_RGB565(3, 6, 3), (uint8_t)(0.8f * 255.0f));
    for(int y = 0; y < S.height; y += 4) zc_blend_rect(0, y, S.width, 1, ZC_RGB565(155, 47, 34), 9);
    int px = 26;
    int py = 60;
    int pw = 338;
    int ph = 372;
    zc_blend_rect(px + 3, py + 5, pw, ph, ZC_BLACK, 153);
    zc_chamfer_panel(px, py, pw, ph, ZC_RGB565(16, 22, 14), accent, 8, ZC_RGB565(11, 16, 10));
    for(int i = 0; i < 16; i++) {
        zc_rect(px + 22 + i * 18, py + 3, 8, 2, i % 2 ? accent : ZC_OLIVE_D);
    }
    zc_text("AFTER ACTION REPORT", 195, 76, 1, ZC_BONE_DD, ZC_ALIGN_CENTER, 2);
    zc_text("OVERRUN", 195 + 3, 94, 5, ZC_INK, ZC_ALIGN_CENTER, 2);
    zc_text("OVERRUN", 195, 91, 5, accent, ZC_ALIGN_CENTER, 2);
    zc_cn_text("防线失守", 195, 132, 17, ZC_BONE, ZC_ALIGN_CENTER, true);
    zc_blend_rect(56, 158, 278, 1, ZC_RGB565(170, 179, 112), 71);
    zc_rect(195, 156, 10, 5, ZC_OLIVE);

    char value[24];
    zc_cn_text("坚守波次", 54, 172, 11, ZC_BONE_DD, ZC_ALIGN_LEFT, false);
    pad2(S.wave_index > 0 ? S.wave_index : 1, value);
    zc_text(value, 332, 170, 2, ZC_BONE_D, ZC_ALIGN_RIGHT, 2);
    zc_cn_text("感染者击杀", 54, 195, 11, ZC_BONE_DD, ZC_ALIGN_LEFT, false);
    snprintf(value, sizeof(value), "%d", S.kills);
    zc_text(value, 332, 193, 2, ZC_BONE_D, ZC_ALIGN_RIGHT, 2);
    zc_cn_text("作战用时", 54, 218, 11, ZC_BONE_DD, ZC_ALIGN_LEFT, false);
    format_time_text(S.run_time, value, sizeof(value));
    zc_text(value, 332, 216, 2, ZC_BONE_D, ZC_ALIGN_RIGHT, 2);
    zc_blend_rect(56, 238, 278, 1, ZC_RGB565(170, 179, 112), 51);

    zc_cn_text("最 终 得 分", 195, 249, 9, ZC_BONE_DD, ZC_ALIGN_CENTER, false);
    pad5(S.score, value);
    zc_text(value, 195, 260, 4, ZC_BONE, ZC_ALIGN_CENTER, 4);
    if(S.new_best) zc_text("NEW RECORD", 195, 289, 1, ZC_GOLD, ZC_ALIGN_CENTER, 2);
    char best[64];
    char bw[16];
    char bs[16];
    pad2(S.best_wave, bw);
    pad5(S.best_score, bs);
    snprintf(best, sizeof(best), "BEST WAVE %s  /  SCORE %s", bw, bs);
    zc_text(best, 195, S.new_best ? 301 : 294, 1, ZC_BONE_DD, ZC_ALIGN_CENTER, 1);

    draw_action_button(74, 324, 242, 48, "再 守 一 夜", "REDEPLOY", true, accent);
    draw_action_button(132, 382, 126, 30, "返回哨站", NULL, false, accent);
    zc_text("OUTPOST LOST", 195, 420, 1, ZC_BONE_DD, ZC_ALIGN_CENTER, 2);
    if(!S.ai_mode && S.ai_timer > 4.0f) {
        char ai[16];
        snprintf(ai, sizeof(ai), "AI IN %d", (int)ceilf(12.0f - S.ai_timer));
        zc_text(ai, 195, 438, 1, ZC_ACID_D, ZC_ALIGN_CENTER, 1);
    }
}

static void draw_pause_overlay(void)
{
    zc_blend_rect(0, 0, S.width, S.height, ZC_RGB565(4, 7, 4), 179);
    if(S.embedded) {
        zc_chamfer_panel(68, 166, 254, 146, ZC_RGB565(18, 24, 15), ZC_RGB565(102, 115, 63), 6, ZC_RGB565(13, 18, 11));
        zc_cn_text("已 暂 停", 195, 180, 19, ZC_BONE, ZC_ALIGN_CENTER, true);
        zc_cn_text("战斗暂停", 195, 212, 11, ZC_BONE_D, ZC_ALIGN_CENTER, false);
        zc_chamfer_panel(92, 236, 206, 28, ZC_RGB565(32, 43, 22), ZC_ACID_D, 4, ZC_RGB565(19, 26, 14));
        zc_cn_text("继续战斗", 195, 242, 12, ZC_BONE, ZC_ALIGN_CENTER, false);
        zc_chamfer_panel(92, 272, 206, 28, ZC_RGB565(22, 20, 14), ZC_RGB565(115, 81, 60), 4, ZC_RGB565(14, 13, 10));
        zc_cn_text("返回哨站", 195, 278, 12, ZC_BONE_D, ZC_ALIGN_CENTER, false);
    }
    else {
        zc_chamfer_panel(68, 174, 254, 116, ZC_RGB565(18, 24, 15), ZC_RGB565(102, 115, 63), 6, ZC_RGB565(13, 18, 11));
        zc_cn_text("已 暂 停", 195, 190, 19, ZC_BONE, ZC_ALIGN_CENTER, true);
        zc_cn_text("点击任意处返回战场", 195, 222, 11, ZC_BONE_D, ZC_ALIGN_CENTER, false);
        float a = 0.45f + 0.3f * sinf(S.t * 3.0f);
        zc_blend_rect(167, 248, 5, 14, ZC_ACID, (uint8_t)(a * 255.0f));
        zc_blend_rect(218, 248, 5, 14, ZC_ACID, (uint8_t)(a * 255.0f));
    }
}

static void draw_field_controls(void)
{
    if(S.mode == ZC_MODE_TITLE || S.mode == ZC_MODE_GAMEOVER) return;
    int pause_x = S.safe ? 52 : 10;
    int mute_x = S.width - (S.safe ? 80 : 38);
    int y = 429 + S.dy;
    zc_blend_rect(pause_x, y, 28, 27, ZC_RGB565(10, 14, 8), 219);
    zc_outline(pause_x, y, 28, 27, 1, ZC_RGB565(137, 150, 82));
    zc_rect(pause_x + 9, y + 7, 3, 11, ZC_BONE_D);
    zc_rect(pause_x + 16, y + 7, 3, 11, ZC_BONE_D);
    zc_blend_rect(mute_x, y, 28, 27, ZC_RGB565(10, 14, 8), 219);
    zc_outline(mute_x, y, 28, 27, 1, ZC_RGB565(137, 150, 82));
    draw_speaker_button(mute_x + 14, y + 13, S.sound_on != 0);
}

static void draw_screen_effects(void)
{
    if(S.flash_white > 0.0f) {
        zc_blend_rect(0, 0, S.width, S.height, ZC_RGB565(242, 235, 204),
                      (uint8_t)(clampf(S.flash_white * 0.55f, 0.0f, 0.6f) * 255.0f));
    }
    if(S.flash_red > 0.0f) {
        zc_blend_rect(0, 0, S.width, S.height, ZC_RGB565(185, 43, 29),
                      (uint8_t)(clampf(S.flash_red * 0.42f, 0.0f, 0.5f) * 255.0f));
    }
    if(S.mode == ZC_MODE_PLAYING && S.base_hp <= 2) {
        float a = 0.04f + 0.035f * (0.5f + 0.5f * sinf(S.t * 6.0f));
        uint8_t alpha = (uint8_t)(a * 255.0f);
        zc_blend_rect(0, ZC_HUD_H, 13, S.height - ZC_HUD_H, ZC_RGB565(150, 34, 24), alpha);
        zc_blend_rect(S.width - 13, ZC_HUD_H, 13, S.height - ZC_HUD_H, ZC_RGB565(150, 34, 24), alpha);
        zc_blend_rect(0, S.height - 12, S.width, 12, ZC_RGB565(150, 34, 24), alpha);
    }
    if(S.boss != NULL && !S.boss->dead && S.mode == ZC_MODE_PLAYING) {
        float a = 0.025f + 0.022f * sinf(S.t * 5.0f);
        uint8_t alpha = (uint8_t)(a * 255.0f);
        zc_blend_rect(0, ZC_HUD_H, S.width, 9, ZC_RGB565(180, 42, 30), alpha);
        zc_blend_rect(0, S.height - 12, S.width, 12, ZC_RGB565(180, 42, 30), alpha);
    }
}


typedef struct {
    int type;
    float x;
    float y;
    float phase;
    float speed;
} title_ambient_t;

static const title_ambient_t title_ambient[3] = {
    {E_WALKER, 86.0f, 136.0f, 0.4f, 2.2f},
    {E_RUNNER, 296.0f, 126.0f, 2.1f, 1.7f},
    {E_WALKER, 330.0f, 111.0f, 4.3f, 1.2f}
};

static void draw_title(void)
{
    zc_blend_rect(0, 82, S.width, 158, ZC_RGB565(4, 8, 5), 84);
    for(int y = 82; y < 240; y += 4) {
        float a = 0.04f + (float)(y - 82) / 158.0f * 0.1f;
        zc_blend_rect(0, y, S.width, 2, ZC_RGB565(4, 8, 5), (uint8_t)(a * 255.0f));
    }
    zc_rect(14, 16, 5, 5, ZC_RED);
    zc_text("OUTPOST 07", 24, 15, 1, ZC_BONE_D, ZC_ALIGN_LEFT, 1);
    zc_text("NIGHT WATCH  /  03:17", 24, 27, 1, ZC_BONE_DD, ZC_ALIGN_LEFT, 1);
    if(sinf(S.t * 2.6f) > 0.0f) zc_rect(154, 28, 2, 5, ZC_ACID_D);
    char best[40];
    char bw[16];
    if(S.best_wave > 0) pad2(S.best_wave, bw);
    else snprintf(bw, sizeof(bw), "--");
    snprintf(best, sizeof(best), "BEST WAVE %s", bw);
    zc_text(best, S.width - 16, 15, 1, ZC_BONE_D, ZC_ALIGN_RIGHT, 1);
    char sb[24];
    char ss[16];
    pad5(S.best_score, ss);
    snprintf(sb, sizeof(sb), "SCORE %s", ss);
    zc_text(sb, S.width - 16, 27, 1, ZC_BONE_DD, ZC_ALIGN_RIGHT, 1);

    for(int i = 0; i < 3; i++) {
        const title_ambient_t * z = &title_ambient[i];
        const zc_sprite_def_t * def = sprite_for(z->type);
        int frame = ((int)(S.t * (z->type == E_RUNNER ? 5.0f : 3.0f) + z->phase)) & 1;
        float sway = sinf(S.t * z->speed + z->phase) * 2.0f;
        int bob = (int)lroundf(sinf(S.t * 3.0f + z->phase));
        int fw = def->w * def->scale;
        int fh = def->h * def->scale;
        int x = (int)lroundf(z->x + sway - (float)fw * 0.5f);
        int y = (int)lroundf(z->y + (float)bob - (float)fh);
        uint8_t alpha = z->y > 120.0f ? 173 : 115;
        zc_art_sprite_draw(z->type, frame, x, y, 2, alpha);
    }

    zc_text("GRAVEYARD", 195 + 3, 97, 5, ZC_INK, ZC_ALIGN_CENTER, 5);
    zc_text("GRAVEYARD", 195, 94, 5, ZC_BONE, ZC_ALIGN_CENTER, 5);
    zc_text("SHIFT", 195 + 4, 134, 9, ZC_INK, ZC_ALIGN_CENTER, 5);
    zc_text("SHIFT", 195, 130, 9, ZC_ACID, ZC_ALIGN_CENTER, 5);
    zc_blend_rect(55, 186, 280, 2, ZC_RGB565(111, 35, 28), 184);
    zc_rect(62, 192, 8, 2, ZC_RED_D);
    zc_rect(75, 192, 3, 2, ZC_RED_D);
    zc_rect(68, 93, 9, 2, ZC_OLIVE_L);
    zc_rect(74, 95, 2, 5, ZC_OLIVE_L);
    zc_rect(310, 166, 6, 6, ZC_RED_D);
    zc_rect(316, 169, 2, 2, ZC_RED);
    zc_cn_text("第 七 哨 站 · 尸 潮 无 尽", 195, 204, 14, ZC_BONE_D, ZC_ALIGN_CENTER, true);
    zc_text("ENDLESS SIEGE  /  NO DAWN", 195, 227, 1, ZC_BONE_DD, ZC_ALIGN_CENTER, 1);
    zc_blend_rect(115, 241, 160, 1, ZC_RGB565(171, 177, 113), 64);
    zc_rect(190, 239, 10, 5, ZC_OLIVE);

    int px = 70;
    int py = 258;
    int pw = 250;
    int ph = 58;
    float pulse = 0.55f + 0.45f * sinf(S.t * 3.2f);
    zc_rect(px - 3, py + ph - 1, pw + 6, 3, ZC_RGB565(5, 8, 5));
    zc_blend_rect(px - 1, py - 1, pw + 2, ph + 2, ZC_ACID, (uint8_t)((0.18f + pulse * 0.2f) * 255.0f));
    zc_chamfer_panel(px, py, pw, ph, ZC_RGB565(32, 40, 24), ZC_RGB565(185, 195, 103), 7, ZC_RGB565(19, 25, 14));
    for(int i = 0; i < 4; i++) {
        zc_rect(px + 5 + i * 5, py + 7, 3, 2, ZC_ACID_DEEP);
        zc_rect(px + pw - 8 - i * 5, py + 7, 3, 2, ZC_ACID_DEEP);
    }
    zc_cn_text("开 始 守 夜", 195, py + 12, 19, ZC_BONE, ZC_ALIGN_CENTER, true);
    zc_text("TAP TO DEPLOY", 195, py + 40, 1, ZC_ACID, ZC_ALIGN_CENTER, 1);
    zc_rect(px + 18, py + 28, 9, 2, ZC_ACID_D);
    zc_rect(px + 21, py + 25, 2, 8, ZC_ACID_D);
    zc_rect(px + pw - 27, py + 28, 9, 2, ZC_ACID_D);
    zc_rect(px + pw - 24, py + 25, 2, 8, ZC_ACID_D);

    zc_cn_text("按住战场瞄准 · 松手自动开火", 195, 330, 12, ZC_BONE_D, ZC_ALIGN_CENTER, true);
    zc_text("TOUCH TO AIM   /   RELEASE TO AUTO-FIRE", 195, 350, 1, ZC_BONE_DD, ZC_ALIGN_CENTER, 1);
    if(!S.ai_mode && S.ai_timer > 4.0f && S.ai_timer < 12.0f) {
        char ai[16];
        snprintf(ai, sizeof(ai), "AI IN %d", (int)ceilf(12.0f - S.ai_timer));
        zc_text(ai, 195, 370, 1, ZC_ACID_D, ZC_ALIGN_CENTER, 1);
    }
    draw_speaker_button(S.width - 30, 432 + S.dy, S.sound_on != 0);

    if(S.embedded) {
        zc_blend_rect(22, 50, 36, 30, ZC_RGB565(10, 14, 8), 210);
        zc_outline(22, 50, 36, 30, 1, ZC_RGB565(137, 150, 82));
        draw_back_chevron(31, 60);
        zc_text("BACK", 64, 61, 1, ZC_BONE_DD, ZC_ALIGN_LEFT, 1);
    }
}


static void draw_game_world(void)
{
    zc.ox = S.shake_x;
    zc.oy = S.shake_y;
    zc_art_backdrop_draw();
    if(!S.safe) zc_art_fog_draw(S.t);
    draw_decals();
    draw_fires();

    enemy_t * order[ZC_MAX_ENEMIES];
    int n = 0;
    for(int i = 0; i < ZC_MAX_ENEMIES; i++) {
        if(S.enemies[i].active && !S.enemies[i].dead) order[n++] = &S.enemies[i];
    }
    for(int i = 1; i < n; i++) {
        enemy_t * key = order[i];
        int j = i - 1;
        while(j >= 0 && order[j]->y > key->y) {
            order[j + 1] = order[j];
            j--;
        }
        order[j + 1] = key;
    }
    for(int i = 0; i < n; i++) draw_enemy(order[i]);

    zc_art_base_draw(S.t, S.aim_angle, S.recoil, S.base_hp, S.upg[UPG_TWIN] > 0);
    draw_sentries();
    draw_shells();
    draw_blasts();
    draw_particles();
    draw_tracers();
    draw_floaters();
    draw_muzzle_flash();
    zc_art_motes_draw(S.t);
    draw_reticle();
    zc.ox = 0;
    zc.oy = 0;
}

static void draw_scanlines(void)
{
    for(int y = 0; y < S.height; y += 4) zc_blend_rect(0, y, S.width, 1, ZC_BLACK, 14);
}

void zc_render(void)
{
    if(!g_created) return;
    if(S.mode == ZC_MODE_TITLE) {
        zc.ox = 0;
        zc.oy = 0;
        zc_art_backdrop_draw();
        if(!S.safe) zc_art_fog_draw(S.t);
        zc_art_base_draw(S.t, S.aim_angle, S.recoil, S.base_hp, S.upg[UPG_TWIN] > 0);
        zc_art_motes_draw(S.t);
        draw_title();
        if(S.scanlines && !S.safe) draw_scanlines();
        return;
    }

    draw_game_world();
    draw_screen_effects();
    draw_hud();
    draw_field_controls();
    draw_boss_bar();
    if(S.mode == ZC_MODE_PLAYING) {
        draw_hint();
        draw_toast();
        draw_banner();
    }
    else if(S.mode == ZC_MODE_ENDING) {
        draw_banner();
        float a = clampf(S.ending_t * 2.4f, 0.0f, 0.35f);
        zc_blend_rect(0, 0, S.width, S.height, ZC_RGB565(72, 16, 12), (uint8_t)(a * 255.0f));
    }
    else if(S.mode == ZC_MODE_UPGRADE) {
        draw_upgrade_overlay();
    }
    else if(S.mode == ZC_MODE_PAUSED) {
        draw_pause_overlay();
    }
    else if(S.mode == ZC_MODE_GAMEOVER) {
        draw_end_overlay();
    }
    if(S.scanlines && !S.safe) draw_scanlines();
}


static void reset_run(void)
{
    memset(S.enemies, 0, sizeof(S.enemies));
    memset(S.shells, 0, sizeof(S.shells));
    memset(S.particles, 0, sizeof(S.particles));
    memset(S.blasts, 0, sizeof(S.blasts));
    memset(S.fires, 0, sizeof(S.fires));
    memset(S.decals, 0, sizeof(S.decals));
    memset(S.tracers, 0, sizeof(S.tracers));
    memset(S.floaters, 0, sizeof(S.floaters));
    memset(S.sentries, 0, sizeof(S.sentries));
    S.particle_head = 0;
    S.blast_head = 0;
    S.decal_head = 0;
    S.tracer_head = 0;
    S.floater_head = 0;
    S.boss = NULL;
    for(int i = 0; i < UPG_COUNT; i++) S.upg[i] = 0;
    S.level = 1;
    S.xp = 0;
    S.xp_need = 6;
    S.display_xp = 0.0f;
    S.pending_upgrades = 0;
    S.upgrade_delay = 0.0f;
    S.upgrade_overlay_t = 0.0f;
    S.upgrade_choice_count = 0;
    S.base_hp = 6;
    S.base_max_hp = 6;
    S.base_flash = 0.0f;
    S.kills = 0;
    S.score = 0;
    S.shots = 0;
    S.run_time = 0.0f;
    S.new_best = false;
    S.wave_index = 0;
    S.wave_count = 0;
    S.wave_cursor = 0;
    S.wave_clock = 0.0f;
    S.wave_grace = 0.0f;
    S.wave_intermission = 0.0f;
    S.wave_clear_timer = 0.0f;
    S.wave_active = false;
    S.aim_angle = -(float)M_PI * 0.5f;
    S.target_angle = S.aim_angle;
    S.fire_timer = 0.0f;
    S.recoil = 0.0f;
    S.muzzle_flash = 0.0f;
    S.input_active = false;
    S.input_x = 195.0f;
    S.input_y = 230.0f;
    S.aim_valid = false;
    S.aim_snapped = false;
    S.hint_timer = 8.0f;
    S.banner_active = false;
    S.toast_active = false;
    S.ending_lose = true;
    S.ending_timer = 0.0f;
    S.ending_t = 0.0f;
    S.end_overlay_t = 0.0f;
    S.shake = 0.0f;
    S.shake_x = 0;
    S.shake_y = 0;
    S.flash_red = 0.0f;
    S.flash_white = 0.0f;
    S.ai_mode = false;
    S.ai_timer = 0.0f;
    S.ai_idle = 0.0f;
    rng_seed(0x5EED1234U);
}

static void go_title(void)
{
    reset_run();
    S.mode = ZC_MODE_TITLE;
    S.hint_timer = 0.0f;
}

static void start_game(void)
{
    reset_run();
    S.mode = ZC_MODE_PLAYING;
    S.run_start = S.t;
    begin_wave(1);
    sfx(ZC_SFX_CLICK);
    haptic(ZC_HAPTIC_TAP);
}

void zc_enter(void)
{
    if(!g_created) return;
    S.exit_requested = false;
    S.input_active = false;
    go_title();
}

void zc_leave(void)
{
    S.input_active = false;
    S.aim_valid = false;
}

void zc_tick(uint32_t now_ms, uint32_t elapsed_ms)
{
    (void)now_ms;
    if(!g_created) return;
    float dt = (float)elapsed_ms / 1000.0f;
    if(dt <= 0.0f) dt = 1.0f / 60.0f;
    if(dt > 0.1f) dt = 0.1f;
    S.t += dt;
    zc_art_motes_update(dt, S.t);
    if(S.mode == ZC_MODE_TITLE) {
        S.ai_timer += dt;
        if(S.ai_mode || S.ai_timer >= 12.0f) {
            start_game();
            S.ai_mode = true;
        }
    }
    else if(S.mode == ZC_MODE_PLAYING) {
        update_game(dt);
    }
    else if(S.mode == ZC_MODE_UPGRADE) {
        S.upgrade_overlay_t = fminf(1.0f, S.upgrade_overlay_t + dt * 3.8f);
        S.ai_timer += dt;
        if(S.ai_mode || S.ai_timer >= 6.0f) {
            int pick = ai_pick_upgrade();
            if(pick >= 0) {
                S.ai_mode = true;
                choose_upgrade(pick);
            }
        }
    }
    else if(S.mode == ZC_MODE_ENDING) {
        S.ending_t += dt;
        S.ending_timer -= dt;
        update_effects(dt);
        if(S.ending_timer <= 0.0f) {
            S.mode = ZC_MODE_GAMEOVER;
            S.end_overlay_t = 0.0f;
            S.ai_timer = 0.0f;
            S.input_active = false;
            S.aim_valid = false;
        }
    }
    else if(S.mode == ZC_MODE_GAMEOVER) {
        S.end_overlay_t = fminf(1.0f, S.end_overlay_t + dt * 4.4f);
        S.ai_timer += dt;
        if(S.ai_mode || S.ai_timer >= 12.0f) {
            start_game();
            S.ai_mode = true;
        }
    }
}


static bool point_in(int x, int y, int rx, int ry, int rw, int rh)
{
    return x >= rx && x <= rx + rw && y >= ry && y <= ry + rh;
}

static void set_sound(bool on)
{
    if(S.sound_on == (on ? 1 : 0)) return;
    S.sound_on = on ? 1 : 0;
    save_store();
    if(on) sfx(ZC_SFX_CLICK);
}

static void pause_toggle(void)
{
    if(S.mode == ZC_MODE_PLAYING) {
        S.input_active = false;
        S.aim_valid = false;
        S.mode = ZC_MODE_PAUSED;
        sfx(ZC_SFX_CLICK);
    }
    else if(S.mode == ZC_MODE_PAUSED) {
        S.mode = ZC_MODE_PLAYING;
        sfx(ZC_SFX_CLICK);
    }
}

static void request_exit_or_title(void)
{
    if(S.embedded) S.exit_requested = true;
    else go_title();
}

static void handle_down(int x, int y)
{
    S.ai_mode = false;
    S.ai_timer = 0.0f;
    S.ai_idle = 0.0f;
    if(S.mode == ZC_MODE_TITLE) {
        if(S.embedded && point_in(x, y, 22, 50, 36, 30)) {
            S.exit_requested = true;
            return;
        }
        if(point_in(x, y, S.width - 48, 414 + S.dy, 36, 36)) {
            set_sound(S.sound_on == 0);
            return;
        }
        if(point_in(x, y, 70, 258, 250, 58)) start_game();
        return;
    }

    if(S.mode == ZC_MODE_UPGRADE) {
        if(S.upgrade_overlay_t < 0.24f) return;
        for(int i = 0; i < S.upgrade_choice_count; i++) {
            int ry = card_y[i] + (int)lroundf((1.0f - ease_out_cubic(clampf((S.upgrade_overlay_t - (float)i * 0.07f) / 0.42f, 0.0f, 1.0f))) * 20.0f);
            if(point_in(x, y, card_x, ry, card_w, card_h)) {
                choose_upgrade(S.upgrade_choices[i]);
                return;
            }
        }
        return;
    }

    if(S.mode == ZC_MODE_GAMEOVER) {
        if(point_in(x, y, 74, 324, 242, 48)) {
            start_game();
            return;
        }
        if(point_in(x, y, 132, 382, 126, 30)) {
            request_exit_or_title();
            return;
        }
        return;
    }

    if(S.mode == ZC_MODE_PAUSED) {
        if(S.embedded) {
            if(point_in(x, y, 92, 272, 206, 28)) {
                S.exit_requested = true;
                return;
            }
            if(point_in(x, y, 92, 236, 206, 28)) {
                S.mode = ZC_MODE_PLAYING;
                sfx(ZC_SFX_CLICK);
                return;
            }
            return;
        }
        S.mode = ZC_MODE_PLAYING;
        sfx(ZC_SFX_CLICK);
        return;
    }

    if(S.mode != ZC_MODE_PLAYING) return;
    int pause_x = S.safe ? 52 : 10;
    int mute_x = S.width - (S.safe ? 80 : 38);
    int controls_y = 429 + S.dy;
    if(point_in(x, y, pause_x, controls_y, 28, 27)) {
        pause_toggle();
        return;
    }
    if(point_in(x, y, mute_x, controls_y, 28, 27)) {
        set_sound(S.sound_on == 0);
        return;
    }
    if(y < ZC_HUD_H + 1) return;
    if(y > S.height + 20) return;
    if(S.input_active) return;
    S.input_active = true;
    S.input_x = (float)x;
    S.input_y = (float)y;
    S.hint_timer = 0.0f;
    resolve_aim(S.input_x, S.input_y);
}

void zc_pointer(zc_pointer_action_t action, int x, int y)
{
    if(!g_created) return;
    if(action == ZC_POINTER_DOWN) {
        handle_down(x, y);
    }
    else if(action == ZC_POINTER_MOVE) {
        if(S.input_active && S.mode == ZC_MODE_PLAYING) {
            S.ai_mode = false;
            S.ai_idle = 0.0f;
            S.input_x = (float)x;
            S.input_y = (float)y;
            resolve_aim(S.input_x, S.input_y);
        }
    }
    else {
        S.input_active = false;
        S.aim_valid = false;
        S.ai_idle = 0.0f;
    }
}

bool zc_key(uint32_t key)
{
    if(!g_created) return false;
    S.ai_mode = false;
    S.ai_timer = 0.0f;
    S.ai_idle = 0.0f;
    if(key == 10U || key == ' ') {
        if(S.mode == ZC_MODE_TITLE) {
            start_game();
            return true;
        }
        if(S.mode == ZC_MODE_GAMEOVER) {
            start_game();
            return true;
        }
        if(S.mode == ZC_MODE_PAUSED) {
            S.mode = ZC_MODE_PLAYING;
            sfx(ZC_SFX_CLICK);
            return true;
        }
        return false;
    }
    if(key == 27U || key == 2U) {
        if(S.mode == ZC_MODE_PLAYING) {
            pause_toggle();
            return true;
        }
        if(S.mode == ZC_MODE_TITLE || S.mode == ZC_MODE_GAMEOVER) {
            request_exit_or_title();
            return true;
        }
        if(S.mode == ZC_MODE_PAUSED) {
            if(S.embedded) S.exit_requested = true;
            else go_title();
            return true;
        }
        return false;
    }
    return false;
}

bool zc_wants_exit(void)
{
    return S.exit_requested;
}

void zc_clear_exit(void)
{
    S.exit_requested = false;
}

bool zc_audio_on(void)
{
    return S.sound_on != 0;
}

void zc_set_audio_on(bool on)
{
    set_sound(on);
}

int zc_mode(void)
{
    return S.mode;
}

int zc_wave(void)
{
    return S.wave_index;
}

int zc_level(void)
{
    return S.level;
}

int32_t zc_best_wave(void)
{
    return S.best_wave;
}

int32_t zc_best_score(void)
{
    return S.best_score;
}

bool zc_create(uint16_t * fb, uint16_t * backdrop, const zc_config_t * cfg)
{
    if(fb == NULL || cfg == NULL) return false;
    int w = cfg->width;
    int h = cfg->height;
    if(w <= 0 || h <= 0) return false;
    if(w > ZC_MAX_W) w = ZC_MAX_W;
    if(h > ZC_MAX_H) h = ZC_MAX_H;
    memset(&S, 0, sizeof(S));
    g_cfg = *cfg;
    g_cfg.width = w;
    g_cfg.height = h;
    g_cfg.hooks = cfg->hooks;
    if(cfg->hooks != NULL) g_hooks = *cfg->hooks;
    else memset(&g_hooks, 0, sizeof(g_hooks));
    S.width = w;
    S.height = h;
    S.dy = h - 460;
    S.safe = cfg->safe_inset;
    S.embedded = cfg->embedded;
    S.scanlines = cfg->show_scanlines;
    S.sound_on = 1;
    S.best_score = 0;
    S.best_wave = 0;
    if(g_hooks.load != NULL) {
        zc_save_t save;
        memset(&save, 0, sizeof(save));
        if(g_hooks.load(&save, g_hooks.user)) {
            S.best_score = save.best_score;
            S.best_wave = save.best_wave;
            S.sound_on = save.sound_on ? 1 : 0;
        }
    }
    zc_gfx_bind(fb, backdrop, w, h, S.dy, S.safe);
    zc_art_fog_init();
    zc_art_motes_init();
    zc_art_backdrop_build();
    S.t = 0.0f;
    S.mode = ZC_MODE_TITLE;
    go_title();
    g_created = true;
    return true;
}

void zc_destroy(void)
{
    g_created = false;
    memset(&S, 0, sizeof(S));
    memset(&g_hooks, 0, sizeof(g_hooks));
    zc.fb = NULL;
    zc.backdrop = NULL;
}
