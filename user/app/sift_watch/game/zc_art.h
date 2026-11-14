#ifndef ZC_ART_H
#define ZC_ART_H

#include "zc_priv.h"

typedef struct {
    int w;
    int h;
    int scale;
    int frames;
    const char * const * const * rows;
    const uint16_t * pal;
} zc_sprite_def_t;

const zc_sprite_def_t * zc_art_sprite(int type);

/* mode: 0 normal, 1 hit flash, 2 title silhouette. */
void zc_art_sprite_draw(int type, int frame, int x, int y, int mode, uint8_t alpha);

void zc_art_backdrop_build(void);
/* Copies the cached backdrop with the current shake offset.  With no cache it
 * draws the procedural sky directly each frame. */
void zc_art_backdrop_draw(void);

void zc_art_fog_init(void);
void zc_art_fog_draw(float t);

void zc_art_motes_init(void);
void zc_art_motes_update(float dt, float t);
void zc_art_motes_draw(float t);

void zc_art_base_draw(float t, float aim, float recoil, int base_hp, bool twin);

#endif /* ZC_ART_H */
