#ifndef LVGL_AI_SIM_SIFLI_H
#define LVGL_AI_SIM_SIFLI_H

#include <stdint.h>

typedef int rt_err_t;

enum
{
    RT_EOK = 0
};

rt_err_t littlevgl2rtt_init(const char *name);
float lv_get_fps(void);
void set_display_fps_and_cpu_load(int en);
int get_display_fps_and_cpu_load(void);
void rt_kprintf(const char *fmt, ...);
void rt_thread_mdelay(uint32_t ms);

#endif
