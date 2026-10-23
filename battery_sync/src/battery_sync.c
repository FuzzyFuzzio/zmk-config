#define DT_DRV_COMPAT zmk_behavior_battery_sync

#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <drivers/behavior.h>
#include <zmk/behavior.h>
#include <battery_sync.h>

LOG_MODULE_REGISTER(battery_sync, CONFIG_ZMK_LOG_LEVEL);

ZMK_EVENT_IMPL(zmk_battery_sync_changed);

static uint8_t right_level = ZMK_BATTERY_SYNC_UNKNOWN;

uint8_t zmk_battery_sync_get(void) { return right_level; }

static void set_right_level(uint8_t level) {
    if (right_level == level) {
        return;
    }

    right_level = level;
    int err = raise_zmk_battery_sync_changed((struct zmk_battery_sync_changed){.level = level});
    if (err < 0) {
        LOG_WRN("Failed to update right battery display (%d)", err);
    }
}

static int on_battery_sync_pressed(struct zmk_behavior_binding *binding,
                                   struct zmk_behavior_binding_event event) {
    if (binding->param1 > 100 && binding->param1 != ZMK_BATTERY_SYNC_UNKNOWN) {
        LOG_ERR("Invalid right battery level: %u", binding->param1);
        return -EINVAL;
    }

    set_right_level(binding->param1);
    return ZMK_BEHAVIOR_OPAQUE;
}

static int on_battery_sync_released(struct zmk_behavior_binding *binding,
                                    struct zmk_behavior_binding_event event) {
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api battery_sync_api = {
    .locality = BEHAVIOR_LOCALITY_GLOBAL,
    .binding_pressed = on_battery_sync_pressed,
    .binding_released = on_battery_sync_released,
};

BEHAVIOR_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL,
                        CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &battery_sync_api);

#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL) || IS_ENABLED(CONFIG_SHIELD_HILLSIDE_VIEW_RIGHT)

#include <zephyr/bluetooth/gatt.h>
#include <zmk/battery.h>

/* A right-only characteristic identifies the half independently of BLE bond order. */
#define RIGHT_BATTERY_SERVICE_UUID                                                                  \
    BT_UUID_128_ENCODE(0x8d6d0001, 0x4f6b, 0x4b7c, 0x9b20, 0x828e3d0d879a)
#define RIGHT_BATTERY_LEVEL_UUID                                                                    \
    BT_UUID_128_ENCODE(0x8d6d0002, 0x4f6b, 0x4b7c, 0x9b20, 0x828e3d0d879a)

static struct bt_uuid_128 right_battery_uuid = BT_UUID_INIT_128(RIGHT_BATTERY_LEVEL_UUID);

#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)

#include <zephyr/bluetooth/conn.h>
#include <zephyr/sys/atomic.h>
#include <zmk/ble.h>
#include <zmk/events/position_state_changed.h>
#include <zmk/split/central.h>

#define POLL_INTERVAL K_SECONDS(60)
#define RETRY_DELAY K_SECONDS(3)

struct battery_read {
    struct bt_gatt_read_params params;
    struct bt_conn *conn;
    atomic_t busy;
    bool unsupported;
};

static struct battery_read reads[CONFIG_BT_MAX_CONN];
static struct bt_conn *right_conn;

static void sync_work_cb(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(sync_work, sync_work_cb);
static void poll_work_cb(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(poll_work, poll_work_cb);

static void sync_connection(struct bt_conn *conn, void *data) {
    struct bt_conn_info info;
    if (bt_conn_get_info(conn, &info) || info.role != BT_CONN_ROLE_CENTRAL ||
        info.state != BT_CONN_STATE_CONNECTED) {
        return;
    }

    int source = zmk_ble_put_peripheral_addr(bt_conn_get_dst(conn));
    if (source < 0) {
        LOG_WRN("Failed to locate split peripheral for battery sync (%d)", source);
        return;
    }

    struct zmk_behavior_binding binding = {
        .behavior_dev = "bat_sync",
        .param1 = zmk_battery_sync_get(),
    };
    struct zmk_behavior_binding_event event = {
        .timestamp = k_uptime_get(),
        .source = ZMK_POSITION_STATE_CHANGE_SOURCE_LOCAL,
    };

    int err = zmk_split_central_invoke_behavior(source, &binding, event, true);
    if (err < 0) {
        LOG_WRN("Failed to mirror right battery to peripheral %d (%d)", source, err);
    }
}

static void sync_work_cb(struct k_work *work) {
    /* Preserve a reconnect timer installed before this queued handler starts. */
    k_work_schedule(&sync_work, POLL_INTERVAL);
    bt_conn_foreach(BT_CONN_TYPE_LE, sync_connection, NULL);
}

static void update_right_level(uint8_t level) {
    set_right_level(level);
    k_work_reschedule(&sync_work, K_NO_WAIT);
}

static uint8_t battery_read_cb(struct bt_conn *conn, uint8_t err,
                              struct bt_gatt_read_params *params, const void *data,
                              uint16_t length) {
    struct battery_read *read = CONTAINER_OF(params, struct battery_read, params);
    struct bt_conn_info info;
    bool connected = bt_conn_get_info(conn, &info) == 0 &&
                     info.state == BT_CONN_STATE_CONNECTED;

    if (!connected) {
        /* The disconnect callback invalidates the display; ignore late read completions. */
    } else if (err == BT_ATT_ERR_ATTRIBUTE_NOT_FOUND) {
        read->unsupported = true;
        LOG_DBG("Peripheral has no right-half battery service");
        if (conn == right_conn) {
            update_right_level(ZMK_BATTERY_SYNC_UNKNOWN);
        }
    } else if (err || !data || length != sizeof(uint8_t) || *(const uint8_t *)data > 100) {
        LOG_WRN("Failed to read right battery (ATT %u, length %u)", err, length);
        if (conn == right_conn) {
            update_right_level(ZMK_BATTERY_SYNC_UNKNOWN);
        }
        k_work_reschedule(&poll_work, RETRY_DELAY);
    } else if (right_conn && right_conn != conn) {
        LOG_ERR("More than one peripheral exposes the right-half battery service");
    } else {
        if (!right_conn) {
            right_conn = bt_conn_ref(conn);
        }
        update_right_level(*(const uint8_t *)data);
    }

    read->conn = NULL;
    atomic_clear(&read->busy);
    bt_conn_unref(conn);
    return BT_GATT_ITER_STOP;
}

static void poll_connection(struct bt_conn *conn, void *data) {
    struct bt_conn_info info;
    if (bt_conn_get_info(conn, &info) || info.role != BT_CONN_ROLE_CENTRAL ||
        info.state != BT_CONN_STATE_CONNECTED) {
        return;
    }

    struct battery_read *read = &reads[bt_conn_index(conn)];
    if (read->unsupported || !atomic_cas(&read->busy, 0, 1)) {
        return;
    }

    /* Keep the connection (and its index) alive until this request completes. */
    read->conn = bt_conn_ref(conn);
    read->params = (struct bt_gatt_read_params){
        .func = battery_read_cb,
        .handle_count = 0,
        .by_uuid = {
            .start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE,
            .end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE,
            .uuid = &right_battery_uuid.uuid,
        },
    };

    int err = bt_gatt_read(conn, &read->params);
    if (err < 0) {
        LOG_WRN("Failed to request right battery level (%d)", err);
        if (conn == right_conn) {
            update_right_level(ZMK_BATTERY_SYNC_UNKNOWN);
        }
        read->conn = NULL;
        atomic_clear(&read->busy);
        bt_conn_unref(conn);
        k_work_reschedule(&poll_work, RETRY_DELAY);
    }
}

static void poll_work_cb(struct k_work *work) {
    k_work_reschedule(&poll_work, POLL_INTERVAL);
    bt_conn_foreach(BT_CONN_TYPE_LE, poll_connection, NULL);
}

static void connected(struct bt_conn *conn, uint8_t err) {
    struct bt_conn_info info;
    if (err || bt_conn_get_info(conn, &info) || info.role != BT_CONN_ROLE_CENTRAL) {
        return;
    }

    reads[bt_conn_index(conn)].unsupported = false;
    k_work_reschedule(&poll_work, RETRY_DELAY);
    k_work_reschedule(&sync_work, RETRY_DELAY);
}

static void disconnected(struct bt_conn *conn, uint8_t reason) {
    if (conn == right_conn) {
        right_conn = NULL;
        update_right_level(ZMK_BATTERY_SYNC_UNKNOWN);
        bt_conn_unref(conn);
    }
}

BT_CONN_CB_DEFINE(battery_sync_conn_cb) = {
    .connected = connected,
    .disconnected = disconnected,
};

#else

static ssize_t read_battery(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf,
                            uint16_t len, uint16_t offset) {
    uint8_t level = zmk_battery_state_of_charge();
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &level, sizeof(level));
}

BT_GATT_SERVICE_DEFINE(right_battery_service,
    BT_GATT_PRIMARY_SERVICE(BT_UUID_DECLARE_128(RIGHT_BATTERY_SERVICE_UUID)),
    BT_GATT_CHARACTERISTIC(&right_battery_uuid.uuid, BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ_ENCRYPT, read_battery, NULL, NULL));

#endif
#endif

#if !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
#include <zmk/events/split_peripheral_status_changed.h>

static int peripheral_status_listener(const zmk_event_t *eh) {
    const struct zmk_split_peripheral_status_changed *ev =
        as_zmk_split_peripheral_status_changed(eh);
    if (!ev->connected) {
        set_right_level(ZMK_BATTERY_SYNC_UNKNOWN);
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(battery_sync_status, peripheral_status_listener);
ZMK_SUBSCRIPTION(battery_sync_status, zmk_split_peripheral_status_changed);
#endif
