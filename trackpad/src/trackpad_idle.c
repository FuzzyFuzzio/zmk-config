#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/logging/log.h>
#include <zmk/event_manager.h>
#include <zmk/events/activity_state_changed.h>

#include "input_pinnacle.h"

LOG_MODULE_REGISTER(trackpad_idle, CONFIG_INPUT_LOG_LEVEL);

#define PINNACLE_DEVICE(node_id) DEVICE_DT_GET(node_id),

static const struct device *const trackpads[] = {
    DT_FOREACH_STATUS_OKAY(cirque_pinnacle, PINNACLE_DEVICE)};

static int trackpad_activity_changed(const zmk_event_t *eh) {
    const struct zmk_activity_state_changed *event = as_zmk_activity_state_changed(eh);
    if (!event || event->state == ZMK_ACTIVITY_SLEEP) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    for (size_t i = 0; i < ARRAY_SIZE(trackpads); i++) {
        if (!device_is_ready(trackpads[i])) {
            LOG_ERR("Cannot change sleep on an uninitialized trackpad");
            continue;
        }
        int err = pinnacle_request_sleep(trackpads[i], event->state == ZMK_ACTIVITY_IDLE);
        if (err < 0) {
            LOG_ERR("Failed to request trackpad sleep change: %d", err);
        } else {
            LOG_INF("Trackpad %s requested", event->state == ZMK_ACTIVITY_IDLE ? "idle sleep" : "wake");
        }
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(trackpad_idle, trackpad_activity_changed);
ZMK_SUBSCRIPTION(trackpad_idle, zmk_activity_state_changed);
