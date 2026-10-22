"""Exercise actual patched ZMK proxy/listener code, including partial input failure."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_trackpad_frames import ROOT, STUB


EXTRA = r"""
#include <trackpad_frames.h>
#define LOG_MODULE_DECLARE(...)
#define LOG_DBG(...)
#define CONFIG_ZMK_INPUT_SPLIT_INIT_PRIORITY 90
#define CONFIG_ZMK_POINTING_SMOOTH_SCROLLING 0
#define ZMK_INPUT_PROC_CONTINUE 0
#define ZMK_INPUT_PROC_STOP 1
#define ZMK_HID_MOUSE_NUM_BUTTONS 5
#define INPUT_EV_ABS 3
#define INPUT_REL_WHEEL 8
#define INPUT_REL_HWHEEL 6
#define INPUT_BTN_1 (INPUT_BTN_0 + 1)
#define INPUT_BTN_2 (INPUT_BTN_0 + 2)
#define INPUT_BTN_3 (INPUT_BTN_0 + 3)
#define INPUT_BTN_4 (INPUT_BTN_0 + 4)
#define K_FOREVER -1
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define DT_INST_FOREACH_STATUS_OKAY(fn) fn(0)
#define DT_INST_REG_ADDR(n) 1
#define DT_DRV_INST(n) n
#define DEVICE_DT_GET(n) (&proxy_device)
#define DEVICE_DT_INST_DEFINE(...)
struct device { int unused; };
static const struct device proxy_device;
enum {
    INPUT_LISTENER_XY_DATA_MODE_NONE,
    INPUT_LISTENER_XY_DATA_MODE_REL,
};
struct input_listener_xy_data {
    int mode;
    struct { int16_t value; } x, y;
};
struct input_listener_config { int unused; };
struct input_listener_data {
    struct {
        struct input_listener_xy_data data, wheel_data;
        uint8_t button_set, button_clear;
    } mouse;
};
static int filter_with_input_config(const struct input_listener_config *c,
                                    struct input_listener_data *d, struct input_event *e) { return 0; }
static int hid_x, hid_y, sent_x, sent_y, reports;
static uint8_t hid_buttons;
static void zmk_hid_mouse_movement_set(int x, int y) { hid_x = x; hid_y = y; }
static void zmk_hid_mouse_scroll_set(int x, int y) {}
static void zmk_hid_mouse_button_press(int button) { hid_buttons |= BIT(button); }
static void zmk_hid_mouse_button_release(int button) { hid_buttons &= ~BIT(button); }
static void zmk_endpoints_send_mouse_report(void) {
    reports++; sent_x = hid_x; sent_y = hid_y;
}
static int input_report(const struct device *, uint8_t, uint16_t, int32_t, bool, int);
static int input_report_key(const struct device *d, int code, int value, bool sync, int timeout) {
    return input_report(d, INPUT_EV_KEY, code, value, sync, timeout);
}
static int input_report_rel(const struct device *d, int code, int value, bool sync, int timeout) {
    return input_report(d, INPUT_EV_REL, code, value, sync, timeout);
}
#define BT_GATT_ITER_STOP 0
#define BT_GATT_ITER_CONTINUE 1
#define ZMK_SPLIT_TRANSPORT_PERIPHERAL_EVENT_TYPE_INPUT_EVENT 1
struct bt_conn { int unused; };
struct bt_gatt_subscribe_params { uint16_t value_handle; };
struct peripheral_input_slot {
    struct bt_conn *conn;
    struct bt_gatt_subscribe_params sub;
    uint8_t reg;
    struct trackpad_receiver frame_receiver;
};
static struct peripheral_input_slot peripheral_input_slots[1];
struct zmk_split_input_event_payload {
    uint8_t type;
    uint16_t code;
    uint32_t value;
    uint8_t sync;
} __packed;
struct peripheral_event_wrapper {
    uint8_t source;
    struct {
        uint8_t type;
        struct { struct { uint8_t reg, sync, type; uint16_t code; uint32_t value; } input_event; } data;
    } event;
};
K_MSGQ_DEFINE(peripheral_event_msgq, sizeof(struct peripheral_event_wrapper), 32, 4);
static struct k_work peripheral_event_work;
static int k_work_submit(struct k_work *work) { return 0; }
static int peripheral_slot_index_for_conn(struct bt_conn *conn) { return 0; }
"""

HARNESS = r"""
#include "proxy.c"
#include "listener.c"
#include "notify.c"
static struct input_listener_data listener_data;
static const struct input_listener_config listener_config;
static int calls, fail_call, reset_events;
static int accepted_frames;
int trackpad_receive_frame(uint8_t reg, struct trackpad_receiver *receiver,
                          const void *data, size_t length) {
    assert(reg == 1 && receiver == &peripheral_input_slots[0].frame_receiver);
    accepted_frames++;
    return 0;
}
static int input_report(const struct device *dev, uint8_t type, uint16_t code,
                         int32_t value, bool sync, int timeout) {
    assert(dev == &proxy_device && timeout == K_FOREVER);
    if (++calls == fail_call) { return -ENOMEM; }
    if (type == TRACKPAD_INPUT_RESET_TYPE) { reset_events++; }
    struct input_event event = {.dev=dev, .type=type, .code=code, .value=value, .sync=sync};
    input_handler(&listener_config, &listener_data, &event);
    return 0;
}
int main(void) {
    struct trackpad_wire_frame frame = {.x=20, .y=-20, .buttons=1};
    fail_call = 3; /* Accept button and X, then fail the final Y/sync. */
    assert(trackpad_deliver_frame(1, &frame) == -ENOMEM);
    assert(reports == 0 && proxy_inputs[0].buttons == 0 && proxy_inputs[0].needs_reset);
    fail_call = 0;
    assert(trackpad_deliver_frame(1, &frame) == 0);
    assert(reset_events == 1 && reports == 1 && sent_x == 20 && sent_y == -20);
    assert(hid_buttons == 1 && proxy_inputs[0].buttons == 1);
    frame.x = frame.y = frame.buttons = 0;
    assert(trackpad_deliver_frame(1, &frame) == 0);
    assert(hid_buttons == 0 && reports == 2);
    assert(trackpad_deliver_frame(1, &frame) == 0 && reports == 2);
    assert(trackpad_deliver_frame(99, &frame) == -ENODEV);
    struct bt_conn owner = {0}, stale = {0};
    struct peripheral_input_slot *slot = &peripheral_input_slots[0];
    slot->conn = &owner;
    slot->reg = 1;
    slot->sub.value_handle = 1;
    assert(peripheral_input_event_notify_cb(&stale, &slot->sub, &frame, sizeof(frame)) ==
           BT_GATT_ITER_CONTINUE);
    assert(accepted_frames == 0);
    peripheral_input_event_notify_cb(&owner, &slot->sub, &frame, sizeof(frame));
    assert(accepted_frames == 1);
    slot->conn = NULL;
    peripheral_input_event_notify_cb(&owner, &slot->sub, &frame, sizeof(frame));
    assert(accepted_frames == 1);
    struct zmk_split_input_event_payload legacy = {.type=INPUT_EV_REL, .code=INPUT_REL_X};
    peripheral_input_event_notify_cb(&stale, &slot->sub, &legacy, sizeof(legacy));
    assert(peripheral_event_msgq.count == 0);
    slot->conn = &owner;
    peripheral_input_event_notify_cb(&owner, &slot->sub, &legacy, sizeof(legacy));
    assert(peripheral_event_msgq.count == 1);
    assert(peripheral_input_event_notify_cb(&stale, &slot->sub, NULL, 0) == BT_GATT_ITER_CONTINUE);
    assert(slot->sub.value_handle == 1);
    assert(peripheral_input_event_notify_cb(&owner, &slot->sub, NULL, 0) == BT_GATT_ITER_STOP);
    assert(slot->sub.value_handle == 0);
    puts("Patched ZMK frame retry and listener reset checks passed");
    return 0;
}
"""


def function_source(source, name, declaration="static void"):
    start = source.index(declaration + " " + name + "(")
    first = source.index("{", start)
    depth = 1
    end = first + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


class TrackpadSplitTests(unittest.TestCase):
    def test_patched_proxy_and_listener(self):
        module = os.environ.get("ZMK_MODULE_DIR")
        self.assertTrue(module, "Set ZMK_MODULE_DIR to the ZMK checkout from config/west.yml")
        compiler = (
            shlex.split(os.environ["CC"], posix=os.name != "nt") if os.environ.get("CC")
            else ["cc"] if shutil.which("cc")
            else [sys.executable, "-m", "ziglang", "cc"]
        )
        with tempfile.TemporaryDirectory(prefix="zmk-split-tests-") as directory:
            temp = Path(directory)
            for name in (
                "src/pointing/input_split.c", "src/pointing/input_listener.c",
                "src/split/bluetooth/central.c", "src/split/bluetooth/service.c",
            ):
                target = temp / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(Path(module) / "app" / name, target)
            patch = subprocess.run(
                ["git", "--work-tree=" + str(temp), "apply",
                 str(ROOT / "trackpad" / "zmk-input-frames.patch")],
                cwd=temp, capture_output=True, text=True,
            )
            self.assertEqual(patch.returncode, 0, patch.stdout + patch.stderr)
            shutil.copyfile(temp / "src" / "pointing" / "input_split.c", temp / "proxy.c")
            listener = (temp / "src" / "pointing" / "input_listener.c").read_text()
            (temp / "listener.c").write_text("".join(
                function_source(listener, name) for name in (
                    "handle_rel_code", "handle_abs_code", "handle_key_code",
                    "clear_xy_data", "input_handler",
                )
            ), encoding="ascii")
            central = (temp / "src" / "split" / "bluetooth" / "central.c").read_text()
            (temp / "notify.c").write_text(function_source(
                central, "peripheral_input_event_notify_cb", "static uint8_t"
            ), encoding="ascii")
            (temp / "stub.h").write_text(STUB + EXTRA, encoding="ascii")
            (temp / "test.c").write_text(HARNESS, encoding="ascii")
            for name in (
                "zephyr/kernel.h", "zephyr/device.h", "zephyr/input/input.h",
                "zephyr/logging/log.h", "zephyr/sys/util.h",
                "zephyr/dt-bindings/input/input-event-codes.h", "drivers/input_processor.h",
            ):
                header = temp / name
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text("", encoding="ascii")
            exe = temp / ("split.exe" if os.name == "nt" else "split")
            build = subprocess.run(
                compiler + [
                    "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                    "-include", str(temp / "stub.h"), "-I", str(temp),
                    "-I", str(ROOT / "trackpad" / "include"),
                    "-DCONFIG_ZMK_SPLIT_ROLE_CENTRAL=1",
                    str(temp / "test.c"), "-o", str(exe),
                ], capture_output=True, text=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
