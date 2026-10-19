#include "screens/screen.h"

/* CMakeLists.txt only builds this file when CONFIG_NICE_VIEW_WIDGET_STATUS is set. */
static struct zmk_widget_screen screen_widget;

lv_obj_t *zmk_display_status_screen() {
    lv_obj_t *screen = lv_obj_create(NULL);

    zmk_widget_screen_init(&screen_widget, screen);
    lv_obj_align(zmk_widget_screen_obj(&screen_widget), LV_ALIGN_TOP_LEFT, 0, 0);

    return screen;
}
