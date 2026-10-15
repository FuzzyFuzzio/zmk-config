#include <zephyr/kernel.h>
#include "battery.h"
#include "../assets/font.h"

#define OFFSET_X 29
#define OFFSET_Y 37

LV_IMG_DECLARE(bolt);
LV_IMG_DECLARE(battery);
LV_IMG_DECLARE(battery_mask);

void draw_battery_status(lv_obj_t *canvas, const struct status_state *state) {
    lv_draw_img_dsc_t img_dsc;
    lv_draw_img_dsc_init(&img_dsc);
    lv_draw_rect_dsc_t rect_dsc;
    init_rect_dsc(&rect_dsc, LVGL_FOREGROUND);
    lv_draw_label_dsc_t outline_dsc;
    init_label_dsc(&outline_dsc, LVGL_BACKGROUND, &font, LV_TEXT_ALIGN_CENTER);
    lv_draw_label_dsc_t label_dsc;
    init_label_dsc(&label_dsc, LVGL_FOREGROUND, &font, LV_TEXT_ALIGN_CENTER);

    lv_canvas_draw_img(canvas, 0, 0, &battery, &img_dsc);
    lv_canvas_draw_rect(canvas, 4, 4, 54 * state->battery / 100, 23, &rect_dsc);
    lv_canvas_draw_img(canvas, 2, 2, &battery_mask, &img_dsc);

    char text[10] = {};
    sprintf(text, "%i%%", state->battery);

    const int y = 9;
    const int w = 62;

    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (dx != 0 || dy != 0) {
                lv_canvas_draw_text(canvas, dx, y + dy, w, &outline_dsc, text);
            }
        }
    }

    lv_canvas_draw_text(canvas, 0, y, w, &label_dsc, text);

    if (state->charging) {
        lv_canvas_draw_img(canvas, OFFSET_X, OFFSET_Y, &bolt, &img_dsc);
    }
}
