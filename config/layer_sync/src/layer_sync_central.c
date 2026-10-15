/*
 * Central side of layer sync: whenever the keyboard settles with no keys held, the highest
 * active layer is the toggled one (momentary/hold layers have been released). Send it to the
 * peripherals via the global-locality lyr_sync behavior. Resend after a peripheral connects
 * so a rebooted or reconnected half picks up the current layer.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(layer_sync, CONFIG_ZMK_LOG_LEVEL);

#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/events/position_state_changed.h>
#include <zmk/keymap.h>

#define MAX_POSITIONS 128
#define SETTLE_DELAY K_MSEC(30)
#define RESYNC_DELAY K_SECONDS(3)
#define RESYNC_ATTEMPTS 2

static ATOMIC_DEFINE(held_positions, MAX_POSITIONS);
static uint8_t last_sent;
static uint8_t resyncs_left;

static bool any_key_held(void) {
    for (size_t i = 0; i < ARRAY_SIZE(held_positions); i++) {
        if (atomic_get(&held_positions[i])) {
            return true;
        }
    }
    return false;
}

static void sync_work_cb(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(sync_work, sync_work_cb);

static void sync_work_cb(struct k_work *work) {
    /* A held key may be a momentary layer; the next release reschedules us. */
    if (any_key_held()) {
        return;
    }

    uint8_t layer = zmk_keymap_highest_layer_active();
    if (layer == last_sent && resyncs_left == 0) {
        return;
    }

    struct zmk_behavior_binding binding = {.behavior_dev = "lyr_sync", .param1 = layer};
    struct zmk_behavior_binding_event event = {
        .layer = layer,
        .timestamp = k_uptime_get(),
        .source = ZMK_POSITION_STATE_CHANGE_SOURCE_LOCAL,
    };

    int err = zmk_behavior_invoke_binding(&binding, event, true);
    if (err < 0) {
        LOG_WRN("Failed to send layer %d to peripherals (%d)", layer, err);
    }
    last_sent = layer;

    if (resyncs_left > 0 && --resyncs_left > 0) {
        k_work_reschedule(&sync_work, RESYNC_DELAY);
    }
}

static int layer_sync_listener(const zmk_event_t *eh) {
    const struct zmk_position_state_changed *pos = as_zmk_position_state_changed(eh);
    if (pos != NULL && pos->position < MAX_POSITIONS) {
        if (pos->state) {
            atomic_set_bit(held_positions, pos->position);
            return ZMK_EV_EVENT_BUBBLE;
        }
        atomic_clear_bit(held_positions, pos->position);
    }

    k_work_reschedule(&sync_work, SETTLE_DELAY);
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_sync, layer_sync_listener);
ZMK_SUBSCRIPTION(layer_sync, zmk_position_state_changed);
ZMK_SUBSCRIPTION(layer_sync, zmk_layer_state_changed);

static void connected(struct bt_conn *conn, uint8_t err) {
    struct bt_conn_info info;

    /* Only outgoing links are split peripherals; GATT discovery finishes after this fires. */
    if (err || bt_conn_get_info(conn, &info) || info.role != BT_CONN_ROLE_CENTRAL) {
        return;
    }
    resyncs_left = RESYNC_ATTEMPTS;
    k_work_reschedule(&sync_work, RESYNC_DELAY);
}

BT_CONN_CB_DEFINE(layer_sync_conn_cb) = {
    .connected = connected,
};
