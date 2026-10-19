#define DT_DRV_COMPAT zmk_behavior_layer_sync

#include <zephyr/device.h>
#include <drivers/behavior.h>
#include <zmk/behavior.h>

#include <layer_sync.h>

ZMK_EVENT_IMPL(zmk_layer_sync_changed);

static uint8_t synced_layer;

uint8_t zmk_layer_sync_get(void) { return synced_layer; }

static int on_layer_sync_pressed(struct zmk_behavior_binding *binding,
                                 struct zmk_behavior_binding_event event) {
#if !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    synced_layer = (uint8_t)binding->param1;
    raise_zmk_layer_sync_changed((struct zmk_layer_sync_changed){.layer = synced_layer});
#endif
    return ZMK_BEHAVIOR_OPAQUE;
}

static int on_layer_sync_released(struct zmk_behavior_binding *binding,
                                  struct zmk_behavior_binding_event event) {
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api behavior_layer_sync_driver_api = {
    .locality = BEHAVIOR_LOCALITY_GLOBAL,
    .binding_pressed = on_layer_sync_pressed,
    .binding_released = on_layer_sync_released,
};

BEHAVIOR_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL,
                        CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &behavior_layer_sync_driver_api);
