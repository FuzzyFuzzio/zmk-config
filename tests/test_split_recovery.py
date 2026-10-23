"""Execute the real split-recovery sources against host Bluetooth/workqueue stubs."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]

STUB = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define IS_ENABLED(x) x
#define ARG_UNUSED(x) (void)(x)
#define LOG_MODULE_REGISTER(...)
#define LOG_WRN(...)
#define LOG_INF(...)
#define LOG_DBG(...)
#define LOG_ERR(...)
#define CONFIG_DONGLE_BOND_AUTOHEAL_LOG_LEVEL 0
#define CONFIG_DONGLE_BOND_AUTOHEAL_COOLDOWN_MS 30000
#define CONFIG_DONGLE_BOND_AUTOHEAL_MAX_UNENCRYPTED_DISCONNECTS 3
#define CONFIG_PERIPHERAL_BOOT_BONDCLEAR_LOG_LEVEL 0
#define CONFIG_PERIPHERAL_BOOT_BONDCLEAR_WINDOW_MS 4000
#define CONFIG_PERIPHERAL_BOOT_BONDCLEAR_HOLD_MS 5000
#define CONFIG_PERIPHERAL_BOOT_BONDCLEAR_POS_A 0
#define CONFIG_PERIPHERAL_BOOT_BONDCLEAR_POS_B 24
#define CONFIG_APPLICATION_INIT_PRIORITY 50
#define APPLICATION 0
#define SYS_INIT(fn, level, priority)
#define K_NO_WAIT 0
#define K_FOREVER -1
#define K_MSEC(x) (x)
static int64_t now;
static int64_t k_uptime_get(void) { return now; }
typedef int atomic_t;
#define ATOMIC_INIT(x) (x)
static int atomic_get(atomic_t *a) { return *a; }
static void atomic_set(atomic_t *a, int value) { *a = value; }
static bool atomic_cas(atomic_t *a, int old, int value) {
    if (*a != old) { return false; }
    *a = value; return true;
}
struct k_mutex { bool locked; };
#define K_MUTEX_DEFINE(name) struct k_mutex name
static int k_mutex_lock(struct k_mutex *m, int timeout) {
    assert(!m->locked); m->locked = true; return 0;
}
static int k_mutex_unlock(struct k_mutex *m) {
    assert(m->locked); m->locked = false; return 0;
}
struct k_work { void (*fn)(struct k_work *); };
struct k_work_delayable { struct k_work work; int64_t delay; };
#define K_WORK_DEFINE(name, fn) struct k_work name = {fn}
#define K_WORK_DELAYABLE_DEFINE(name, fn) struct k_work_delayable name = {{fn}, -1}
static int k_work_submit(struct k_work *work) { return 1; }
static int k_work_schedule(struct k_work_delayable *work, int64_t delay) {
    if (work->delay >= 0) { return 0; }
    work->delay = delay; return 1;
}
static int k_work_reschedule(struct k_work_delayable *work, int64_t delay) {
    work->delay = delay; return 1;
}
static int k_work_cancel_delayable(struct k_work_delayable *work) {
    work->delay = -1; return 0;
}
typedef struct { uint8_t value; } bt_addr_le_t;
static const bt_addr_le_t any = {0};
#define BT_ADDR_LE_ANY (&any)
#define BT_ADDR_LE_STR_LEN 30
#define BT_ID_DEFAULT 0
#define BT_CONN_TYPE_LE 1
#define BT_CONN_ROLE_CENTRAL 0
#define BT_CONN_ROLE_PERIPHERAL 1
#define BT_HCI_ERR_REMOTE_USER_TERM_CONN 19
#define BT_HCI_ERR_TERM_DUE_TO_MIC_FAIL 61
#define BT_HCI_ERR_CONN_FAIL_TO_ESTAB 62
#define BT_SECURITY_L2 2
typedef int bt_security_t;
enum bt_security_err {
    BT_SECURITY_ERR_SUCCESS,
    BT_SECURITY_ERR_AUTH_FAIL,
    BT_SECURITY_ERR_PIN_OR_KEY_MISSING,
    BT_SECURITY_ERR_KEY_REJECTED,
    BT_SECURITY_ERR_UNSPECIFIED,
};
struct bt_conn { bt_addr_le_t addr; int role; };
struct bt_conn_info { int role; };
static struct bt_conn conns[] = {{{1}, 0}, {{2}, 0}};
static bool bt_addr_le_eq(const bt_addr_le_t *a, const bt_addr_le_t *b) {
    return a->value == b->value;
}
static void bt_addr_le_copy(bt_addr_le_t *a, const bt_addr_le_t *b) { *a = *b; }
static int bt_addr_le_to_str(const bt_addr_le_t *a, char *buf, size_t size) {
    return snprintf(buf, size, "%u", a->value);
}
static const bt_addr_le_t *bt_conn_get_dst(struct bt_conn *conn) { return &conn->addr; }
static int bt_conn_get_info(struct bt_conn *conn, struct bt_conn_info *info) {
    info->role = conn->role; return 0;
}
struct bt_conn_cb {
    void (*connected)(struct bt_conn *, uint8_t);
    void (*disconnected)(struct bt_conn *, uint8_t);
    void (*security_changed)(struct bt_conn *, bt_security_t, enum bt_security_err);
};
static void bt_conn_cb_register(struct bt_conn_cb *cb) {}
static int unpair_count, disconnect_count, stored_bonds;
static bool bluetooth_ready;
static bool bt_is_ready(void) { return bluetooth_ready; }
static int bt_unpair(int id, const bt_addr_le_t *addr) {
    unpair_count++; stored_bonds = 0; return 0;
}
static int bt_conn_disconnect(struct bt_conn *conn, int reason) {
    disconnect_count++; return 0;
}
static void bt_conn_foreach(int type, void (*cb)(struct bt_conn *, void *), void *data) {
    for (size_t i = 0; i < 2; i++) { cb(&conns[i], data); }
}
struct msgq { bt_addr_le_t values[4]; int count; bool full; };
#define K_MSGQ_DEFINE(name, size, count, align) struct msgq name
static int k_msgq_put(struct msgq *q, const void *value, int timeout) {
    if (q->full || q->count == 4) { return -1; }
    q->values[q->count++] = *(const bt_addr_le_t *)value; return 0;
}
static int k_msgq_get(struct msgq *q, void *value, int timeout) {
    if (!q->count) { return -1; }
    *(bt_addr_le_t *)value = q->values[--q->count]; return 0;
}
typedef struct { uint32_t position; bool state; } zmk_event_t;
struct zmk_position_state_changed { uint32_t position; bool state; };
static const struct zmk_position_state_changed *
as_zmk_position_state_changed(const zmk_event_t *ev) {
    return (const struct zmk_position_state_changed *)ev;
}
#define ZMK_EV_EVENT_BUBBLE 0
#define ZMK_LISTENER(...)
#define ZMK_SUBSCRIPTION(...)
static int (*settings_commit_hook)(void);
#define SETTINGS_STATIC_HANDLER_DEFINE(name, tree, get, set, commit, exp) \
    static void remember_##name(void) __attribute__((constructor)); \
    static void remember_##name(void) { settings_commit_hook = commit; }
"""

AUTOHEAL = r"""
#include "dongle_split_recovery/src/dongle_bond_autoheal.c"

static void reset(void) {
    memset(peers, 0, sizeof(peers));
    memset(&unpair_q, 0, sizeof(unpair_q));
    next_evict = unpair_count = 0; now = 1000;
    conns[0].role = BT_CONN_ROLE_CENTRAL;
}
static void test_security_paths(void) {
    reset();
    connected(&conns[0], 0);
    security_changed(&conns[0], BT_SECURITY_L2, BT_SECURITY_ERR_SUCCESS);
    disconnected(&conns[0], 19);
    assert(unpair_q.count == 0);
    connected(&conns[0], 0);
    security_changed(&conns[0], 1, BT_SECURITY_ERR_UNSPECIFIED);
    assert(unpair_q.count == 0);
    security_changed(&conns[0], 1, BT_SECURITY_ERR_AUTH_FAIL);
    assert(unpair_q.count == 1 && unpair_count == 0);
    unpair_work_handler(NULL);
    assert(unpair_count == 1);
    security_changed(&conns[0], 1, BT_SECURITY_ERR_PIN_OR_KEY_MISSING);
    assert(unpair_q.count == 0);
    now += COOLDOWN_MS;
    security_changed(&conns[0], 1, BT_SECURITY_ERR_KEY_REJECTED);
    assert(unpair_q.count == 1);
    reset();
    conns[0].role = BT_CONN_ROLE_PERIPHERAL;
    connected(&conns[0], 0);
    disconnected(&conns[0], BT_HCI_ERR_TERM_DUE_TO_MIC_FAIL);
    security_changed(&conns[0], 1, BT_SECURITY_ERR_AUTH_FAIL);
    assert(unpair_q.count == 0);
}
static void test_failed_enqueue(void) {
    reset();
    connected(&conns[0], 0);
    unpair_q.full = true;
    security_changed(&conns[0], 1, BT_SECURITY_ERR_AUTH_FAIL);
    assert(!peers[0].has_unpaired);
    unpair_q.full = false;
    security_changed(&conns[0], 1, BT_SECURITY_ERR_AUTH_FAIL);
    assert(unpair_q.count == 1 && peers[0].has_unpaired);
}
static void test_disconnect_count(void) {
    reset();
    connected(&conns[0], 0);
    disconnected(&conns[0], BT_HCI_ERR_CONN_FAIL_TO_ESTAB);
    assert(peers[0].unenc_disconnects == 0);
    for (int i = 0; i < MAX_UNENC_DISCONNECTS; i++) {
        disconnected(&conns[0], 19);
    }
    assert(unpair_q.count == 1);
    for (int i = 0; i < UINT8_MAX; i++) {
        disconnected(&conns[0], 19);
    }
    disconnected(&conns[0], 19);
    assert(peers[0].unenc_disconnects == UINT8_MAX);
    assert(unpair_q.count == 1);
    security_changed(&conns[0], BT_SECURITY_L2, BT_SECURITY_ERR_SUCCESS);
    assert(peers[0].unenc_disconnects == 0);
}
int main(void) {
    test_failed_enqueue();
    test_disconnect_count();
    test_security_paths();
    puts("Split recovery checks passed");
}
"""

PERIPHERAL = r"""
#include "dongle_split_recovery/src/peripheral_boot_bondclear.c"

static void key(int position, bool down) {
    zmk_event_t ev = {.position = position, .state = down};
    assert(position_listener(&ev) == ZMK_EV_EVENT_BUBBLE);
}
static void test_boot_readiness(void) {
    key(POS_A, true); key(POS_B, true);
    assert(fired && unpair_work.delay == 250);
    do_unpair_work(NULL);
    assert(unpair_count == 0 && unpair_work.delay == 250);
    bluetooth_ready = true;
#if CONFIG_SETTINGS
    do_unpair_work(NULL);
    assert(unpair_count == 0);
    /* Bond restoration occurs after SYS_INIT, in main's settings_load(). */
    stored_bonds = 2;
    assert(settings_commit_hook != NULL);
    settings_commit_hook();
#endif
    do_unpair_work(NULL);
    assert(unpair_count == 1 && stored_bonds == 0 && disconnect_count == 2);
    key(POS_A, false); key(POS_A, true);
    assert(unpair_count == 1);
}
static void test_panic_hold(void) {
    fired = pos_a_down = pos_b_down = 0;
    close_window_work(NULL);
    unpair_work.delay = panic_work.delay = -1;
    now = 10000;
    key(POS_A, true); key(POS_B, true);
    assert(panic_work.delay == HOLD_MS);
    key(99, true);
    assert(panic_work.delay == HOLD_MS);
    now += HOLD_MS;
    /* The old handler has started but has not checked its state yet.
     * Cancellation cannot stop a handler that is already running. */
    panic_work.delay = -1;
    key(POS_A, false);
    panic_hold_work(NULL);
    assert(!fired);
    key(POS_A, true);
    panic_hold_work(NULL);
    assert(!fired && unpair_work.delay == -1);
    now += HOLD_MS - 1;
    key(POS_B, true);
    panic_hold_work(NULL);
    assert(!fired);
    now++;
    panic_hold_work(NULL);
    assert(fired && unpair_work.delay == 250);
}
int main(void) {
    test_boot_readiness();
    test_panic_hold();
    puts("Split recovery checks passed");
}
"""

HEADERS = (
    "zephyr/logging/log.h", "zephyr/init.h", "zephyr/kernel.h",
    "zephyr/bluetooth/bluetooth.h", "zephyr/bluetooth/conn.h",
    "zephyr/bluetooth/hci.h", "zephyr/settings/settings.h",
    "zmk/event_manager.h", "zmk/events/position_state_changed.h",
)


class SplitRecoveryTests(unittest.TestCase):
    def test_runtime(self):
        if os.environ.get("CC"):
            compiler = shlex.split(os.environ["CC"], posix=os.name != "nt")
        elif shutil.which("cc"):
            compiler = ["cc"]
        else:
            compiler = [sys.executable, "-m", "ziglang", "cc"]
        with tempfile.TemporaryDirectory(prefix="zmk-recovery-tests-", dir=ROOT) as directory:
            scratch = Path(directory)
            stub = scratch / "stubs.h"
            stub.write_text(STUB, encoding="ascii")
            for name in HEADERS:
                header = scratch.joinpath(*name.split("/"))
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text("", encoding="ascii")
            for name, harness, settings in (
                ("autoheal", AUTOHEAL, 1),
                ("peripheral", PERIPHERAL, 1),
                ("peripheral-no-settings", PERIPHERAL, 0),
            ):
                with self.subTest(name=name):
                    source = scratch / (name + ".c")
                    source.write_text(harness, encoding="ascii")
                    executable = scratch / (name + (".exe" if os.name == "nt" else ""))
                    command = compiler + [
                        "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-function", "-Wno-unused-parameter", "-Wno-unused-variable",
                        "-include", str(stub), "-I", str(scratch), "-I", str(ROOT),
                        f"-DCONFIG_SETTINGS={settings}", str(source), "-o", str(executable),
                    ]
                    build = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
