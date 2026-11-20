
#include "xhs_ui.h"

#include <stdint.h>
#include <stdio.h>

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

typedef struct {
    const char * name;
    const char * price;
    const char * sales;
    int cover_index;
    int category;
} xhs_product_t;

static xhs_product_t products[4] = {
    {XHS_TXT_PRODUCT_0_NAME, XHS_TXT_PRODUCT_0_PRICE, XHS_TXT_PRODUCT_0_SALES,
     0, 1},
    {XHS_TXT_PRODUCT_1_NAME, XHS_TXT_PRODUCT_1_PRICE, XHS_TXT_PRODUCT_1_SALES,
     5, 2},
    {XHS_TXT_PRODUCT_2_NAME, XHS_TXT_PRODUCT_2_PRICE, XHS_TXT_PRODUCT_2_SALES,
     3, 3},
    {XHS_TXT_PRODUCT_3_NAME, XHS_TXT_PRODUCT_3_PRICE, XHS_TXT_PRODUCT_3_SALES,
     2, 1},
};
#define XHS_PRODUCT_COUNT 4

static const char * const market_categories[6] = {
    XHS_TXT_MARKET_ALL,     XHS_TXT_MARKET_HOME, XHS_TXT_CAT_OUTFIT,
    XHS_TXT_MARKET_DIGITAL, XHS_TXT_MARKET_FOOD, XHS_TXT_MARKET_SPORT,
};

static lv_obj_t * market_page;
static lv_obj_t * market_grid;
static lv_obj_t * market_chips[6];
static lv_obj_t * product_overlay;
static lv_obj_t * product_cart_label;

static int active_market_category = 0;
static int open_product = -1;

static void xhs_product_event_cb(lv_event_t * event);

static void xhs_market_chip_style(int active)
{
    for(int i = 0; i < 6; i++) {
        lv_obj_set_style_bg_color(
            market_chips[i], lv_color_hex(i == active ? XHS_RED : XHS_SOFT), 0);
        lv_obj_t * label = lv_obj_get_child(market_chips[i], 0);
        if(label != NULL) {
            lv_obj_set_style_text_color(
                label, lv_color_hex(i == active ? XHS_WHITE : XHS_MUTED), 0);
        }
    }
}

static void xhs_product_card(lv_obj_t * parent, int index, int x, int y)
{
    xhs_product_t * product = &products[index];
    lv_obj_t * card = xhs_box(parent, x, y, XHS_COVER_W, 196);
    xhs_clickable(card, index == 0   ? "product_0"
                        : index == 1 ? "product_1"
                        : index == 2 ? "product_2"
                                     : "product_3");
    lv_obj_add_event_cb(card, xhs_product_event_cb, LV_EVENT_CLICKED,
                        (void *)(intptr_t)index);

    xhs_cover_thumb(card, product->cover_index, 0, 0, XHS_COVER_W, 112, 8);

    lv_obj_t * name = xhs_label_at(card, product->name, XHS_FT_12, XHS_TITLE, 0,
                                   118, XHS_COVER_W, 34);
    lv_label_set_long_mode(name, LV_LABEL_LONG_MODE_DOTS);
    lv_obj_set_style_text_line_space(name, 1, 0);

    char price[24];
    snprintf(price, sizeof(price), "%s%s", XHS_TXT_YUAN, product->price);
    xhs_label_at(card, price, XHS_FT_14B, XHS_RED, 0, 156, 100, 20);
    xhs_label_at(card, product->sales, XHS_FT_11, XHS_MUTED, 0, 178, 138, 16);
}

static void xhs_market_grid_build(void)
{
    if(market_grid == NULL) return;
    lv_obj_clean(market_grid);
    lv_obj_scroll_to_y(market_grid, 0, LV_ANIM_OFF);

    int shown = 0;
    for(int i = 0; i < XHS_PRODUCT_COUNT; i++) {
        if(active_market_category != 0 &&
           products[i].category != active_market_category) {
            continue;
        }
        int column = shown % 2;
        int row = shown / 2;
        xhs_product_card(market_grid, i, column == 0 ? 10 : 156, row * 206);
        shown++;
    }

    if(shown == 0) {
        lv_obj_t * empty =
            xhs_label_at(market_grid, XHS_TXT_MARKET_EMPTY, XHS_FT_12,
                         XHS_MUTED, 0, 60, XHS_SCREEN_W, 20);
        lv_obj_set_style_text_align(empty, LV_TEXT_ALIGN_CENTER, 0);
    }
    else {
        xhs_box(market_grid, 0, ((shown + 1) / 2) * 206, 1, 1);
    }
}

static void xhs_market_chip_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    active_market_category = (int)(intptr_t)lv_event_get_user_data(event);
    xhs_market_chip_style(active_market_category);
    xhs_market_grid_build();
    printf("[xhs] market category=%s\n",
           market_categories[active_market_category]);
}

static void xhs_market_banner_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] market banner clicked\n");
    }
}

static void xhs_market_search_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] market search clicked\n");
    }
}

static void xhs_product_more_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) == LV_EVENT_CLICKED) {
        printf("[xhs] product more clicked\n");
    }
}

static void xhs_product_cart_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    if(product_cart_label != NULL) {
        lv_label_set_text(product_cart_label, XHS_TXT_ADDED_CART);
    }
    lv_obj_t * button = lv_event_get_target_obj(event);
    lv_obj_set_style_bg_color(button, lv_color_hex(0x9A9A9E), 0);
    printf("[xhs] cart add product=%d\n", open_product);
}

static void xhs_product_build(lv_obj_t * page, int index)
{
    lv_obj_clean(page);
    xhs_product_t * product = &products[index];

    lv_obj_t * back = xhs_image(page, XHS_ICON_BACK, 12, 13);
    xhs_clickable(back, "product_back");
    lv_obj_set_ext_click_area(back, 8);
    lv_obj_add_event_cb(back, xhs_back_event_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * title = xhs_label_at(page, XHS_TXT_MARKET_DETAIL, XHS_FT_14B,
                                    XHS_TEXT, 0, 13, XHS_SCREEN_W, 18);
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t * more = xhs_image(page, XHS_ICON_MORE, 272, 18);
    xhs_clickable(more, "product_more");
    lv_obj_set_ext_click_area(more, 8);
    lv_obj_add_event_cb(more, xhs_product_more_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * top_line = xhs_box(page, 0, 43, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(top_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(top_line, LV_OPA_COVER, 0);

    lv_obj_t * content = xhs_scroll(page, 0, 44, XHS_SCREEN_W, 440);
    int cover_h = xhs_cover_height(product->cover_index);
    xhs_cover_scaled(content, product->cover_index, 200, 152, 10);
    int cover_bottom = 10 + cover_h * 2;

    lv_point_t name_size;
    lv_text_get_size(&name_size, product->name, xhs_font(XHS_FT_14B), 0, 2, 272,
                     LV_TEXT_FLAG_NONE);
    lv_obj_t * name = xhs_label(content, product->name, XHS_FT_14B, XHS_TITLE);
    lv_obj_set_pos(name, 16, cover_bottom + 12);
    lv_obj_set_width(name, 272);
    lv_label_set_long_mode(name, LV_LABEL_LONG_MODE_WRAP);

    int price_y = cover_bottom + 12 + name_size.y + 10;
    char price[24];
    snprintf(price, sizeof(price), "%s%s", XHS_TXT_YUAN, product->price);
    xhs_label_at(content, price, XHS_FT_14B, XHS_RED, 16, price_y, 120, 22);
    lv_obj_t * sales = xhs_label_at(content, product->sales, XHS_FT_11,
                                    XHS_MUTED, 184, price_y + 5, 104, 16);
    lv_obj_set_style_text_align(sales, LV_TEXT_ALIGN_RIGHT, 0);

    int divider_y = price_y + 36;
    lv_obj_t * divider = xhs_box(content, 16, divider_y, 272, 1);
    lv_obj_set_style_bg_color(divider, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(divider, LV_OPA_COVER, 0);

    lv_obj_t * guarantee =
        xhs_label_at(content, XHS_TXT_MARKET_GUARANTEE, XHS_FT_11, XHS_MUTED,
                     16, divider_y + 16, 272, 18);
    lv_label_set_long_mode(guarantee, LV_LABEL_LONG_MODE_DOTS);

    xhs_box(content, 0, divider_y + 60, 1, 1);

    lv_obj_t * bar = xhs_box(page, 0, 496, XHS_SCREEN_W, 44);
    lv_obj_set_style_bg_color(bar, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_t * bar_line = xhs_box(bar, 0, 0, XHS_SCREEN_W, 1);
    lv_obj_set_style_bg_color(bar_line, lv_color_hex(XHS_LINE), 0);
    lv_obj_set_style_bg_opa(bar_line, LV_OPA_COVER, 0);

    lv_obj_t * cart = xhs_pill(bar, 16, 4, 272, 36, XHS_RED, XHS_TXT_ADD_CART,
                               XHS_FT_13, XHS_WHITE, 18);
    xhs_clickable(cart, "add_cart");
    lv_obj_add_event_cb(cart, xhs_product_cart_cb, LV_EVENT_CLICKED, NULL);
    product_cart_label = lv_obj_get_child(cart, 0);
}

static void xhs_product_event_cb(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    int index = (int)(intptr_t)lv_event_get_user_data(event);
    if(product_overlay == NULL) {
        product_overlay = xhs_page(xhs_overlay_host());
    }
    open_product = index;
    xhs_product_build(product_overlay, index);
    xhs_open_overlay(product_overlay);
    printf("[xhs] product open index=%d\n", index);
}

lv_obj_t * xhs_market_create(lv_obj_t * parent)
{
    market_page = xhs_root_page(parent);

    lv_obj_t * title =
        xhs_label_at(market_page, XHS_TXT_MARKET_TITLE, XHS_FT_14B, XHS_TEXT, 0,
                     12, XHS_SCREEN_W, 20);
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t * search = xhs_image(market_page, XHS_ICON_SEARCH, 272, 12);
    xhs_clickable(search, "market_search");
    lv_obj_set_ext_click_area(search, 6);
    lv_obj_add_event_cb(search, xhs_market_search_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * banner = xhs_box(market_page, 12, 44, 280, 84);
    lv_obj_set_style_radius(banner, 14, 0);
    lv_obj_set_style_clip_corner(banner, true, 0);
    lv_obj_set_style_bg_color(banner, lv_color_hex(XHS_RED), 0);
    lv_obj_set_style_bg_grad_color(banner, lv_color_hex(0xFF7A8C), 0);
    lv_obj_set_style_bg_grad_dir(banner, LV_GRAD_DIR_HOR, 0);
    lv_obj_set_style_bg_opa(banner, LV_OPA_COVER, 0);
    lv_obj_set_style_shadow_color(banner, lv_color_hex(XHS_RED), 0);
    lv_obj_set_style_shadow_width(banner, 10, 0);
    lv_obj_set_style_shadow_opa(banner, 35, 0);
    xhs_clickable(banner, "market_banner");
    lv_obj_add_event_cb(banner, xhs_market_banner_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t * bubble = xhs_box(banner, 196, -22, 120, 120);
    lv_obj_set_style_radius(bubble, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(bubble, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(bubble, 26, 0);
    bubble = xhs_box(banner, 238, 52, 70, 70);
    lv_obj_set_style_radius(bubble, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(bubble, lv_color_hex(XHS_WHITE), 0);
    lv_obj_set_style_bg_opa(bubble, 20, 0);

    xhs_label_at(banner, XHS_TXT_MARKET_BANNER_TITLE, XHS_FT_14B, XHS_WHITE, 16,
                 16, 200, 22);
    xhs_label_at(banner, XHS_TXT_MARKET_BANNER_SUB, XHS_FT_11, XHS_WHITE, 16,
                 45, 200, 18);

    for(int i = 0; i < 6; i++) {
        lv_obj_t * chip =
            xhs_pill(market_page, 8 + i * 48, 140, 42, 22,
                     i == 0 ? XHS_RED : XHS_SOFT, market_categories[i],
                     XHS_FT_11, i == 0 ? XHS_WHITE : XHS_MUTED, 11);
        xhs_clickable(chip, NULL);
        lv_obj_add_event_cb(chip, xhs_market_chip_cb, LV_EVENT_CLICKED,
                            (void *)(intptr_t)i);
        market_chips[i] = chip;
    }

    market_grid = xhs_scroll(market_page, 0, 170, XHS_SCREEN_W, 324);
    lv_obj_set_name(market_grid, "market_grid");
    xhs_market_grid_build();
    return market_page;
}

#endif
