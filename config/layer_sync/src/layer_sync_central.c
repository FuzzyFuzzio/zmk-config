/*
 * Central side of layer sync: send the highest active layer to the peripherals via the
 * global-locality lyr_sync behavior. Moving to a higher layer is delayed by MIN_HOLD so brief
 * layer-key holds don't flash on the display; dropping back is sent almost immediately.
 * Resend after a peripheral connects so a rebooted or reconnected half picks up the layer.
 */

#include <zephyr/kernel.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(layer_sync, CONFIG_ZMK_LOG_LEVEL);

#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/keymap.h>

#define MIN_HOLD K_MSEC(120)
#define SETTLE_DELAY K_MSEC(20)
#define RESYNC_DELAY K_SECONDS(3)
#define RESYNC_ATTEMPTS 2

static uint8_t last_sent;
static uint8_t resyncs_left;

static void send_layer(bool force) {
    uint8_t layer = zmk_keymap_highest_layer_active();
    if (layer == last_sent && !force) {
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
}

static void sync_work_cb(struct k_work *work) { send_layer(false); }
static K_WORK_DELAYABLE_DEFINE(sync_work, sync_work_cb);

static void resync_work_cb(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(resync_work, resync_work_cb);

static void resync_work_cb(struct k_work *work) {
    send_layer(true);
    if (resyncs_left > 0 && --resyncs_left > 0) {
        k_work_reschedule(&resync_work, RESYNC_DELAY);
    }
}

static int layer_sync_listener(const zmk_event_t *eh) {
    uint8_t layer = zmk_keymap_highest_layer_active();
    k_work_reschedule(&sync_work, layer > last_sent ? MIN_HOLD : SETTLE_DELAY);
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_sync, layer_sync_listener);
ZMK_SUBSCRIPTION(layer_sync, zmk_layer_state_changed);

static void connected(struct bt_conn *conn, uint8_t err) {
    struct bt_conn_info info;

    /* Only outgoing links are split peripherals; GATT discovery finishes after this fires. */
    if (err || bt_conn_get_info(conn, &info) || info.role != BT_CONN_ROLE_CENTRAL) {
        return;
    }
    resyncs_left = RESYNC_ATTEMPTS;
    k_work_reschedule(&resync_work, RESYNC_DELAY);
}

BT_CONN_CB_DEFINE(layer_sync_conn_cb) = {
    .connected = connected,
};
