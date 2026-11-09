#include "sim_sifli.h"

#include <stdarg.h>
#include <stdio.h>

rt_err_t littlevgl2rtt_init(const char *name)
{
    (void)name;
    return RT_EOK;
}

float lv_get_fps(void)
{
    return 0.0f;
}

void set_display_fps_and_cpu_load(int en)
{
    (void)en;
}

int get_display_fps_and_cpu_load(void)
{
    return 0;
}

void rt_kprintf(const char *fmt, ...)
{
    va_list ap;

    va_start(ap, fmt);
    (void)vprintf(fmt, ap);
    va_end(ap);
    (void)fflush(stdout);
}

void rt_thread_mdelay(uint32_t ms)
{
    (void)ms;
}
