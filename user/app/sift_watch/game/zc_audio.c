#include "zc_audio.h"
#include "zc_synth.h"

#if defined(LVGL_AI_EZIP_ASSETS)
#include "rtthread.h"
#endif

#if defined(LVGL_AI_EZIP_ASSETS) && defined(PA_USING_AW8155)

#include "rtdevice.h"
#include "bf0_hal.h"
#include <drivers/audio.h>
#include "sifli_aw8155.h"

#include <stdint.h>
#include <string.h>

#define ZC_AUDIO_SR 16000
#define ZC_AUDIO_SAMPLES 320
#define ZC_AUDIO_BYTES (ZC_AUDIO_SAMPLES * 2)
#define ZC_EVENT_COUNT 64

static rt_device_t s_prc;
static rt_device_t s_codec;
static rt_event_t s_event;
static rt_thread_t s_thread;
static bool s_started;
static bool s_enabled;
static bool s_muted;
static int16_t s_pcm[ZC_AUDIO_SAMPLES];
static volatile uint16_t s_evt_head;
static volatile uint16_t s_evt_tail;
static uint8_t s_evt[ZC_EVENT_COUNT];

static rt_err_t audio_tx_done(rt_device_t dev, void * buffer)
{
    (void)dev;
    (void)buffer;
    if(s_event != NULL) rt_event_send(s_event, 1);
    return RT_EOK;
}

static void audio_thread_entry(void * parameter)
{
    (void)parameter;
    rt_uint32_t evt;
    while(1) {
        rt_event_recv(s_event, 1, RT_EVENT_FLAG_OR | RT_EVENT_FLAG_CLEAR,
                      RT_WAITING_FOREVER, &evt);
        while(s_evt_tail != s_evt_head) {
            uint8_t id = s_evt[s_evt_tail];
            s_evt_tail = (uint16_t)((s_evt_tail + 1) % ZC_EVENT_COUNT);
            zc_synth_play((zc_sfx_t)id);
        }
        zc_synth_fill(s_pcm, ZC_AUDIO_SAMPLES);
        rt_device_write(s_prc, 0, s_pcm, sizeof(s_pcm));
    }
}

static bool audio_config(void)
{
    struct rt_audio_caps caps;
    struct rt_audio_sr_convert src;

    rt_device_control(s_codec, AUDIO_CTL_SETOUTPUT, (void *)(uintptr_t)AUDPRC_TX_TO_CODEC);
    rt_device_control(s_prc, AUDIO_CTL_SETOUTPUT, (void *)(uintptr_t)AUDPRC_TX_TO_CODEC);

    memset(&caps, 0, sizeof(caps));
    caps.main_type = AUDIO_TYPE_OUTPUT;
    /* The Huangshan Pi routes AU_DAC1P/N to the AW8155 speaker PA. */
    caps.sub_type = 1U << HAL_AUDCODEC_DAC_CH1;
    caps.udata.config.channels = 1;
    caps.udata.config.samplerate = ZC_AUDIO_SR;
    caps.udata.config.samplefmt = 16;
    if(rt_device_control(s_codec, AUDIO_CTL_CONFIGURE, &caps) != RT_EOK) return false;

    src.channel = 1;
    src.source_sr = ZC_AUDIO_SR;
    src.dest_sr = ZC_AUDIO_SR;
    rt_device_control(s_prc, AUDIO_CTL_OUTPUTSRC, &src);

    caps.main_type = AUDIO_TYPE_SELECTOR;
    caps.sub_type = 0xFF;
    caps.udata.value = 0x5050;
    rt_device_control(s_prc, AUDIO_CTL_CONFIGURE, &caps);
    caps.main_type = AUDIO_TYPE_MIXER;
    caps.sub_type = 0xFF;
    caps.udata.value = 0x5050;
    rt_device_control(s_prc, AUDIO_CTL_CONFIGURE, &caps);

    memset(&caps, 0, sizeof(caps));
    caps.main_type = AUDIO_TYPE_OUTPUT;
    caps.sub_type = HAL_AUDPRC_TX_CH0;
    caps.udata.config.channels = 1;
    caps.udata.config.samplerate = ZC_AUDIO_SR;
    caps.udata.config.samplefmt = 16;
    if(rt_device_control(s_prc, AUDIO_CTL_CONFIGURE, &caps) != RT_EOK) return false;

    rt_device_control(s_codec, AUDIO_CTL_SETVOLUME, (void *)(intptr_t)0);
    rt_device_control(s_codec, AUDIO_CTL_MUTE, (void *)(intptr_t)1);
    return true;
}

static bool audio_open(void)
{
    s_prc = rt_device_find("audprc");
    s_codec = rt_device_find("audcodec");
    if(s_prc == NULL || s_codec == NULL) {
        rt_kprintf("[zc_audio] audprc/audcodec not found\n");
        return false;
    }
    if(rt_device_open(s_prc, RT_DEVICE_FLAG_RDWR) != RT_EOK) {
        rt_kprintf("[zc_audio] open audprc failed\n");
        return false;
    }
    if(rt_device_open(s_codec, RT_DEVICE_FLAG_WRONLY) != RT_EOK) {
        rt_kprintf("[zc_audio] open audcodec failed\n");
        rt_device_close(s_prc);
        s_prc = NULL;
        return false;
    }
    return true;
}

bool zc_audio_start(void)
{
    if(s_started) {
        zc_audio_set_enabled(true);
        return true;
    }
    if(!audio_open()) return false;
    s_event = rt_event_create("zc_audio", RT_IPC_FLAG_FIFO);
    if(s_event == NULL) {
        rt_device_close(s_codec);
        rt_device_close(s_prc);
        s_codec = NULL;
        s_prc = NULL;
        return false;
    }
    rt_device_set_tx_complete(s_prc, audio_tx_done);
    rt_device_control(s_prc, AUDIO_CTL_SET_TX_DMA_SIZE, (void *)(uintptr_t)ZC_AUDIO_BYTES);
    if(!audio_config()) {
        rt_kprintf("[zc_audio] audio config failed\n");
        return false;
    }
    zc_synth_reset();
    s_thread = rt_thread_create("zc_audio", audio_thread_entry, NULL, 4096,
                                RT_THREAD_PRIORITY_HIGH, 10);
    if(s_thread == NULL) {
        rt_kprintf("[zc_audio] thread create failed\n");
        return false;
    }
    rt_thread_startup(s_thread);

    int stream = AUDIO_STREAM_REPLAY | ((1 << HAL_AUDCODEC_DAC_CH1) << 8);
    rt_device_control(s_codec, AUDIO_CTL_START, &stream);
    stream = AUDIO_STREAM_REPLAY | ((1 << HAL_AUDPRC_TX_CH0) << 8);
    rt_device_control(s_prc, AUDIO_CTL_START, &stream);

    sifli_aw8155_start();
    rt_thread_mdelay(30);
    s_started = true;
    s_enabled = true;
    s_muted = false;
    rt_device_control(s_codec, AUDIO_CTL_MUTE, (void *)(intptr_t)0);
    rt_kprintf("[zc_audio] speaker ready audprc+audcodec+AW8155\n");
    return true;
}

void zc_audio_set_enabled(bool on)
{
    if(!s_started) return;
    if(on == s_enabled) return;
    if(on) {
        sifli_aw8155_start();
        rt_thread_mdelay(30);
        s_enabled = true;
        rt_device_control(s_codec, AUDIO_CTL_MUTE,
                          (void *)(intptr_t)(s_muted ? 1 : 0));
    }
    else {
        s_enabled = false;
        rt_device_control(s_codec, AUDIO_CTL_MUTE, (void *)(intptr_t)1);
        sifli_aw8155_stop();
    }
}

void zc_audio_set_muted(bool muted)
{
    if(s_muted == muted) return;
    s_muted = muted;
    if(s_started) {
        rt_device_control(s_codec, AUDIO_CTL_MUTE,
                          (void *)(intptr_t)((muted || !s_enabled) ? 1 : 0));
    }
}

bool zc_audio_is_started(void)
{
    return s_started;
}

void zc_audio_play(zc_sfx_t id)
{
    if(!s_started || !s_enabled || s_muted) return;
    uint16_t next = (uint16_t)((s_evt_head + 1) % ZC_EVENT_COUNT);
    if(next == s_evt_tail) return;
    s_evt[s_evt_head] = (uint8_t)id;
    s_evt_head = next;
}

#else

bool zc_audio_start(void)
{
    return false;
}

void zc_audio_set_enabled(bool on)
{
    (void)on;
}

void zc_audio_set_muted(bool muted)
{
    (void)muted;
}

bool zc_audio_is_started(void)
{
    return false;
}

void zc_audio_play(zc_sfx_t id)
{
    (void)id;
}

#endif
