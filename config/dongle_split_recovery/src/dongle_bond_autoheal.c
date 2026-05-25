/*
 * Dongle BLE split bond auto-heal.
 *
 * Watches for BLE security failures on outgoing (central-role) connections
 * - which on this build are the split peripheral connections - and clears
 * the stored bond for that peer when authentication / encryption fails.
 * The next connection attempt then performs a fresh just-works pairing.
 *
 * This is the dongle-side half of a self-healing bond strategy. The other
 * half is CONFIG_BT_SMP_ALLOW_UNAUTH_OVERWRITE=y on the peripherals,
 * which lets the peripheral accept the dongle's new keys to overwrite
 * its own stored bond.
 *
 * Successful connections (the normal sleep/wake cycle on a battery
 * peripheral) fire security_changed with err=SUCCESS and are ignored.
 *
 * Incoming connections (e.g. HID over BLE, which would have
 * role == BT_CONN_ROLE_PERIPHERAL on this device) live in a different
 * pairing namespace and are skipped explicitly so a host-side pairing
 * hiccup cannot accidentally nuke split bonds.
 */

#define LOG_LEVEL CONFIG_DONGLE_BOND_AUTOHEAL_LOG_LEVEL
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(dongle_bond_autoheal);

#include <zephyr/init.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>

#define COOLDOWN_MS CONFIG_DONGLE_BOND_AUTOHEAL_COOLDOWN_MS

static int64_t last_unpair_uptime;
static bt_addr_le_t last_unpair_addr;

static void security_changed(struct bt_conn *conn, bt_security_t level,
                             enum bt_security_err err)
{
    ARG_UNUSED(level);

    if (err == BT_SECURITY_ERR_SUCCESS) {
        /* Encryption restored or freshly negotiated successfully.
         * Normal sleep/wake reconnects land here. Do nothing.
         */
        return;
    }

    struct bt_conn_info info;
    if (bt_conn_get_info(conn, &info) != 0) {
        return;
    }

    /* Only act on outgoing connections (split peripherals). Incoming
     * connections (HID over BLE) use a different pairing namespace.
     */
    if (info.role != BT_CONN_ROLE_CENTRAL) {
        return;
    }

    const bt_addr_le_t *peer = bt_conn_get_dst(conn);
    char addr[BT_ADDR_LE_STR_LEN];
    bt_addr_le_to_str(peer, addr, sizeof(addr));

    int64_t now = k_uptime_get();
    if (bt_addr_le_eq(peer, &last_unpair_addr) &&
        (now - last_unpair_uptime) < COOLDOWN_MS) {
        LOG_WRN("Security err %d with %s but in cooldown - skipping unpair",
                err, addr);
        return;
    }

    LOG_WRN("Security err %d with split peripheral %s - "
            "clearing bond to allow a fresh pairing", err, addr);

    bt_addr_le_copy(&last_unpair_addr, peer);
    last_unpair_uptime = now;

    /* Drop the link first so the unpair doesn't race against a still-open
     * (but unusable) encrypted channel. The peripheral will re-advertise
     * and we will reconnect with no stored bond, triggering a fresh
     * just-works pair. CONFIG_BT_SMP_ALLOW_UNAUTH_OVERWRITE=y on the
     * peripheral lets it overwrite its own stored bond on the new pair.
     */
    int derr = bt_conn_disconnect(conn, BT_HCI_ERR_AUTH_FAIL);
    if (derr && derr != -ENOTCONN) {
        LOG_WRN("bt_conn_disconnect(%s) returned %d", addr, derr);
    }

    int uerr = bt_unpair(BT_ID_DEFAULT, peer);
    if (uerr) {
        LOG_ERR("bt_unpair(%s) failed: %d", addr, uerr);
    } else {
        LOG_INF("Bond for %s cleared. Awaiting fresh pairing.", addr);
    }
}

static struct bt_conn_cb conn_cb = {
    .security_changed = security_changed,
};

static int dongle_bond_autoheal_init(void)
{
    bt_conn_cb_register(&conn_cb);
    LOG_INF("Dongle bond auto-heal active (cooldown %d ms)", COOLDOWN_MS);
    return 0;
}

SYS_INIT(dongle_bond_autoheal_init, APPLICATION,
         CONFIG_APPLICATION_INIT_PRIORITY);
