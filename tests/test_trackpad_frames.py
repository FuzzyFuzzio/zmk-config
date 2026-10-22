"""Host fault tests for the real complete-frame queue and wire protocol."""

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
#include <string.h>
#include <errno.h>
#include <stdio.h>
#define __packed __attribute__((packed))
#define BUILD_ASSERT(c, ...) _Static_assert(c, #c)
#define BIT(n) (1U << (n))
#define WRITE_BIT(v,n,b) ((v) = ((v) & ~BIT(n)) | ((b) ? BIT(n) : 0))
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define IS_ENABLED(c) c
#ifndef TEST_SPLIT_DEVICE_COUNT
#define TEST_SPLIT_DEVICE_COUNT 1
#endif
#define DT_NUM_INST_STATUS_OKAY(compat) TEST_SPLIT_DEVICE_COUNT
#define CONFIG_INPUT_LOG_LEVEL 0
#define LOG_MODULE_REGISTER(...)
static int errors, warnings;
#define LOG_ERR(...) (++errors)
#define LOG_WRN(...) (++warnings)
#define K_NO_WAIT 0
#define K_MSEC(n) (n)
#define K_THREAD_STACK_DEFINE(name,size) char name[size]
#define K_THREAD_STACK_SIZEOF(name) sizeof(name)
#define SYS_INIT(...)
#define INPUT_EV_KEY 1
#define INPUT_EV_REL 2
#define INPUT_BTN_0 0x110
#define INPUT_REL_X 0
#define INPUT_REL_Y 1
struct input_event { const struct device *dev; uint8_t type; uint16_t code; int32_t value; bool sync; };
struct k_work { void (*fn)(struct k_work *); };
struct k_work_delayable { struct k_work work; bool scheduled; int delay; };
struct k_work_q { int unused; };
struct k_spinlock { int unused; };
typedef int k_spinlock_key_t;
static int k_spin_lock(struct k_spinlock *lock) { return 0; }
static void k_spin_unlock(struct k_spinlock *lock, int key) {}
static int64_t now;
static int64_t k_uptime_get(void) { return now; }
static void k_work_init_delayable(struct k_work_delayable *w, void (*fn)(struct k_work *)) {
    w->work.fn = fn;
}
static void k_work_queue_start(struct k_work_q *q, char *stack, size_t size, int priority,
                               const void *config) {}
static int k_work_schedule_for_queue(struct k_work_q *q, struct k_work_delayable *w, int delay) {
    if (!w->scheduled) { w->scheduled = true; w->delay = delay; }
    return 0;
}
static int k_work_reschedule_for_queue(struct k_work_q *q, struct k_work_delayable *w, int delay) {
    w->scheduled = true;
    w->delay = delay;
    return 0;
}
struct k_msgq { uint8_t data[4096]; size_t size; int capacity, count, head; };
#define K_MSGQ_DEFINE(name,item_size,n,align) struct k_msgq name = {.size=item_size,.capacity=n}
static int k_msgq_put(struct k_msgq *q, const void *p, int timeout) {
    if (q->count == q->capacity) { return -ENOMSG; }
    memcpy(q->data + ((q->head + q->count) % q->capacity) * q->size, p, q->size);
    q->count++;
    return 0;
}
static int k_msgq_get(struct k_msgq *q, void *p, int timeout) {
    if (!q->count) { return -ENOMSG; }
    memcpy(p, q->data + q->head * q->size, q->size);
    q->head = (q->head + 1) % q->capacity;
    q->count--;
    return 0;
}
#define sys_cpu_to_le32(v) ((uint32_t)(v))
#define sys_le32_to_cpu(v) ((uint32_t)(v))
#define sys_cpu_to_le16(v) ((uint16_t)(v))
#define sys_le16_to_cpu(v) ((uint16_t)(v))
"""

HARNESS = r"""
#include "trackpad/src/trackpad_frames.c"

static struct trackpad_wire_frame delivered[128];
static int delivered_count, delivery_error, delivery_attempts;
static bool publish_while_delivering;
static void publish(int value, uint8_t buttons);
static int deliver(uint8_t reg, const struct trackpad_wire_frame *frame) {
    assert(reg == 1);
    delivery_attempts++;
    if (publish_while_delivering) {
        publish_while_delivering = false;
        publish(1, 0);
    }
    if (delivery_error) { return delivery_error; }
    assert(delivered_count < 128);
    delivered[delivered_count++] = *frame;
    return 0;
}
int trackpad_bt_send_frame(uint8_t reg, const struct trackpad_wire_frame *frame) {
    return deliver(reg, frame);
}
int trackpad_deliver_frame(uint8_t reg, const struct trackpad_wire_frame *frame) {
    return deliver(reg, frame);
}
static void reset(void) {
    frame_queue.count = frame_queue.head = 0;
    pending = have_current = stale_warned = false;
    memset(&frame_work, 0, sizeof(frame_work));
    retry_ms = delivered_count = delivery_error = errors = warnings = 0;
    delivery_attempts = 0;
    retry_at = 0;
    publish_while_delivering = false;
    now = 0;
    frame_init();
}
static void run(void) {
    frame_work.scheduled = false;
    frame_work_cb(&frame_work.work);
}
static void publish(int value, uint8_t buttons) {
    struct trackpad_wire_frame frame = {
        .x = value, .y = -value, .buttons = buttons, .version = TRACKPAD_FRAME_VERSION,
    };
    enqueue_frame(1, &frame);
}
static void test_capture(void) {
    reset();
    struct trackpad_frame_builder builder = {0};
    struct input_event e = {.type = INPUT_EV_KEY, .code = INPUT_BTN_0, .value = 1};
    assert(trackpad_capture_event(1, &builder, &e) == 0);
    e = (struct input_event){.type = INPUT_EV_REL, .code = INPUT_REL_X, .value = 200};
    assert(trackpad_capture_event(1, &builder, &e) == 0 && frame_queue.count == 0);
    e = (struct input_event){.type = INPUT_EV_REL, .code = INPUT_REL_Y, .value = -255, .sync = true};
    assert(trackpad_capture_event(1, &builder, &e) == 0 && frame_queue.count == 1);
    assert(builder.frame.x == 0 && builder.frame.y == 0 && builder.frame.buttons == 1);
    run();
    assert(delivered_count == 1 && delivered[0].x == 200 && delivered[0].y == -255);
    assert(delivered[0].buttons == 1 && delivered[0].sequence == 0);
    e = (struct input_event){.type = INPUT_EV_KEY, .code = INPUT_BTN_0, .sync = true};
    trackpad_capture_event(1, &builder, &e);
    run();
    assert(delivered[1].buttons == 0 && delivered[1].sequence == 1);
    e.type = 99;
    assert(trackpad_capture_event(1, &builder, &e) == -ENOTSUP && errors == 1);
}
static void test_wire(void) {
    reset();
    struct trackpad_receiver receiver = {0};
    struct trackpad_wire_frame wire = {
        .x = -255, .y = 255, .version = TRACKPAD_FRAME_VERSION, .sequence = UINT16_MAX,
    };
    assert(sizeof(wire) == 12);
    assert(trackpad_receive_frame(1, &receiver, &wire, sizeof(wire)) == 0);
    assert(trackpad_receive_frame(1, &receiver, &wire, sizeof(wire)) == 0);
    run();
    assert(delivered_count == 1);
    wire.sequence = 0;
    assert(trackpad_receive_frame(1, &receiver, &wire, sizeof(wire)) == 0);
    assert(warnings == 0);
    wire.sequence = 2;
    assert(trackpad_receive_frame(1, &receiver, &wire, sizeof(wire)) == 0);
    assert(warnings == 1);
    assert(trackpad_receive_frame(1, &receiver, NULL, 12) == -EINVAL);
    assert(trackpad_receive_frame(1, &receiver, &wire, 8) == -EINVAL);
    wire.version = 2;
    assert(trackpad_receive_frame(1, &receiver, &wire, sizeof(wire)) == -EINVAL);
    wire.version = TRACKPAD_FRAME_VERSION;
    wire.buttons = 0x80;
    assert(trackpad_receive_frame(1, &receiver, &wire, sizeof(wire)) == -EINVAL);
    wire.buttons = 0;
    wire.x = 256;
    assert(trackpad_receive_frame(1, &receiver, &wire, sizeof(wire)) == -ERANGE);
}
static void test_age_and_backpressure(void) {
    reset();
    publish(20, 1);
    now = 49;
    run();
    assert(delivered[0].x == 20);
    publish(30, 0);
    now += 50;
    run();
    assert(delivered[1].x == 0 && delivered[1].y == 0 && delivered[1].buttons == 0);
    assert(warnings == 1);
    reset();
    delivery_error = -ENODEV;
    publish(1, 0);
    run();
    assert(!have_current && frame_queue.count == 0 && errors == 1);
    delivery_error = 0;
    publish(2, 0);
    run();
    assert(delivered_count == 1 && delivered[0].x == 2);
    reset();
    delivery_error = -ENOTCONN;
    publish(12, 1);
    publish_while_delivering = true;
    run();
    assert(have_current && frame_work.delay == 5);
    run(); /* Zephyr rescheduling does not remove an already-submitted callback. */
    assert(delivery_attempts == 1);
    now = 4;
    run();
    assert(delivery_attempts == 1);
    now = 5;
    run();
    assert(delivery_attempts == 2 && frame_work.delay == 10);
    reset();
    delivery_error = -ENOTCONN;
    publish(12, 1);
    run();
    assert(have_current && frame_work.delay == 5 && delivered_count == 0);
    for (int i = 0; i < 10; i++) { now += frame_work.delay; run(); }
    assert(frame_work.delay == 250 && errors == 1);
    for (int i = 0; i < 40; i++) { publish(i, i == 39 ? 0 : 1); }
    assert(frame_queue.count == 32 && pending);
    assert(pending_frame.frame.buttons == 0 && errors == 2);
    /* New samples must not cancel recovery backoff. */
    assert(frame_work.delay == 250);
    now += 1000;
    delivery_error = 0;
    run();
    run();
    assert(!have_current && !pending && frame_queue.count == 0);
    assert(delivered_count == 1 && delivered[0].buttons == 0);
    for (int i = 0; i < delivered_count; i++) {
        assert(delivered[i].x == 0 && delivered[i].y == 0);
    }
    /* The old press/release history must not become a delayed phantom click. */
    assert(delivered[0].buttons == 0);
    reset();
    publish(10, 1);
    trackpad_release(1);
    run();
    assert(delivered_count == 2 && delivered[1].buttons == 0 && delivered[1].x == 0);
}
int main(void) {
    test_capture();
    test_wire();
    test_age_and_backpressure();
    puts("Complete-frame queue checks passed");
    return 0;
}
"""


class TrackpadFrameTests(unittest.TestCase):
    def test_frame_roles(self):
        if os.environ.get("CC"):
            compiler = shlex.split(os.environ["CC"], posix=os.name != "nt")
        elif shutil.which("cc"):
            compiler = ["cc"]
        else:
            compiler = [sys.executable, "-m", "ziglang", "cc"]
        with tempfile.TemporaryDirectory(prefix="zmk-frame-tests-") as directory:
            temp = Path(directory)
            (temp / "stub.h").write_text(STUB, encoding="ascii")
            (temp / "test.c").write_text(HARNESS, encoding="ascii")
            for name in (
                "kernel.h", "devicetree.h", "logging/log.h", "sys/byteorder.h", "sys/util.h",
                "input/input.h", "dt-bindings/input/input-event-codes.h",
            ):
                header = temp / "zephyr" / name
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text("", encoding="ascii")
            for central in (0, 1):
                with self.subTest(central=central):
                    exe = temp / ("frames.exe" if os.name == "nt" else "frames")
                    command = compiler + [
                            "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-parameter", "-Wno-unused-function",
                            "-include", str(temp / "stub.h"), "-I", str(temp),
                            "-I", str(ROOT), "-I", str(ROOT / "trackpad" / "include"),
                            f"-DCONFIG_ZMK_SPLIT_ROLE_CENTRAL={central}",
                            str(temp / "test.c"), "-o", str(exe),
                        ]
                    build = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            invalid = subprocess.run(
                command + ["-DTEST_SPLIT_DEVICE_COUNT=2"], capture_output=True, text=True,
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("DT_NUM_INST_STATUS_OKAY", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
