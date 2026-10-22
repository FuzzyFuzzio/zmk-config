"""Host tests for the real battery-sync and drawing C sources.

Run with: python -m unittest discover -s tests -p test_battery_sync.py
Requires a GCC/Clang-compatible C compiler (CC), or the ziglang Python package.
Zephyr/Bluetooth calls are simulated; this does not replace a firmware build.
"""

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
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>

#define IS_ENABLED(x) x
#define CONFIG_KERNEL_INIT_PRIORITY_DEFAULT 50
#define CONFIG_ZMK_LOG_LEVEL 0
#define CONFIG_BT_MAX_CONN 6
#define CONTAINER_OF(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define POST_KERNEL 0
#define LOG_MODULE_REGISTER(...)
static int warnings, errors;
#define LOG_WRN(...) (++warnings)
#define LOG_ERR(...) (++errors)
#define LOG_DBG(...)
#define ZMK_BEHAVIOR_OPAQUE 0
#define BEHAVIOR_LOCALITY_GLOBAL 2
#define ZMK_POSITION_STATE_CHANGE_SOURCE_LOCAL 255
#define ZMK_EV_EVENT_BUBBLE 0
#define K_SECONDS(x) ((x) * 1000)
#define K_NO_WAIT 0

static int event_count, event_result;
static uint8_t event_level;
#define ZMK_EVENT_IMPL(name)
#define ZMK_EVENT_DECLARE(name) \
    static int raise_##name(struct name ev) { \
        event_count++; event_level = ev.level; return event_result; \
    }
typedef struct { bool connected; } zmk_event_t;
struct zmk_split_peripheral_status_changed { bool connected; };
static const struct zmk_split_peripheral_status_changed *
as_zmk_split_peripheral_status_changed(const zmk_event_t *ev) {
    return (const struct zmk_split_peripheral_status_changed *)ev;
}
#define ZMK_LISTENER(name, fn) static const void *name __attribute__((used)) = fn
#define ZMK_SUBSCRIPTION(...)

struct zmk_behavior_binding { const char *behavior_dev; uint32_t param1, param2; };
struct zmk_behavior_binding_event { int64_t timestamp; uint8_t source; };
struct behavior_driver_api {
    int locality;
    int (*binding_pressed)(struct zmk_behavior_binding *, struct zmk_behavior_binding_event);
    int (*binding_released)(struct zmk_behavior_binding *, struct zmk_behavior_binding_event);
};
#define BEHAVIOR_DT_INST_DEFINE(a,b,c,d,e,f,g,api) \
    static const void *used_api __attribute__((used)) = api
static uint8_t mirrored_level;
static int mirror_count, mirror_error;
static int zmk_split_central_invoke_behavior(uint8_t source, struct zmk_behavior_binding *binding,
                                           struct zmk_behavior_binding_event event, bool pressed) {
    assert(strcmp(binding->behavior_dev, "bat_sync") == 0);
    assert(event.source == ZMK_POSITION_STATE_CHANGE_SOURCE_LOCAL);
    assert(pressed);
    mirrored_level = binding->param1;
    mirror_count++;
    return mirror_error;
}

struct k_work { int unused; };
struct k_work_delayable { struct k_work work; void (*fn)(struct k_work *); int delay; };
#define K_WORK_DELAYABLE_DEFINE(name, fn) struct k_work_delayable name = {{0}, fn, -1}
static int k_work_reschedule(struct k_work_delayable *work, int delay) {
    work->delay = delay; return 0;
}
static int64_t k_uptime_get(void) { return 123; }
typedef int atomic_t;
static bool atomic_cas(atomic_t *value, int old, int next) {
    if (*value != old) { return false; }
    *value = next; return true;
}
static void atomic_clear(atomic_t *value) { *value = 0; }

#define BT_CONN_ROLE_CENTRAL 0
#define BT_CONN_ROLE_PERIPHERAL 1
#define BT_CONN_STATE_CONNECTED 1
#define BT_CONN_TYPE_LE 1
#define BT_ATT_ERR_ATTRIBUTE_NOT_FOUND 10
#define BT_ATT_FIRST_ATTRIBUTE_HANDLE 1
#define BT_ATT_LAST_ATTRIBUTE_HANDLE 65535
#define BT_GATT_ITER_STOP 0
#define BT_GATT_CHRC_READ 2
#define BT_GATT_PERM_READ_ENCRYPT 2
struct bt_uuid { int type; };
struct bt_uuid_128 { struct bt_uuid uuid; uint8_t value[16]; };
#define BT_UUID_128_ENCODE(...) 0
#define BT_UUID_INIT_128(...) {{0}, {0}}
#define BT_UUID_DECLARE_128(...) NULL
struct bt_conn { int index, role, state, refs; };
struct bt_conn_info { int role, state; };
static struct bt_conn conns[6];
struct bt_gatt_read_params {
    uint8_t (*func)(struct bt_conn *, uint8_t, struct bt_gatt_read_params *,
                    const void *, uint16_t);
    uint16_t handle_count;
    struct { uint16_t start_handle, end_handle; const struct bt_uuid *uuid; } by_uuid;
};
static struct bt_gatt_read_params *pending[6];
static int request_error, request_count;
static int bt_conn_get_info(struct bt_conn *conn, struct bt_conn_info *info) {
    info->role = conn->role; info->state = conn->state; return 0;
}
static uint8_t bt_conn_index(struct bt_conn *conn) { return conn->index; }
static const int *bt_conn_get_dst(struct bt_conn *conn) { return &conn->index; }
static int zmk_ble_put_peripheral_addr(const int *address) { return *address; }
static struct bt_conn *bt_conn_ref(struct bt_conn *conn) { conn->refs++; return conn; }
static void bt_conn_unref(struct bt_conn *conn) { assert(conn->refs > 0); conn->refs--; }
static void bt_conn_foreach(int type, void (*fn)(struct bt_conn *, void *), void *data) {
    for (int i = 0; i < 6; i++) {
        if (conns[i].state) { fn(&conns[i], data); }
    }
}
static int bt_gatt_read(struct bt_conn *conn, struct bt_gatt_read_params *params) {
    request_count++;
    assert(params->handle_count == 0);
    assert(params->by_uuid.start_handle == 1 && params->by_uuid.end_handle == 65535);
    assert(params->by_uuid.uuid != NULL);
    if (request_error) { return request_error; }
    assert(pending[conn->index] == NULL);
    pending[conn->index] = params;
    return 0;
}
struct bt_conn_cb {
    void (*connected)(struct bt_conn *, uint8_t);
    void (*disconnected)(struct bt_conn *, uint8_t);
};
#define BT_CONN_CB_DEFINE(name) struct bt_conn_cb name
struct bt_gatt_attr { int unused; };
static uint8_t local_battery;
static uint8_t zmk_battery_state_of_charge(void) { return local_battery; }
static ssize_t bt_gatt_attr_read(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                                void *buf, uint16_t len, uint16_t offset,
                                const void *value, uint16_t size) {
    if (offset > size) { return -1; }
    size -= offset;
    if (len < size) { size = len; }
    memcpy(buf, (const uint8_t *)value + offset, size);
    return size;
}
#define BT_GATT_PRIMARY_SERVICE(...) NULL
#define BT_GATT_CHARACTERISTIC(uuid, props, perms, read, write, data) read
#define BT_GATT_SERVICE_DEFINE(name, ...) \
    static const void *name[] __attribute__((used)) = {__VA_ARGS__}

typedef struct { int unused; } lv_obj_t;
typedef struct { int unused; } lv_img_dsc_t;
typedef struct { int unused; } lv_draw_img_dsc_t;
typedef struct { int unused; } lv_draw_rect_dsc_t;
typedef struct { int unused; } lv_draw_label_dsc_t;
typedef struct { int unused; } lv_draw_line_dsc_t;
typedef struct { int unused; } lv_font_t;
typedef int lv_color_t;
typedef int lv_text_align_t;
#define LV_TEXT_ALIGN_CENTER 0
#define LV_IMG_DECLARE(name) extern const lv_img_dsc_t name
struct zmk_endpoint_instance { int unused; };
static lv_color_t lv_color_black(void) { return 0; }
static lv_color_t lv_color_white(void) { return 1; }
const lv_font_t lv_font_montserrat_10 = {0};
const lv_img_dsc_t battery = {0}, battery_mask = {0}, bolt = {0};
static char drawn_text[32];
static int fill_width, bolt_count;
static void lv_draw_img_dsc_init(lv_draw_img_dsc_t *dsc) {}
static void lv_canvas_draw_img(lv_obj_t *obj, int x, int y, const lv_img_dsc_t *img,
                              const lv_draw_img_dsc_t *dsc) {
    if (img == &bolt) { bolt_count++; }
}
static void lv_canvas_draw_rect(lv_obj_t *obj, int x, int y, int w, int h,
                               const lv_draw_rect_dsc_t *dsc) { fill_width = w; }
static void lv_canvas_draw_text(lv_obj_t *obj, int x, int y, int w,
                               const lv_draw_label_dsc_t *dsc, const char *text) {
    assert(w == 62);
    snprintf(drawn_text, sizeof(drawn_text), "%s", text);
}
"""

HARNESS = r"""
#include "battery_sync/src/battery_sync.c"
#include "boards/shields/nice_view_battery/widgets/battery.c"

void init_rect_dsc(lv_draw_rect_dsc_t *dsc, lv_color_t color) {}
void init_label_dsc(lv_draw_label_dsc_t *dsc, lv_color_t color,
                    const lv_font_t *font, lv_text_align_t align) {
    assert(font == &lv_font_montserrat_10);
}

static void reset(void) {
    right_level = ZMK_BATTERY_SYNC_UNKNOWN;
    event_count = warnings = errors = event_result = 0;
    mirror_count = mirror_error = request_error = request_count = 0;
    bolt_count = 0;
    for (int i = 0; i < 6; i++) {
        conns[i] = (struct bt_conn){.index = i};
        pending[i] = NULL;
    }
#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    memset(reads, 0, sizeof(reads));
    right_conn = NULL;
#endif
}

#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
static void connect_half(int i) {
    conns[i].state = BT_CONN_STATE_CONNECTED;
    connected(&conns[i], 0);
}
static void complete(int i, uint8_t err, const void *value, uint16_t length) {
    struct bt_gatt_read_params *params = pending[i];
    assert(params != NULL);
    pending[i] = NULL;
    assert(params->func(&conns[i], err, params, value, length) == BT_GATT_ITER_STOP);
    assert(!reads[i].busy);
}
static void disconnect_half(int i) {
    conns[i].state = 0;
    disconnected(&conns[i], 19);
}
static void test_mode(int left_index, int right_index) {
    reset();
    connect_half(right_index);
    if (left_index >= 0) { connect_half(left_index); }
    poll_work_cb(NULL);
    assert(pending[right_index] != NULL);
    if (left_index >= 0) {
        complete(left_index, BT_ATT_ERR_ATTRIBUTE_NOT_FOUND, NULL, 0);
    }
    uint8_t level = 18;
    complete(right_index, 0, &level, 1);
    assert(zmk_battery_sync_get() == 18 && event_count == 1);
    sync_work_cb(NULL);
    assert(mirrored_level == 18 && mirror_count == (left_index >= 0 ? 2 : 1));
    assert(sync_work.delay == POLL_INTERVAL);
    poll_work_cb(NULL);
    assert(pending[right_index] != NULL);
    if (left_index >= 0) { assert(pending[left_index] == NULL); }
    level = 0;
    complete(right_index, 0, &level, 1);
    assert(zmk_battery_sync_get() == 0);
    poll_work_cb(NULL);
    level = 100;
    complete(right_index, 0, &level, 1);
    assert(zmk_battery_sync_get() == 100);
    disconnect_half(right_index);
    assert(zmk_battery_sync_get() == ZMK_BATTERY_SYNC_UNKNOWN);
    assert(conns[right_index].refs == 0);
    connect_half(right_index);
    poll_work_cb(NULL);
    complete(right_index, 0, &level, 1);
    assert(zmk_battery_sync_get() == 100);
    disconnect_half(right_index);
}

static void test_central_failures(void) {
    reset();
    connect_half(0);
    request_error = -12;
    poll_work_cb(NULL);
    assert(warnings == 1 && conns[0].refs == 0 && !reads[0].busy);
    assert(poll_work.delay == RETRY_DELAY);
    request_error = 0;
    poll_work_cb(NULL);
    poll_work_cb(NULL);
    assert(request_count == 2);
    uint8_t level = 45;
    complete(0, 0, &level, 1);
    poll_work_cb(NULL);
    complete(0, 5, NULL, 0);
    assert(zmk_battery_sync_get() == ZMK_BATTERY_SYNC_UNKNOWN);
    poll_work_cb(NULL);
    level = 101;
    complete(0, 0, &level, 1);
    assert(zmk_battery_sync_get() == ZMK_BATTERY_SYNC_UNKNOWN);
    poll_work_cb(NULL);
    complete(0, 0, &level, 0);
    poll_work_cb(NULL);
    complete(0, 0, NULL, 0);
    poll_work_cb(NULL);
    level = 75;
    disconnect_half(0);
    complete(0, 0, &level, 1);
    assert(zmk_battery_sync_get() == ZMK_BATTERY_SYNC_UNKNOWN);
    assert(conns[0].refs == 0);

    reset();
    conns[0].state = BT_CONN_STATE_CONNECTED;
    conns[0].role = BT_CONN_ROLE_PERIPHERAL;
    connected(&conns[0], 0);
    poll_work_cb(NULL);
    assert(request_count == 0);
    conns[0].role = BT_CONN_ROLE_CENTRAL;
    mirror_error = -5;
    sync_work_cb(NULL);
    assert(warnings == 1);
}
#endif

static void test_behavior(void) {
    reset();
    struct zmk_behavior_binding binding = {.param1 = 18};
    struct zmk_behavior_binding_event event = {0};
    assert(on_battery_sync_pressed(&binding, event) == 0);
    assert(zmk_battery_sync_get() == 18 && event_count == 1);
    on_battery_sync_pressed(&binding, event);
    assert(event_count == 1);
    binding.param1 = 256 + 18;
    assert(on_battery_sync_pressed(&binding, event) == -EINVAL);
    assert(zmk_battery_sync_get() == 18 && errors == 1);
    binding.param1 = ZMK_BATTERY_SYNC_UNKNOWN;
    on_battery_sync_pressed(&binding, event);
    assert(event_level == ZMK_BATTERY_SYNC_UNKNOWN);
    event_result = -5;
    binding.param1 = 25;
    on_battery_sync_pressed(&binding, event);
    assert(warnings == 1);
    assert(on_battery_sync_released(&binding, event) == 0);
#if !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    zmk_event_t status = {.connected = true};
    peripheral_status_listener(&status);
    assert(zmk_battery_sync_get() == 25);
    status.connected = false;
    peripheral_status_listener(&status);
    assert(zmk_battery_sync_get() == ZMK_BATTERY_SYNC_UNKNOWN);
#endif
}

static void test_drawing(void) {
    reset();
    lv_obj_t canvas = {0};
    struct status_state state = {.battery = 25, .right_battery = 18};
    draw_battery_status(&canvas, &state);
    assert(strcmp(drawn_text, "25 / 18") == 0);
    assert(fill_width == 54 * 25 / 100 && bolt_count == 0);
    state.battery = 100;
    state.right_battery = 100;
    state.charging = true;
    draw_battery_status(&canvas, &state);
    assert(strcmp(drawn_text, "100 / 100") == 0 && bolt_count == 1);
    state.battery = 0;
    state.right_battery = 0;
    draw_battery_status(&canvas, &state);
    assert(strcmp(drawn_text, "0 / 0") == 0 && fill_width == 0);
    state.right_battery = ZMK_BATTERY_SYNC_UNKNOWN;
    draw_battery_status(&canvas, &state);
    assert(strcmp(drawn_text, "0 / --") == 0);
}

int main(void) {
    test_behavior();
    test_drawing();
#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    test_mode(0, 1);
    test_mode(1, 0);
    test_mode(-1, 0);
    test_central_failures();
#elif IS_ENABLED(CONFIG_SHIELD_HILLSIDE_VIEW_RIGHT)
    reset();
    uint8_t value = 255;
    local_battery = 18;
    assert(read_battery(NULL, NULL, &value, 1, 0) == 1 && value == 18);
    assert(read_battery(NULL, NULL, &value, 1, 1) == 0);
    assert(read_battery(NULL, NULL, &value, 1, 2) < 0);
#endif
    puts("Battery sync and drawing checks passed");
    return 0;
}
"""

HEADERS = (
    "zephyr/device.h",
    "zephyr/kernel.h",
    "zephyr/logging/log.h",
    "zephyr/bluetooth/gatt.h",
    "zephyr/bluetooth/conn.h",
    "zephyr/sys/atomic.h",
    "drivers/behavior.h",
    "zmk/behavior.h",
    "zmk/ble.h",
    "zmk/battery.h",
    "zmk/endpoints.h",
    "zmk/event_manager.h",
    "zmk/split/central.h",
    "zmk/events/position_state_changed.h",
    "zmk/events/split_peripheral_status_changed.h",
    "lvgl.h",
)


class BatterySyncTests(unittest.TestCase):
    def test_firmware_roles(self):
        if os.environ.get("CC"):
            compiler = shlex.split(os.environ["CC"], posix=os.name != "nt")
        elif shutil.which("cc"):
            compiler = ["cc"]
        else:
            compiler = [sys.executable, "-m", "ziglang", "cc"]

        with tempfile.TemporaryDirectory(prefix="zmk-battery-tests-") as directory:
            temp = Path(directory)
            stub = temp / "stubs.h"
            stub.write_text(STUB, encoding="ascii")
            source = temp / "test.c"
            source.write_text(HARNESS, encoding="ascii")
            for name in HEADERS:
                header = temp.joinpath(*name.split("/"))
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text("", encoding="ascii")

            for role in ("central", "left", "right"):
                with self.subTest(role=role):
                    executable = temp / (role + (".exe" if os.name == "nt" else ""))
                    command = compiler + [
                        "-std=c11",
                        "-Wall",
                        "-Wextra",
                        "-Werror",
                        "-Wno-unused-parameter",
                        "-Wno-unused-function",
                        "-Wno-unused-variable",
                        "-include", str(stub),
                        "-I", str(temp),
                        "-I", str(ROOT),
                        "-I", str(ROOT / "battery_sync" / "include"),
                        "-DCONFIG_ZMK_SPLIT=1",
                        f"-DCONFIG_ZMK_SPLIT_ROLE_CENTRAL={int(role == 'central')}",
                        f"-DCONFIG_SHIELD_HILLSIDE_VIEW_RIGHT={int(role == 'right')}",
                        "-DCONFIG_NICE_VIEW_WIDGET_INVERTED=0",
                        str(source),
                        "-o", str(executable),
                    ]
                    build = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                    result = subprocess.run(
                        [str(executable)], capture_output=True, text=True
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
