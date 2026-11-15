#include "zc_synth.h"

#include <math.h>
#include <string.h>

#define ZC_SYNTH_SR    16000
#define ZC_VOICE_COUNT 16

typedef struct {
    uint8_t active;
    uint8_t wave;
    uint8_t noise_mode;
    float phase;
    float freq0;
    float freq1;
    float t;
    float dur;
    float amp;
    float env;
    float attack_step;
    float decay;
    float lp;
    uint32_t noise_state;
} zc_voice_t;

static zc_voice_t s_voices[ZC_VOICE_COUNT];
static float s_sine[256];

static void voice_spawn(uint8_t wave, float f0, float f1, float dur, float amp,
                        float delay, uint8_t noise_mode)
{
    if(amp <= 0.0f || dur <= 0.0f) return;
    zc_voice_t * v = NULL;
    for(int i = 0; i < ZC_VOICE_COUNT; i++) {
        if(!s_voices[i].active) {
            v = &s_voices[i];
            break;
        }
    }
    if(v == NULL) v = &s_voices[0];
    memset(v, 0, sizeof(*v));
    v->active = 1;
    v->wave = wave;
    v->noise_mode = noise_mode;
    v->freq0 = f0;
    v->freq1 = f1;
    v->t = -delay;
    v->dur = dur;
    v->amp = amp;
    v->env = 0.0f;
    v->attack_step = 1.0f / (0.004f * (float)ZC_SYNTH_SR);
    v->decay = expf(-5.5f / (dur * (float)ZC_SYNTH_SR));
    v->noise_state =
        0x9E3779B9U ^ (uint32_t)(f0 * 13.0f) ^ (uint32_t)(dur * 100000.0f);
}

static float voice_sample(zc_voice_t * v)
{
    v->t += 1.0f / (float)ZC_SYNTH_SR;
    if(v->t < 0.0f) return 0.0f;
    if(v->t >= v->dur) {
        v->active = 0;
        return 0.0f;
    }
    if(v->env < 1.0f) {
        v->env += v->attack_step;
        if(v->env > 1.0f) v->env = 1.0f;
    }
    else {
        v->env *= v->decay;
    }
    float t = v->t;
    float f = v->freq0 + (v->freq1 - v->freq0) * (t / v->dur);
    if(f < 0.0f) f = 0.0f;
    v->phase += f / (float)ZC_SYNTH_SR;
    while(v->phase >= 1.0f) v->phase -= 1.0f;
    float s = 0.0f;
    switch(v->wave) {
        case 0:
            s = v->phase < 0.5f ? 1.0f : -1.0f;
            break;
        case 1:
            s = 4.0f * fabsf(v->phase - 0.5f) - 1.0f;
            break;
        case 2:
            s = 2.0f * v->phase - 1.0f;
            break;
        case 3:
            s = s_sine[(int)(v->phase * 256.0f) & 255];
            break;
        default: {
            v->noise_state ^= v->noise_state << 13;
            v->noise_state ^= v->noise_state >> 17;
            v->noise_state ^= v->noise_state << 5;
            float n = (float)(v->noise_state >> 8) / 8388608.0f - 1.0f;
            v->lp += 0.12f * (n - v->lp);
            if(v->noise_mode == 1) s = v->lp * 2.2f;
            else if(v->noise_mode == 2)
                s = (n - v->lp) * 0.8f;
            else
                s = n * 0.7f;
            break;
        }
    }
    float env = v->env;
    if(t > v->dur - 0.006f) env *= (v->dur - t) / 0.006f;
    return s * v->amp * env;
}

void zc_synth_reset(void)
{
    memset(s_voices, 0, sizeof(s_voices));
    for(int i = 0; i < 256; i++)
        s_sine[i] = sinf((float)i / 256.0f * 6.2831853f);
}

void zc_synth_fill(int16_t * out, int count)
{
    for(int i = 0; i < count; i++) {
        float mix = 0.0f;
        for(int v = 0; v < ZC_VOICE_COUNT; v++) {
            if(s_voices[v].active) mix += voice_sample(&s_voices[v]);
        }
        mix *= 0.72f;
        if(mix > 1.0f) mix = 1.0f;
        else if(mix < -1.0f)
            mix = -1.0f;
        out[i] = (int16_t)(mix * 32767.0f);
    }
}

void zc_synth_play(zc_sfx_t id)
{
    switch(id) {
        case ZC_SFX_SHOOT:
            voice_spawn(0, 150.0f, 48.0f, 0.075f, 0.11f, 0.0f, 0);
            voice_spawn(4, 1.0f, 1.0f, 0.050f, 0.035f, 0.0f, 2);
            break;
        case ZC_SFX_SENTRY:
            voice_spawn(0, 620.0f, 240.0f, 0.045f, 0.05f, 0.0f, 0);
            voice_spawn(4, 1.0f, 1.0f, 0.030f, 0.018f, 0.0f, 2);
            break;
        case ZC_SFX_HIT:
            voice_spawn(4, 1.0f, 1.0f, 0.035f, 0.05f, 0.0f, 2);
            break;
        case ZC_SFX_DEATH:
            voice_spawn(4, 1.0f, 1.0f, 0.080f, 0.07f, 0.0f, 1);
            voice_spawn(1, 160.0f, 45.0f, 0.100f, 0.05f, 0.0f, 0);
            break;
        case ZC_SFX_DEATH_BIG:
            voice_spawn(4, 1.0f, 1.0f, 0.220f, 0.12f, 0.0f, 1);
            voice_spawn(1, 100.0f, 45.0f, 0.220f, 0.08f, 0.0f, 0);
            break;
        case ZC_SFX_EXPLODE:
            voice_spawn(4, 1.0f, 1.0f, 0.250f, 0.15f, 0.0f, 1);
            voice_spawn(3, 120.0f, 30.0f, 0.220f, 0.12f, 0.0f, 0);
            voice_spawn(4, 1.0f, 1.0f, 0.120f, 0.05f, 0.015f, 2);
            break;
        case ZC_SFX_EXPLODE_BIG:
            voice_spawn(4, 1.0f, 1.0f, 0.500f, 0.20f, 0.0f, 1);
            voice_spawn(3, 105.0f, 30.0f, 0.400f, 0.15f, 0.0f, 0);
            voice_spawn(4, 1.0f, 1.0f, 0.140f, 0.06f, 0.015f, 2);
            break;
        case ZC_SFX_HURT:
            voice_spawn(2, 150.0f, 42.0f, 0.360f, 0.14f, 0.0f, 0);
            voice_spawn(4, 1.0f, 1.0f, 0.300f, 0.09f, 0.0f, 1);
            break;
        case ZC_SFX_HEAL:
            voice_spawn(1, 392.0f, 392.0f, 0.120f, 0.06f, 0.000f, 0);
            voice_spawn(1, 523.0f, 523.0f, 0.120f, 0.06f, 0.075f, 0);
            voice_spawn(1, 659.0f, 659.0f, 0.120f, 0.06f, 0.150f, 0);
            break;
        case ZC_SFX_LEVEL_UP:
            voice_spawn(0, 523.0f, 523.0f, 0.160f, 0.055f, 0.00f, 0);
            voice_spawn(0, 659.0f, 659.0f, 0.160f, 0.055f, 0.07f, 0);
            voice_spawn(0, 784.0f, 784.0f, 0.160f, 0.055f, 0.14f, 0);
            voice_spawn(0, 1047.0f, 1047.0f, 0.160f, 0.055f, 0.21f, 0);
            break;
        case ZC_SFX_WAVE:
            voice_spawn(2, 130.0f, 92.0f, 0.500f, 0.08f, 0.0f, 0);
            voice_spawn(0, 196.0f, 130.0f, 0.500f, 0.05f, 0.05f, 0);
            voice_spawn(4, 1.0f, 1.0f, 0.400f, 0.04f, 0.0f, 1);
            break;
        case ZC_SFX_WAVE_BOSS:
            voice_spawn(2, 92.0f, 55.0f, 0.500f, 0.10f, 0.0f, 0);
            voice_spawn(0, 130.0f, 82.0f, 0.500f, 0.06f, 0.05f, 0);
            voice_spawn(4, 1.0f, 1.0f, 0.400f, 0.05f, 0.0f, 1);
            break;
        case ZC_SFX_CLEAR:
            voice_spawn(1, 392.0f, 392.0f, 0.160f, 0.055f, 0.00f, 0);
            voice_spawn(1, 494.0f, 494.0f, 0.160f, 0.055f, 0.08f, 0);
            voice_spawn(1, 587.0f, 587.0f, 0.160f, 0.055f, 0.16f, 0);
            voice_spawn(1, 784.0f, 784.0f, 0.160f, 0.055f, 0.24f, 0);
            break;
        case ZC_SFX_BOSS_SPAWN:
            voice_spawn(2, 65.0f, 32.0f, 0.900f, 0.15f, 0.0f, 0);
            voice_spawn(4, 1.0f, 1.0f, 0.900f, 0.13f, 0.0f, 1);
            voice_spawn(0, 98.0f, 45.0f, 0.900f, 0.05f, 0.0f, 0);
            break;
        case ZC_SFX_BOSS_DOWN:
            voice_spawn(4, 1.0f, 1.0f, 0.900f, 0.18f, 0.0f, 1);
            voice_spawn(3, 80.0f, 28.0f, 0.800f, 0.15f, 0.0f, 0);
            voice_spawn(1, 262.0f, 262.0f, 0.220f, 0.06f, 0.20f, 0);
            voice_spawn(1, 330.0f, 330.0f, 0.220f, 0.06f, 0.30f, 0);
            voice_spawn(1, 392.0f, 392.0f, 0.220f, 0.06f, 0.40f, 0);
            voice_spawn(1, 523.0f, 523.0f, 0.220f, 0.06f, 0.50f, 0);
            break;
        case ZC_SFX_LOSE:
            voice_spawn(2, 220.0f, 198.0f, 0.350f, 0.08f, 0.00f, 0);
            voice_spawn(2, 185.0f, 165.0f, 0.350f, 0.08f, 0.19f, 0);
            voice_spawn(2, 147.0f, 130.0f, 0.350f, 0.08f, 0.38f, 0);
            voice_spawn(2, 110.0f, 90.0f, 0.350f, 0.08f, 0.57f, 0);
            break;
        case ZC_SFX_CLICK:
        default:
            voice_spawn(0, 640.0f, 480.0f, 0.035f, 0.045f, 0.0f, 0);
            break;
    }
}
