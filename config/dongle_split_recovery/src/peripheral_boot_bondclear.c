/*
 * Peripheral bond clear / re-pair trigger.
 *
 * On a split peripheral (a Hillside View half running in non-central
 * role), watch for a specific two-key combo and wipe all stored BLE
 * bonds when it is observed. On the next reconnect the half has no
 * bond, SMP does a fresh just-works pairing, and any stale CCC /
 * GATT state on the dongle is implicitly thrown out alongside the
 * bond. (The dongle-side auto-heal in dongle_bond_autoheal.c picks
 * up the resulting SMP failure and clears its own stored bond too.)
 *
 * Why two modes:
 *
 *   The dongle auto-heal hooks security_changed and only fires on
 *   BLE security FAILURE. If a desync is at the GATT subscription
 *   layer instead (link up, encryption OK, but no notifications
 *   flow) the dongle cannot detect it. That is exactly the
 *   "connection icon shows but no input" case the user has hit.
 *   This module is the peripheral-side escape hatch for that case.
 *
 * Trigger model:
 *
 *   - We listen to zmk_position_state_changed events. On a
 *     peripheral these fire when the local kscan detects a matrix
 *     change, BEFORE the event is forwarded to the central, so the
 *     trigger works even when the central is unresponsive to GATT
 *     writes.
 *
 *   - BOOT WINDOW mode: the window is open by static
 *     initialization so the very first press cannot be missed, and
 *     closes after CONFIG_PERIPHERAL_BOOT_BONDCLEAR_WINDOW_MS.
 *     Holding the combo at power-on is the "I want to wipe bonds
 *     on next boot" recovery procedure.
 *
 *   - PANIC HOLD mode: any time during normal operation, if both
 *     trigger keys are held continuously for
 *     CONFIG_PERIPHERAL_BOOT_BONDCLEAR_HOLD_MS milliseconds, the
 *     unpair fires. This is the "the link is up but no input
 *     reaches the host, fix it without rebooting" recovery path.
 *     The hold duration (5 s by default) plus the trigger being
 *     two outer-corner keys makes accidental triggers vanishingly
 *     unlikely.
 *
 *   - bt_unpair runs from a delayable work item so it isn't called
 *     inside the event-manager call stack and has time for the BT
 *     host to be ready.
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
#define HOLD_MS   CONFIG_PERIPHERAL_BOOT_BONDCLEAR_HOLD_MS
#define POS_A     CONFIG_PERIPHERAL_BOOT_BONDCLEAR_POS_A
#define POS_B     CONFIG_PERIPHERAL_BOOT_BONDCLEAR_POS_B

/* Live press state. Updated from the event-manager listener thread. */
static atomic_t pos_a_down  = ATOMIC_INIT(0);
static atomic_t pos_b_down  = ATOMIC_INIT(0);

/* fired latches true the first time the unpair work has been scheduled,
 * so neither the boot path nor the panic-hold path can re-enter while
 * an unpair is already in-flight or done.
 */
static atomic_t fired       = ATOMIC_INIT(0);

/* The boot window is open by static init so we can't miss the very
 * first kscan press even if kscan starts before our SYS_INIT. SYS_INIT
 * only schedules the timer that closes it.
 */
static atomic_t window_open = ATOMIC_INIT(1);

static void schedule_unpair(const char *reason)
{
    if (!atomic_cas(&fired, 0, 1)) {
        return;
    }
    LOG_WRN("%s: combo (pos %d + pos %d) detected, scheduling unpair",
            reason, POS_A, POS_B);
}

static void do_unpair_work(struct k_work *w)
{
    ARG_UNUSED(w);
    LOG_WRN("Bond clear: wiping all stored BLE bonds");
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

/* Panic-hold delayed work: armed when both trigger keys go down outside
 * the boot window, cancelled the moment either key releases. If it
 * fires, the combo was held continuously for HOLD_MS.
 */
static void panic_hold_work(struct k_work *w)
{
    ARG_UNUSED(w);
    /* Re-check live state; a release that races with the timer expiry
     * should not trigger the unpair.
     */
    if (!atomic_get(&pos_a_down) || !atomic_get(&pos_b_down)) {
        LOG_DBG("Panic hold timer fired but combo no longer held");
        return;
    }
    schedule_unpair("Panic hold");
    k_work_schedule(&unpair_work, K_MSEC(250));
}
static K_WORK_DELAYABLE_DEFINE(panic_work, panic_hold_work);

static void close_window_work(struct k_work *w)
{
    ARG_UNUSED(w);
    atomic_set(&window_open, 0);
    LOG_INF("Boot bondclear window closed; panic hold remains armed "
            "(hold %d ms to trigger)", HOLD_MS);
}
static K_WORK_DELAYABLE_DEFINE(close_window, close_window_work);

static int position_listener(const zmk_event_t *eh)
{
    /* Once we've scheduled an unpair, ignore further events. */
    if (atomic_get(&fired)) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    const struct zmk_position_state_changed *ev =
        as_zmk_position_state_changed(eh);
    if (ev == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    /* Update press state for the two trigger keys. Any other position
     * is irrelevant - we explicitly do NOT cancel the panic timer on
     * an unrelated press, so the user typing while the host is dead
     * doesn't reset the hold-to-recover timer.
     */
    bool changed = false;
    if (ev->position == POS_A) {
        atomic_set(&pos_a_down, ev->state ? 1 : 0);
        changed = true;
    } else if (ev->position == POS_B) {
        atomic_set(&pos_b_down, ev->state ? 1 : 0);
        changed = true;
    }
    if (!changed) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    bool both_down = atomic_get(&pos_a_down) && atomic_get(&pos_b_down);

    /* Boot window: any simultaneous press triggers immediately. */
    if (atomic_get(&window_open) && both_down) {
        schedule_unpair("Boot bondclear");
        atomic_set(&window_open, 0);
        k_work_cancel_delayable(&close_window);
        k_work_cancel_delayable(&panic_work);
        k_work_schedule(&unpair_work, K_MSEC(250));
        return ZMK_EV_EVENT_BUBBLE;
    }

    /* Outside the boot window: arm/disarm the panic-hold timer. */
    if (HOLD_MS > 0) {
        if (both_down) {
            /* Combo just achieved - start the hold timer if not running. */
            k_work_schedule(&panic_work, K_MSEC(HOLD_MS));
            LOG_DBG("Panic hold armed (release either key to cancel)");
        } else {
            /* Either key released - cancel any pending fire. */
            k_work_cancel_delayable(&panic_work);
        }
    }

    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(peripheral_boot_bondclear, position_listener);
ZMK_SUBSCRIPTION(peripheral_boot_bondclear, zmk_position_state_changed);

static int peripheral_boot_bondclear_init(void)
{
    k_work_schedule(&close_window, K_MSEC(WINDOW_MS));
    LOG_INF("Bondclear armed: boot window %d ms, panic hold %d ms, "
            "combo pos %d + pos %d",
            WINDOW_MS, HOLD_MS, POS_A, POS_B);
    return 0;
}

SYS_INIT(peripheral_boot_bondclear_init, APPLICATION,
         CONFIG_APPLICATION_INIT_PRIORITY);
