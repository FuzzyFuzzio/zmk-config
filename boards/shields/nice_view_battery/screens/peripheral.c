#include <zephyr/kernel.h>

#include <zephyr/logging/log.h>
LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#include <zmk/event_manager.h>
#include <zmk/events/usb_conn_state_changed.h>
#include <zmk/events/battery_state_changed.h>
#include <zmk/events/split_peripheral_status_changed.h>
#include <zmk/split/bluetooth/peripheral.h>
#include <zmk/display.h>
#include <zmk/usb.h>
#include <zmk/ble.h>
#include <zmk/battery.h>

#include "screen.h"
#include "../widgets/output.h"
#include "../widgets/battery.h"

#if IS_ENABLED(CONFIG_ZMK_BATTERY_SYNC)
#include <battery_sync.h>
#endif

#if IS_ENABLED(CONFIG_ZMK_LAYER_SYNC)
#include <layer_sync.h>
#include "../widgets/layer.h"

#define LAYER_NAME(node) DT_PROP_OR(node, display_name, DT_PROP_OR(node, label, ""))
static const char *layer_names[] = {
    DT_FOREACH_CHILD_STATUS_OKAY_SEP(DT_INST(0, zmk_keymap), LAYER_NAME, (, ))};
#endif

static sys_slist_t widgets = SYS_SLIST_STATIC_INIT(&widgets);

// Draw

static void draw_top(lv_obj_t *widget, lv_color_t cbuf[], const struct status_state *state) {
    lv_obj_t *canvas = lv_obj_get_child(widget, 0);
    draw_background(canvas, TOP_SIZE);

    draw_output_status(canvas, state);

    rotate_canvas(canvas, cbuf, TOP_SIZE);
}

static void draw_middle(lv_obj_t *widget, lv_color_t cbuf[], const struct status_state *state) {
    lv_obj_t *canvas = lv_obj_get_child(widget, 1);
    draw_background(canvas, CANVAS_SIZE);

    draw_battery_status(canvas, state);

    rotate_canvas(canvas, cbuf, CANVAS_SIZE);
}

#if IS_ENABLED(CONFIG_ZMK_LAYER_SYNC)
static void draw_bottom(lv_obj_t *widget, lv_color_t cbuf[], const struct status_state *state) {
    lv_obj_t *canvas = lv_obj_get_child(widget, 2);
    draw_background(canvas, CANVAS_SIZE);

    draw_layer_status(canvas, state);

    rotate_canvas(canvas, cbuf, CANVAS_SIZE);
}
#endif

// Battery status

static void set_battery_status(struct zmk_widget_screen *widget,
                               struct battery_status_state state) {
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
    widget->state.charging = state.usb_present;
#endif /* IS_ENABLED(CONFIG_USB_DEVICE_STACK) */

    widget->state.battery = state.level;
    widget->state.right_battery = state.right_level;

    draw_middle(widget->obj, widget->cbuf2, &widget->state);
}

static void battery_status_update_cb(struct battery_status_state state) {
    struct zmk_widget_screen *widget;
    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) { set_battery_status(widget, state); }
}

static struct battery_status_state battery_status_get_state(const zmk_event_t *eh) {
    const struct zmk_battery_state_changed *ev = as_zmk_battery_state_changed(eh);

    return (struct battery_status_state){
        .level = (ev != NULL) ? ev->state_of_charge : zmk_battery_state_of_charge(),
#if IS_ENABLED(CONFIG_ZMK_BATTERY_SYNC)
        .right_level = zmk_split_bt_peripheral_is_connected() ? zmk_battery_sync_get()
                                                            : ZMK_BATTERY_SYNC_UNKNOWN,
#else
        .right_level = UINT8_MAX,
#endif
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
        .usb_present = zmk_usb_is_powered(),
#endif /* IS_ENABLED(CONFIG_USB_DEVICE_STACK) */
    };
}

ZMK_DISPLAY_WIDGET_LISTENER(widget_battery_status, struct battery_status_state,
                            battery_status_update_cb, battery_status_get_state);

ZMK_SUBSCRIPTION(widget_battery_status, zmk_battery_state_changed);
#if IS_ENABLED(CONFIG_ZMK_BATTERY_SYNC)
ZMK_SUBSCRIPTION(widget_battery_status, zmk_battery_sync_changed);
#endif
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
ZMK_SUBSCRIPTION(widget_battery_status, zmk_usb_conn_state_changed);
#endif /* IS_ENABLED(CONFIG_USB_DEVICE_STACK) */

// Peripheral status

static struct peripheral_status_state get_state(const zmk_event_t *_eh) {
    return (struct peripheral_status_state){.connected = zmk_split_bt_peripheral_is_connected()};
}

static void set_connection_status(struct zmk_widget_screen *widget,
                                  struct peripheral_status_state state) {
    widget->state.connected = state.connected;
    if (!state.connected) {
        widget->state.right_battery = UINT8_MAX;
        draw_middle(widget->obj, widget->cbuf2, &widget->state);
    }

    draw_top(widget->obj, widget->cbuf, &widget->state);
}

static void output_status_update_cb(struct peripheral_status_state state) {
    struct zmk_widget_screen *widget;
    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) { set_connection_status(widget, state); }
}

ZMK_DISPLAY_WIDGET_LISTENER(widget_peripheral_status, struct peripheral_status_state,
                            output_status_update_cb, get_state)
ZMK_SUBSCRIPTION(widget_peripheral_status, zmk_split_peripheral_status_changed);

#if IS_ENABLED(CONFIG_ZMK_LAYER_SYNC)
// Layer status (highest active layer, mirrored from the central)

static void set_layer_status(struct zmk_widget_screen *widget, struct layer_status_state state) {
    widget->state.layer_label = state.label;

    draw_bottom(widget->obj, widget->cbuf3, &widget->state);
}

static void layer_status_update_cb(struct layer_status_state state) {
    struct zmk_widget_screen *widget;
    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) { set_layer_status(widget, state); }
}

static struct layer_status_state layer_status_get_state(const zmk_event_t *eh) {
    uint8_t index = zmk_layer_sync_get();
    return (struct layer_status_state){
        .index = index, .label = index < ARRAY_SIZE(layer_names) ? layer_names[index] : NULL};
}

ZMK_DISPLAY_WIDGET_LISTENER(widget_layer_status, struct layer_status_state, layer_status_update_cb,
                            layer_status_get_state)
ZMK_SUBSCRIPTION(widget_layer_status, zmk_layer_sync_changed);
#endif

// Initialization

int zmk_widget_screen_init(struct zmk_widget_screen *widget, lv_obj_t *parent) {
    widget->obj = lv_obj_create(parent);
    lv_obj_set_size(widget->obj, 160, 68);

    lv_obj_t *top = lv_canvas_create(widget->obj);
    lv_obj_align(top, LV_ALIGN_TOP_RIGHT, 0, 0);
    lv_canvas_set_buffer(top, widget->cbuf, TOP_SIZE, TOP_SIZE, LV_IMG_CF_TRUE_COLOR);

    lv_obj_t *middle = lv_canvas_create(widget->obj);
    lv_obj_align(middle, LV_ALIGN_TOP_LEFT, 28, 0);
    lv_canvas_set_buffer(middle, widget->cbuf2, CANVAS_SIZE, CANVAS_SIZE, LV_IMG_CF_TRUE_COLOR);

#if IS_ENABLED(CONFIG_NICE_VIEW_WIDGET_INVERTED) || IS_ENABLED(CONFIG_ZMK_LAYER_SYNC)
    lv_obj_t *bottom = lv_canvas_create(widget->obj);
    lv_obj_align(bottom, LV_ALIGN_TOP_LEFT, -40, 0);
    lv_canvas_set_buffer(bottom, widget->cbuf3, CANVAS_SIZE, CANVAS_SIZE, LV_IMG_CF_TRUE_COLOR);
#endif

    sys_slist_append(&widgets, &widget->node);
    widget_battery_status_init();
    widget_peripheral_status_init();
#if IS_ENABLED(CONFIG_ZMK_LAYER_SYNC)
    widget_layer_status_init();
#endif

    return 0;
}

lv_obj_t *zmk_widget_screen_obj(struct zmk_widget_screen *widget) { return widget->obj; }
