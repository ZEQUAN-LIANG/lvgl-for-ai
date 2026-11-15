#include "rtthread.h"
#include "littlevgl2rtt.h"
#include "lvgl.h"

extern void app_create(void);

int main(void)
{
    rt_err_t ret = littlevgl2rtt_init("lcd");

    if(ret == RT_EOK) {
        app_create();

        while(1) {
            rt_uint32_t ms = lv_task_handler();
            rt_thread_mdelay(ms);
        }
    }

    return ret;
}
