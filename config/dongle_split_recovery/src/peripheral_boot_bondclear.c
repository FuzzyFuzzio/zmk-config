/*
 * Peripheral boot-time bond clear.
 *
 * On a split peripheral (a Hillside View half running in non-central
 * role), watch for a specific two-key combo held during a short window
 * after boot. If the combo is observed pressed simultaneously, wipe all
 * stored BLE bonds. On the next reconnect the half has no bond, SMP
 * does a fresh just-works pairing, and any stale CCC / GATT state on
 * the dongle is implicitly thrown out alongside the bond.
 *
 * This is the manual recovery escape hatch for the "link up but no
 * input" failure mode that the dongle-side auto-heal cannot detect,
 * because in that case the BLE security exchange has succeeded - the
 * desync is one level higher, at the GATT subscription layer.
 *
 * Trigger model:
 *   - We listen to zmk_position_state_changed events. On a peripheral
 *     these fire when the local kscan detects a matrix change, BEFORE
 *     the event is forwarded to the central. So this works even when
 *     the central is unresponsive to GATT writes.
 *   - The boot window opens at module init (SYS_INIT, APPLICATION
 *     priority) and closes after CONFIG_PERIPHERAL_BOOT_BONDCLEAR_WINDOW_MS.
 *     After it closes the listener short-circuits, so normal typing
 *     and peripheral sleep/wake (which is not a cold boot) cannot
 *     ever trigger an unpair.
 *   - bt_unpair is dispatched from a delayed work item so it doesn't
 *     run inside the event-manager call stack and has time for the
 *     BT host to finish coming up.
 */

#define LOG_LEVEL CONFIG_PERIPHERAL_BOOT_BONDCLEAR_LOG_LEVEL
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(peripheral_boot_bondclear);

#include <zephyr/init.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>

#include <zmk/event_manager.h>
#include <zmk/events/position_state_changed.h>

#define WINDOW_MS CONFIG_PERIPHERAL_BOOT_BONDCLEAR_WINDOW_MS
#define POS_A     CONFIG_PERIPHERAL_BOOT_BONDCLEAR_POS_A
#define POS_B     CONFIG_PERIPHERAL_BOOT_BONDCLEAR_POS_B

/* The window is opened by static initialization rather than in SYS_INIT
 * so we cannot miss the very first kscan press events even if kscan's
 * init runs ahead of ours. SYS_INIT only schedules the closing timer.
 */
static atomic_t window_open  = ATOMIC_INIT(1);
static atomic_t pos_a_down   = ATOMIC_INIT(0);
static atomic_t pos_b_down   = ATOMIC_INIT(0);
static atomic_t fired        = ATOMIC_INIT(0);

static void do_unpair_work(struct k_work *w)
{
    ARG_UNUSED(w);
    LOG_WRN("Boot-combo bond clear: wiping all stored BLE bonds");
    int err = bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY);
    if (err) {
        LOG_ERR("bt_unpair failed: %d", err);
        return;
    }
    LOG_INF("Bonds cleared. Will pair fresh on next connection.");

    /* Drop any active connection so the central sees the bond loss
     * immediately and we re-pair on its next connect attempt.
     */
    struct bt_conn *conn = bt_conn_lookup_state_le(BT_ID_DEFAULT, NULL,
                                                   BT_CONN_STATE_CONNECTED);
    if (conn) {
        bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        bt_conn_unref(conn);
    }
}
static K_WORK_DELAYABLE_DEFINE(unpair_work, do_unpair_work);

static void close_window_work(struct k_work *w)
{
    ARG_UNUSED(w);
    atomic_set(&window_open, 0);
    LOG_DBG("Boot bondclear window closed");
}
static K_WORK_DELAYABLE_DEFINE(close_window, close_window_work);

static int position_listener(const zmk_event_t *eh)
{
    if (!atomic_get(&window_open)) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    const struct zmk_position_state_changed *ev =
        as_zmk_position_state_changed(eh);
    if (ev == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    /* Track the live press state of each trigger key. */
    if (ev->position == POS_A) {
        atomic_set(&pos_a_down, ev->state ? 1 : 0);
    } else if (ev->position == POS_B) {
        atomic_set(&pos_b_down, ev->state ? 1 : 0);
    } else {
        return ZMK_EV_EVENT_BUBBLE;
    }

    /* Both trigger keys held at once inside the boot window: arm once. */
    if (atomic_get(&pos_a_down) && atomic_get(&pos_b_down) &&
        atomic_cas(&fired, 0, 1)) {
        LOG_WRN("Boot bondclear combo observed (pos %d + %d) - "
                "scheduling unpair", POS_A, POS_B);
        /* Close the window immediately so we don't re-fire, and run the
         * unpair from the system workqueue after a short delay to let
         * the BT host settle.
         */
        atomic_set(&window_open, 0);
        k_work_cancel_delayable(&close_window);
        k_work_schedule(&unpair_work, K_MSEC(250));
    }

    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(peripheral_boot_bondclear, position_listener);
ZMK_SUBSCRIPTION(peripheral_boot_bondclear, zmk_position_state_changed);

static int peripheral_boot_bondclear_init(void)
{
    k_work_schedule(&close_window, K_MSEC(WINDOW_MS));
    LOG_INF("Boot bondclear armed for %d ms (combo: pos %d + pos %d)",
            WINDOW_MS, POS_A, POS_B);
    return 0;
}

SYS_INIT(peripheral_boot_bondclear_init, APPLICATION,
         CONFIG_APPLICATION_INIT_PRIORITY);
