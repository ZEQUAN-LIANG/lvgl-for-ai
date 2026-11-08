/**
 * @file panel.c
 * Second user TU: proves each user/app C file is compiled without a registry.
 */

#include "app.h"

#include <stdio.h>

lv_obj_t * app_panel_create(lv_obj_t * parent)
{
    printf("[app] panel_create\n");

    lv_obj_t * panel = lv_obj_create(parent);
    app_set_name(panel, "panel");
    lv_obj_set_size(panel, 360, 160);
    lv_obj_set_pos(panel, 32, 96);
    lv_obj_set_style_bg_color(panel, lv_color_hex(0x1E293B), 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(panel, 0, 0);
    lv_obj_set_style_radius(panel, 12, 0);
    lv_obj_set_style_pad_all(panel, 16, 0);

    lv_obj_t * label = lv_label_create(panel);
    app_set_name(label, "panel_label");
    lv_label_set_text(label, "lvgl_engine");
    lv_obj_set_style_text_color(label, lv_color_hex(0xE2E8F0), 0);
    lv_obj_set_style_text_font(label, &lv_font_montserrat_16, 0);

    return panel;
}
