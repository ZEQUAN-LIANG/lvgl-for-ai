
#include "app.h"
#include "textarea_evidence.h"

#include <stdio.h>

static lv_obj_t * textarea;

static void textarea_changed_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_VALUE_CHANGED) {
        return;
    }
    printf("[textarea_evidence] text=%s\n", lv_textarea_get_text(textarea));
}

static void textarea_group_attach(void)
{
    lv_group_t * group = lv_group_create();
    if(group == NULL) {
        printf("[textarea_evidence] focus group unavailable\n");
        return;
    }
    lv_group_add_obj(group, textarea);
    lv_group_focus_obj(textarea);
    for(lv_indev_t * indev = lv_indev_get_next(NULL); indev != NULL;
        indev = lv_indev_get_next(indev)) {
        lv_indev_type_t type = lv_indev_get_type(indev);
        if((type == LV_INDEV_TYPE_KEYPAD) ||
           (type == LV_INDEV_TYPE_ENCODER)) {
            lv_indev_set_group(indev, group);
        }
    }
}

void textarea_evidence_create(void)
{
    lv_obj_t * screen = lv_screen_active();

    lv_obj_t * title = lv_label_create(screen);
    lv_label_set_text(title, "Textarea evidence");
    lv_obj_set_pos(title, 40, 40);

    textarea = lv_textarea_create(screen);
    lv_obj_set_pos(textarea, 40, 90);
    lv_obj_set_size(textarea, 360, 120);
    lv_textarea_set_one_line(textarea, false);
    lv_textarea_set_placeholder_text(textarea, "Type ASCII text");
    lv_obj_add_event_cb(
        textarea, textarea_changed_cb, LV_EVENT_VALUE_CHANGED, NULL
    );

    textarea_group_attach();
    printf("[textarea_evidence] ready\n");
}
