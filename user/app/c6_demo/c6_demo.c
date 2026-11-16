#include "c6_demo.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include "app.h"

#include <stdio.h>
#include <string.h>

#define DEMO_W        172
#define DEMO_H        320
#define DEMO_FOOTER_Y 284
#define DEMO_FOOTER_H 28

#define COL_BG    0x0B0F14
#define COL_CARD  0x111A22
#define COL_LINE  0x223746
#define COL_TEXT  0xE8F1F8
#define COL_MUTED 0x8EA3B3
#define COL_CYAN  0x38BDF8
#define COL_GREEN 0x34D399
#define COL_AMBER 0xFBBF24
#define COL_RED   0xFB7185

typedef struct {
    const char * name;
    const char * screen_name;
    const char * title;
    void (*build)(lv_obj_t * screen);
} demo_page_t;

typedef struct {
    lv_obj_t * clock;
    lv_obj_t * uptime;
    lv_obj_t * load_bar;
    lv_obj_t * load_value;
    lv_obj_t * cpu_bar;
    lv_obj_t * cpu_value;
    lv_obj_t * mem_bar;
    lv_obj_t * mem_value;
    lv_obj_t * net_bar;
    lv_obj_t * net_value;
    lv_obj_t * heap_value;
    lv_obj_t * status_uptime;
} demo_refs_t;

static void build_home(lv_obj_t * screen);
static void build_status(lv_obj_t * screen);
static void build_about(lv_obj_t * screen);

static const demo_page_t s_pages[] = {
    {"home", "c6_demo_page_home", "HOME", build_home},
    {"status", "c6_demo_page_status", "STATUS", build_status},
    {"about", "c6_demo_page_about", "ABOUT", build_about},
};

#define DEMO_PAGE_COUNT (sizeof(s_pages) / sizeof(s_pages[0]))

static size_t s_current;
static unsigned s_tick;
static demo_refs_t s_refs;
static lv_timer_t * s_timer;

static lv_obj_t * demo_box(lv_obj_t * parent, int x, int y, int w, int h)
{
    lv_obj_t * obj = lv_obj_create(parent);
    lv_obj_set_pos(obj, x, y);
    lv_obj_set_size(obj, w, h);
    lv_obj_set_style_bg_color(obj, lv_color_hex(COL_CARD), 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(obj, 1, 0);
    lv_obj_set_style_border_color(obj, lv_color_hex(COL_LINE), 0);
    lv_obj_set_style_radius(obj, 8, 0);
    lv_obj_set_style_pad_all(obj, 0, 0);
    app_obj_set_scrollable(obj, false);
    return obj;
}

static lv_obj_t * demo_label(lv_obj_t * parent, const char * text,
                             const lv_font_t * font, uint32_t color, int x,
                             int y, int w, lv_text_align_t align)
{
    lv_obj_t * label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    lv_obj_set_pos(label, x, y);
    if(w > 0) {
        lv_obj_set_width(label, w);
        lv_obj_set_style_text_align(label, align, 0);
    }
    return label;
}

static lv_obj_t * demo_bar(lv_obj_t * parent, int x, int y, int w, int h,
                           uint32_t color)
{
    lv_obj_t * bar = lv_bar_create(parent);
    lv_obj_set_pos(bar, x, y);
    lv_obj_set_size(bar, w, h);
    lv_bar_set_range(bar, 0, 100);
    lv_bar_set_value(bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar, lv_color_hex(COL_LINE), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(bar, lv_color_hex(color), LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, LV_PART_INDICATOR);
    lv_obj_set_style_radius(bar, h / 2, 0);
    lv_obj_set_style_radius(bar, h / 2, LV_PART_INDICATOR);
    app_obj_set_scrollable(bar, false);
    return bar;
}

static lv_obj_t * demo_nav_button(lv_obj_t * parent, int x, const char * text,
                                  const char * name, bool accent)
{
    lv_obj_t * button = lv_button_create(parent);
    lv_obj_set_pos(button, x, DEMO_FOOTER_Y);
    lv_obj_set_size(button, 72, DEMO_FOOTER_H);
    lv_obj_set_style_bg_color(button,
                              lv_color_hex(accent ? 0x0E2A3A : COL_CARD), 0);
    lv_obj_set_style_bg_opa(button, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(button, 1, 0);
    lv_obj_set_style_border_color(
        button, lv_color_hex(accent ? COL_CYAN : COL_LINE), 0);
    lv_obj_set_style_radius(button, 8, 0);
    lv_obj_set_style_shadow_width(button, 0, 0);
    lv_obj_set_style_pad_all(button, 0, 0);
    app_obj_set_name(button, name);

    lv_obj_t * label = lv_label_create(button);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(label,
                                lv_color_hex(accent ? COL_CYAN : COL_MUTED), 0);
    lv_obj_center(label);
    return button;
}

static void prev_cb(lv_event_t * event)
{
    (void)event;
    (void)c6_demo_page_prev();
}

static void next_cb(lv_event_t * event)
{
    (void)event;
    (void)c6_demo_page_next();
}

static void build_chrome(lv_obj_t * screen)
{
    lv_obj_t * brand = demo_label(screen, "C6 DEMO", &lv_font_montserrat_14,
                                  COL_TEXT, 8, 10, 0, LV_TEXT_ALIGN_LEFT);
    app_obj_set_name(brand, "c6_demo_brand");

    char page_text[20];
    snprintf(page_text, sizeof(page_text), "%s %u/%u", s_pages[s_current].title,
             (unsigned)(s_current + 1), (unsigned)DEMO_PAGE_COUNT);
    lv_obj_t * page = demo_label(screen, page_text, &lv_font_montserrat_14,
                                 COL_CYAN, 76, 10, 88, LV_TEXT_ALIGN_RIGHT);
    app_obj_set_name(page, "c6_demo_page_label");

    lv_obj_t * line = demo_box(screen, 8, 32, DEMO_W - 16, 1);
    lv_obj_set_style_bg_color(line, lv_color_hex(COL_LINE), 0);
    lv_obj_set_style_border_width(line, 0, 0);
    lv_obj_set_style_radius(line, 0, 0);
}

static void build_footer(lv_obj_t * screen)
{
    lv_obj_t * prev = demo_nav_button(screen, 8, "PREV", "c6_demo_prev", false);
    lv_obj_add_event_cb(prev, prev_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * next = demo_nav_button(screen, 92, "NEXT", "c6_demo_next", true);
    lv_obj_add_event_cb(next, next_cb, LV_EVENT_CLICKED, NULL);
}

static void build_home(lv_obj_t * screen)
{
    build_chrome(screen);

    s_refs.clock = demo_label(screen, "12:00", &lv_font_montserrat_20, COL_TEXT,
                              0, 48, DEMO_W, LV_TEXT_ALIGN_CENTER);
    app_obj_set_name(s_refs.clock, "c6_demo_clock");
    demo_label(screen, "ESP32-C6 / ST7789", &lv_font_montserrat_14, COL_MUTED,
               0, 80, DEMO_W, LV_TEXT_ALIGN_CENTER);

    lv_obj_t * card = demo_box(screen, 8, 108, DEMO_W - 16, 52);
    demo_label(card, "UPTIME", &lv_font_montserrat_14, COL_MUTED, 8, 6, 76,
               LV_TEXT_ALIGN_LEFT);
    s_refs.uptime = demo_label(card, "00:00", &lv_font_montserrat_16, COL_GREEN,
                               84, 6, 60, LV_TEXT_ALIGN_RIGHT);
    app_obj_set_name(s_refs.uptime, "c6_demo_uptime");

    demo_label(screen, "LOAD", &lv_font_montserrat_14, COL_MUTED, 8, 174, 72,
               LV_TEXT_ALIGN_LEFT);
    s_refs.load_value = demo_label(screen, "42%", &lv_font_montserrat_14,
                                   COL_CYAN, 92, 174, 56, LV_TEXT_ALIGN_RIGHT);
    app_obj_set_name(s_refs.load_value, "c6_demo_load_value");
    s_refs.load_bar = demo_bar(screen, 8, 194, DEMO_W - 16, 8, COL_CYAN);
    lv_bar_set_value(s_refs.load_bar, 42, LV_ANIM_OFF);
    app_obj_set_name(s_refs.load_bar, "c6_demo_load_bar");

    lv_obj_t * hint =
        demo_label(screen, "SERIAL: READY", &lv_font_montserrat_14, COL_MUTED,
                   0, 222, DEMO_W, LV_TEXT_ALIGN_CENTER);
    app_obj_set_name(hint, "c6_demo_hint");

    demo_label(screen, "SERIAL PAGE SWITCH", &lv_font_montserrat_14, COL_LINE,
               0, 246, DEMO_W, LV_TEXT_ALIGN_CENTER);

    build_footer(screen);
}

static void build_metric(lv_obj_t * screen, int y, const char * name,
                         uint32_t color, int initial, lv_obj_t ** bar,
                         lv_obj_t ** value, const char * object_name)
{
    char text[8];
    snprintf(text, sizeof(text), "%d%%", initial);

    demo_label(screen, name, &lv_font_montserrat_14, COL_TEXT, 8, y, 72,
               LV_TEXT_ALIGN_LEFT);
    *value = demo_label(screen, text, &lv_font_montserrat_14, color, 84, y, 64,
                        LV_TEXT_ALIGN_RIGHT);
    app_obj_set_name(*value, object_name);
    *bar = demo_bar(screen, 8, y + 18, DEMO_W - 16, 8, color);
    lv_bar_set_value(*bar, initial, LV_ANIM_OFF);
}

static void build_status(lv_obj_t * screen)
{
    build_chrome(screen);

    demo_label(screen, "SYSTEM STATUS", &lv_font_montserrat_14, COL_MUTED, 8,
               44, 140, LV_TEXT_ALIGN_LEFT);

    build_metric(screen, 70, "CPU", COL_CYAN, 43, &s_refs.cpu_bar,
                 &s_refs.cpu_value, "c6_demo_cpu_value");
    build_metric(screen, 112, "MEM", COL_GREEN, 52, &s_refs.mem_bar,
                 &s_refs.mem_value, "c6_demo_mem_value");
    build_metric(screen, 154, "NET", COL_AMBER, 32, &s_refs.net_bar,
                 &s_refs.net_value, "c6_demo_net_value");

    lv_obj_t * card = demo_box(screen, 8, 204, DEMO_W - 16, 56);
    demo_label(card, "HEAP", &lv_font_montserrat_14, COL_MUTED, 8, 6, 64,
               LV_TEXT_ALIGN_LEFT);
    s_refs.heap_value = demo_label(card, "183 KB", &lv_font_montserrat_16,
                                   COL_GREEN, 76, 6, 72, LV_TEXT_ALIGN_RIGHT);
    demo_label(card, "UPTIME", &lv_font_montserrat_14, COL_MUTED, 8, 32, 64,
               LV_TEXT_ALIGN_LEFT);
    s_refs.status_uptime =
        demo_label(card, "00:00", &lv_font_montserrat_16, COL_TEXT, 76, 32, 72,
                   LV_TEXT_ALIGN_RIGHT);

    build_footer(screen);
}

static void build_about(lv_obj_t * screen)
{
    build_chrome(screen);

    lv_obj_t * card = demo_box(screen, 8, 48, DEMO_W - 16, 132);
    demo_label(card, "C6 DEMO", &lv_font_montserrat_16, COL_TEXT, 8, 8, 140,
               LV_TEXT_ALIGN_LEFT);
    demo_label(card, "LVGL 9.6", &lv_font_montserrat_14, COL_CYAN, 8, 36, 140,
               LV_TEXT_ALIGN_LEFT);
    demo_label(card, "ST7789 172x320", &lv_font_montserrat_14, COL_MUTED, 8, 58,
               140, LV_TEXT_ALIGN_LEFT);
    demo_label(card, "NO TOUCH", &lv_font_montserrat_14, COL_AMBER, 8, 80, 140,
               LV_TEXT_ALIGN_LEFT);
    demo_label(card, "SERIAL CONTROL", &lv_font_montserrat_14, COL_GREEN, 8,
               102, 140, LV_TEXT_ALIGN_LEFT);

    lv_obj_t * bar = demo_bar(screen, 8, 198, DEMO_W - 16, 8, COL_AMBER);
    lv_bar_set_value(bar, 66, LV_ANIM_OFF);
    app_obj_set_name(bar, "c6_demo_about_bar");

    demo_label(screen, "READY FOR ESP-IDF", &lv_font_montserrat_14, COL_MUTED,
               0, 218, DEMO_W, LV_TEXT_ALIGN_CENTER);
    demo_label(screen, "PREV / NEXT", &lv_font_montserrat_14, COL_LINE, 0, 242,
               DEMO_W, LV_TEXT_ALIGN_CENTER);

    build_footer(screen);
}

static bool show_page(size_t index, bool animate)
{
    if(index >= DEMO_PAGE_COUNT) return false;

    lv_obj_t * screen = lv_obj_create(NULL);
    if(screen == NULL) return false;
    lv_obj_set_style_bg_color(screen, lv_color_hex(COL_BG), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(screen, 0, 0);
    app_obj_set_scrollable(screen, false);
    app_obj_set_name(screen, s_pages[index].screen_name);

    s_current = index;
    memset(&s_refs, 0, sizeof(s_refs));
    s_pages[index].build(screen);

    if(animate) {
        lv_screen_load_anim(screen, LV_SCREEN_LOAD_ANIM_MOVE_LEFT, 150, 0,
                            true);
    }
    else {
        lv_obj_t * old = lv_screen_active();
        lv_screen_load(screen);
        if(old != NULL && old != screen) lv_obj_delete(old);
    }

    printf("[c6_demo] page=%s\n", s_pages[index].name);
    fflush(stdout);
    return true;
}

static void update_home(void)
{
    unsigned seconds = s_tick / 2;
    unsigned hour = 12 + (seconds / 3600) % 12;
    unsigned minute = (seconds / 60) % 60;
    unsigned sec = seconds % 60;

    if(s_refs.clock != NULL) {
        lv_label_set_text_fmt(s_refs.clock, "%02u:%02u", hour, minute);
    }
    if(s_refs.uptime != NULL) {
        lv_label_set_text_fmt(s_refs.uptime, "%02u:%02u", (seconds / 60) % 100,
                              sec);
    }
    if(s_refs.load_bar != NULL && s_refs.load_value != NULL) {
        int load = 25 + (int)((s_tick * 7) % 60);
        lv_bar_set_value(s_refs.load_bar, load, LV_ANIM_OFF);
        lv_label_set_text_fmt(s_refs.load_value, "%d%%", load);
    }
}

static void update_status(void)
{
    unsigned seconds = s_tick / 2;
    int cpu = 30 + (int)((s_tick * 13) % 55);
    int mem = 45 + (int)((s_tick * 7) % 30);
    int net = 15 + (int)((s_tick * 17) % 70);
    int heap = 180 + (int)((s_tick * 3) % 40);

    if(s_refs.cpu_bar != NULL && s_refs.cpu_value != NULL) {
        lv_bar_set_value(s_refs.cpu_bar, cpu, LV_ANIM_OFF);
        lv_label_set_text_fmt(s_refs.cpu_value, "%d%%", cpu);
    }
    if(s_refs.mem_bar != NULL && s_refs.mem_value != NULL) {
        lv_bar_set_value(s_refs.mem_bar, mem, LV_ANIM_OFF);
        lv_label_set_text_fmt(s_refs.mem_value, "%d%%", mem);
    }
    if(s_refs.net_bar != NULL && s_refs.net_value != NULL) {
        lv_bar_set_value(s_refs.net_bar, net, LV_ANIM_OFF);
        lv_label_set_text_fmt(s_refs.net_value, "%d%%", net);
    }
    if(s_refs.heap_value != NULL) {
        lv_label_set_text_fmt(s_refs.heap_value, "%d KB", heap);
    }
    if(s_refs.status_uptime != NULL) {
        lv_label_set_text_fmt(s_refs.status_uptime, "%02u:%02u",
                              (seconds / 60) % 100, seconds % 60);
    }
}

static void demo_tick_cb(lv_timer_t * timer)
{
    (void)timer;
    s_tick++;
    if(s_current == 0) {
        update_home();
    }
    else if(s_current == 1) {
        update_status();
    }
}

static int find_page(const char * name)
{
    if(name == NULL) return -1;
    for(size_t i = 0; i < DEMO_PAGE_COUNT; i++) {
        if(strcmp(s_pages[i].name, name) == 0) return (int)i;
    }
    return -1;
}

void c6_demo_create(void)
{
    s_tick = 0;
    s_current = 0;
    if(!show_page(0, false)) {
        printf("[c6_demo] home page failed\n");
        fflush(stdout);
        return;
    }
    if(s_timer == NULL) {
        s_timer = lv_timer_create(demo_tick_cb, 500, NULL);
    }
    printf("[c6_demo] pages=%u\n", (unsigned)DEMO_PAGE_COUNT);
    fflush(stdout);
}

bool c6_demo_page_show(const char * name)
{
    int index = find_page(name);
    if(index < 0) {
        printf("[c6_demo] unknown page=%s\n", name != NULL ? name : "(null)");
        fflush(stdout);
        return false;
    }
    return show_page((size_t)index, true);
}

bool c6_demo_page_next(void)
{
    return show_page((s_current + 1) % DEMO_PAGE_COUNT, true);
}

bool c6_demo_page_prev(void)
{
    return show_page((s_current + DEMO_PAGE_COUNT - 1) % DEMO_PAGE_COUNT, true);
}

const char * c6_demo_page_current(void)
{
    return s_current < DEMO_PAGE_COUNT ? s_pages[s_current].name : NULL;
}

size_t c6_demo_page_count(void)
{
    return DEMO_PAGE_COUNT;
}

const char * c6_demo_page_name(size_t index)
{
    return index < DEMO_PAGE_COUNT ? s_pages[index].name : NULL;
}

#endif
