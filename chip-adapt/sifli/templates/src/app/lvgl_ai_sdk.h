#ifndef LVGL_AI_SDK_H
#define LVGL_AI_SDK_H

#if defined(__has_include)
#  if __has_include("littlevgl2rtt.h")
#    define LVGL_AI_EZIP_ASSETS 1
#    include "rtthread.h"
#    include "littlevgl2rtt.h"
#  else
#    include "sim_sifli.h"
#  endif
#else
#  include "rtthread.h"
#  include "littlevgl2rtt.h"
#endif

#endif
