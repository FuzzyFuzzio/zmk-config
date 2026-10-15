/*
 * Dongle BLE split bond auto-heal.
 *
 * Watches outgoing (central-role) connections - which on this build are the
 * split peripheral connections - and clears the stored bond for a peer when
 * its keys are evidently wrong:
 *   - a definitive SMP/encryption key error (key missing, auth fail, rejected),
 *   - a disconnect with reason "MIC failure", or
 *   - N consecutive disconnects before the link ever encrypted. This catches
 *     the case where BOTH sides hold a bond but the LTKs diverged: the half
 *     detects the MIC failure and drops, and the dongle never sees a
 *     security error - which previously left the halves stuck until a
 *     manual bondclear on each half.
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

#include <stdio.h>
#include <string.h>

#include <zephyr/init.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>

#define COOLDOWN_MS          CONFIG_DONGLE_BOND_AUTOHEAL_COOLDOWN_MS
#define MAX_UNENC_DISCONNECTS CONFIG_DONGLE_BOND_AUTOHEAL_MAX_UNENCRYPTED_DISCONNECTS
#define PEER_SLOTS           4

struct peer_state {
    bt_addr_le_t addr;
    bool encrypted;
    uint8_t unenc_disconnects;
    bool has_unpaired;
    int64_t last_unpair_uptime;
};

/* Only touched from BT host callbacks, which run on a single thread. */
static struct peer_state peers[PEER_SLOTS];
static size_t next_evict;

K_MSGQ_DEFINE(unpair_q, sizeof(bt_addr_le_t), PEER_SLOTS, 1);

/* bt_unpair is deferred so it never frees keys that a conn object being
 * torn down in the disconnected callback still points at.
 */
static void unpair_work_handler(struct k_work *work)
{
    ARG_UNUSED(work);
    bt_addr_le_t peer;

    while (k_msgq_get(&unpair_q, &peer, K_NO_WAIT) == 0) {
        char addr[BT_ADDR_LE_STR_LEN];
        bt_addr_le_to_str(&peer, addr, sizeof(addr));

        /* Also drops any live link to the peer so it reconnects and re-pairs. */
        int err = bt_unpair(BT_ID_DEFAULT, &peer);
        if (err) {
            LOG_ERR("bt_unpair(%s) failed: %d", addr, err);
        } else {
            LOG_INF("Bond for %s cleared. Awaiting fresh pairing.", addr);
        }
    }
}
static K_WORK_DEFINE(unpair_work, unpair_work_handler);

static bool is_split_peer(struct bt_conn *conn)
{
    struct bt_conn_info info;

    /* Incoming (peripheral-role) links are host HID, a different pairing namespace. */
    return bt_conn_get_info(conn, &info) == 0 && info.role == BT_CONN_ROLE_CENTRAL;
}

static struct peer_state *peer_for(const bt_addr_le_t *addr)
{
    for (size_t i = 0; i < PEER_SLOTS; i++) {
        if (bt_addr_le_eq(&peers[i].addr, addr)) {
            return &peers[i];
        }
    }

    struct peer_state *p = NULL;
    for (size_t i = 0; i < PEER_SLOTS; i++) {
        if (bt_addr_le_eq(&peers[i].addr, BT_ADDR_LE_ANY)) {
            p = &peers[i];
            break;
        }
    }
    if (p == NULL) {
        p = &peers[next_evict];
        next_evict = (next_evict + 1) % PEER_SLOTS;
    }

    memset(p, 0, sizeof(*p));
    bt_addr_le_copy(&p->addr, addr);
    return p;
}

static void request_unpair(struct peer_state *p, const char *why)
{
    char addr[BT_ADDR_LE_STR_LEN];
    bt_addr_le_to_str(&p->addr, addr, sizeof(addr));

    int64_t now = k_uptime_get();
    if (p->has_unpaired && (now - p->last_unpair_uptime) < COOLDOWN_MS) {
        LOG_WRN("%s with %s but in cooldown - skipping unpair", why, addr);
        return;
    }

    LOG_WRN("%s with split peripheral %s - clearing bond to allow a fresh pairing",
            why, addr);

    p->has_unpaired = true;
    p->last_unpair_uptime = now;
    p->unenc_disconnects = 0;

    if (k_msgq_put(&unpair_q, &p->addr, K_NO_WAIT) != 0) {
        LOG_ERR("Unpair queue full, dropping request for %s", addr);
        return;
    }
    k_work_submit(&unpair_work);
}

/* Errors that mean the stored keys are wrong. UNSPECIFIED (timeouts, a link
 * dropped mid-procedure during a power glitch) is deliberately excluded so a
 * transient fault can't wipe a good bond and start a re-pair at a bad moment.
 */
static bool is_key_error(enum bt_security_err err)
{
    switch (err) {
    case BT_SECURITY_ERR_AUTH_FAIL:
    case BT_SECURITY_ERR_PIN_OR_KEY_MISSING:
    case BT_SECURITY_ERR_KEY_REJECTED:
        return true;
    default:
        return false;
    }
}

static void connected(struct bt_conn *conn, uint8_t err)
{
    if (err || !is_split_peer(conn)) {
        return;
    }
    peer_for(bt_conn_get_dst(conn))->encrypted = false;
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    if (!is_split_peer(conn)) {
        return;
    }

    struct peer_state *p = peer_for(bt_conn_get_dst(conn));

    if (reason == BT_HCI_ERR_TERM_DUE_TO_MIC_FAIL) {
        request_unpair(p, "MIC failure (mismatched keys)");
        return;
    }

    /* 0x3E = link never established (RF), says nothing about the keys. */
    if (p->encrypted || MAX_UNENC_DISCONNECTS == 0 ||
        reason == BT_HCI_ERR_CONN_FAIL_TO_ESTAB) {
        return;
    }

    /* With mismatched keys the half usually detects the MIC failure and drops
     * silently, so the dongle only sees e.g. a supervision timeout here.
     */
    p->unenc_disconnects++;
    LOG_WRN("Split peripheral disconnected before encrypting (reason 0x%02x), %d/%d",
            reason, p->unenc_disconnects, MAX_UNENC_DISCONNECTS);

    if (p->unenc_disconnects >= MAX_UNENC_DISCONNECTS) {
        request_unpair(p, "Repeated disconnects before encryption");
    }
}

static void security_changed(struct bt_conn *conn, bt_security_t level,
                             enum bt_security_err err)
{
    if (!is_split_peer(conn)) {
        return;
    }

    struct peer_state *p = peer_for(bt_conn_get_dst(conn));

    if (err == BT_SECURITY_ERR_SUCCESS) {
        if (level >= BT_SECURITY_L2) {
            p->encrypted = true;
            p->unenc_disconnects = 0;
        }
        return;
    }

    if (!is_key_error(err)) {
        LOG_WRN("Non-key security err %d with split peripheral - ignoring", err);
        return;
    }

    char why[32];
    snprintf(why, sizeof(why), "Security err %d", err);
    request_unpair(p, why);
}

static struct bt_conn_cb conn_cb = {
    .connected = connected,
    .disconnected = disconnected,
    .security_changed = security_changed,
};

static int dongle_bond_autoheal_init(void)
{
    bt_conn_cb_register(&conn_cb);
    LOG_INF("Dongle bond auto-heal active (cooldown %d ms, unencrypted-disconnect limit %d)",
            COOLDOWN_MS, MAX_UNENC_DISCONNECTS);
    return 0;
}

SYS_INIT(dongle_bond_autoheal_init, APPLICATION,
         CONFIG_APPLICATION_INIT_PRIORITY);
