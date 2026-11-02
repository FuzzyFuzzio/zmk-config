"""Compile and exercise the patched Cirque driver with simulated I/O.

Set CIRQUE_MODULE_DIR and ZMK_MODULE_DIR to the checkouts from config/west.yml.
Requires Git and a GCC/Clang-compatible CC, or the ziglang Python package.
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
#include <errno.h>
#include <string.h>
#include <stdio.h>

#define BIT(n) (1U << (n))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define WRITE_BIT(v, n, b) ((v) = ((v) & ~BIT(n)) | ((b) ? BIT(n) : 0))
#define CONTAINER_OF(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define TEST_BUS_i2c 1
#define TEST_BUS_spi 1
#define DT_ANY_INST_ON_BUS_STATUS_OKAY(bus) TEST_BUS_##bus
#define DT_INST_FOREACH_STATUS_OKAY(...)
#define CONFIG_INPUT_LOG_LEVEL 0
#define CONFIG_PM_DEVICE 1
#ifndef CONFIG_ZMK_TRACKPAD_IDLE_SLEEP
#define CONFIG_ZMK_TRACKPAD_IDLE_SLEEP 1
#endif
#define CONFIG_LOG 1
#define IS_ENABLED(x) x
#define LOG_MODULE_REGISTER(...)
#define LOG_HEXDUMP_DBG(...)
#define LOG_DBG(...)
#define LOG_INF(...)
static int errors, warnings;
#define LOG_ERR(...) (++errors)
#define LOG_WRN(...) (++warnings)
#define K_FOREVER -1
#define K_NO_WAIT 0
#define K_MSEC(n) (n)
#define GPIO_INPUT 0
#define GPIO_INT_EDGE_TO_ACTIVE 1
#define GPIO_INT_DISABLE 0
#define INPUT_BTN_0 0x110
#define INPUT_REL_X 0
#define INPUT_REL_Y 1
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define DEVICE_DT_GET(node) (&dev)
#define DT_FOREACH_STATUS_OKAY(compat, fn) fn(trackpad)
#define ZMK_EV_EVENT_BUBBLE 0
#define ZMK_LISTENER(...)
#define ZMK_SUBSCRIPTION(...)
enum zmk_activity_state { ZMK_ACTIVITY_ACTIVE, ZMK_ACTIVITY_IDLE, ZMK_ACTIVITY_SLEEP };
typedef struct zmk_activity_state_changed { enum zmk_activity_state state; } zmk_event_t;
static const struct zmk_activity_state_changed *
as_zmk_activity_state_changed(const zmk_event_t *event) { return event; }

struct device { const void *config; void *data; };
struct i2c_dt_spec { int unused; };
struct spi_dt_spec { int unused; };
static bool bus_ready = true, gpio_ready = true;
static bool device_is_ready(const struct device *dev) { return gpio_ready; }
static bool i2c_is_ready_dt(const struct i2c_dt_spec *bus) { return bus_ready; }
static bool spi_is_ready_dt(const struct spi_dt_spec *bus) { return bus_ready; }
struct spi_buf { void *buf; size_t len; };
struct spi_buf_set { const struct spi_buf *buffers; size_t count; };
static int spi_error;
static bool spi_bad_filler;
static int spi_transceive_dt(const struct spi_dt_spec *bus, const struct spi_buf_set *tx,
                             const struct spi_buf_set *rx) {
    if (spi_error) { return spi_error; }
    for (size_t i = 0; i < rx->count; i++) {
        memset(rx->buffers[i].buf, spi_bad_filler ? 0 : 0xfb, rx->buffers[i].len);
    }
    return 0;
}
static uint8_t i2c_registers[32], i2c_read_address;
static int i2c_writes, i2c_reads, i2c_bursts, i2c_write_error, i2c_read_error;
static int i2c_write_dt(const struct i2c_dt_spec *bus, const uint8_t *buf, size_t len) {
    i2c_writes++;
    assert(len == 1 && (buf[0] & 0xe0) == 0xa0);
    if (i2c_write_error) { return i2c_write_error; }
    /* Only a completed write (with STOP) commits the Current Read Address. */
    i2c_read_address = buf[0] & 0x1f;
    return 0;
}
static int i2c_read_dt(const struct i2c_dt_spec *bus, uint8_t *buf, size_t len) {
    i2c_reads++;
    if (i2c_read_error) { return i2c_read_error; }
    memcpy(buf, i2c_registers + i2c_read_address, len);
    return 0;
}
static int i2c_burst_read_dt(const struct i2c_dt_spec *bus, uint8_t reg,
                           uint8_t *buf, size_t len) {
    i2c_bursts++;
    /* A repeated START does not implement the documented STOP-delimited read. */
    return i2c_read_dt(bus, buf, len);
}
static int i2c_reg_write_byte_dt(const struct i2c_dt_spec *bus, uint8_t reg, uint8_t val) {
    return 0;
}
struct gpio_dt_spec { const struct device *port; int pin; };
struct gpio_callback { int unused; };
struct k_work { void (*fn)(struct k_work *); };
struct k_work_delayable { struct k_work work; int pending; };
struct k_work_q { int unused; };
struct k_work_sync { int unused; };
struct k_mutex { int unused; };
#define K_THREAD_STACK_MEMBER(name, size) char name[size]
#define K_THREAD_STACK_SIZEOF(stack) sizeof(stack)
static int64_t now_ms;
static int cancellations, worker_starts, gpio_error, callback_error;
static bool irq_enabled, work_initialized, own_worker;
static void k_mutex_init(struct k_mutex *lock) {}
static void k_mutex_lock(struct k_mutex *lock, int timeout) {}
static void k_mutex_unlock(struct k_mutex *lock) {}
static void *k_current_get(void) { return own_worker ? (void *)2 : (void *)1; }
static void *k_work_queue_thread_get(struct k_work_q *q) { return (void *)2; }
static void k_work_queue_start(struct k_work_q *q, char *stack, size_t size,
                               int priority, const void *config) { worker_starts++; }
typedef int atomic_t;
static int atomic_get(const atomic_t *v) { return *v; }
static void atomic_set(atomic_t *v, int n) { *v = n; }
static void atomic_clear(atomic_t *v) { *v = 0; }
static int scheduled_delay, schedules, reschedules, ready_pin, interrupt_error, schedule_error;
static struct k_work_delayable *k_work_delayable_from_work(struct k_work *w) {
    return CONTAINER_OF(w, struct k_work_delayable, work);
}
static void k_work_init_delayable(struct k_work_delayable *w, void (*fn)(struct k_work *)) {
    w->work.fn = fn;
    work_initialized = true;
}
static int k_work_schedule(struct k_work_delayable *w, int delay) {
    schedules++;
    if (!w->pending) { w->pending = 1; scheduled_delay = delay; }
    return 1;
}
static int k_work_reschedule(struct k_work_delayable *w, int delay) {
    if (schedule_error) { return schedule_error; }
    reschedules++; w->pending = 1; scheduled_delay = delay; return 1;
}
static int k_work_cancel_delayable(struct k_work_delayable *w) {
    w->pending = 0; return 0;
}
static int k_work_schedule_for_queue(struct k_work_q *q, struct k_work_delayable *w, int delay) {
    return k_work_schedule(w, delay);
}
static int k_work_reschedule_for_queue(struct k_work_q *q, struct k_work_delayable *w, int delay) {
    return k_work_reschedule(w, delay);
}
static bool k_work_cancel_delayable_sync(struct k_work_delayable *w, struct k_work_sync *sync) {
    assert(!own_worker && !irq_enabled);
    cancellations++;
    k_work_cancel_delayable(w);
    return true;
}
static void k_msleep(int n) { now_ms += n; }
static void k_usleep(int n) {}
static int gpio_pin_get_dt(const struct gpio_dt_spec *s) { return ready_pin; }
static int gpio_pin_interrupt_configure_dt(const struct gpio_dt_spec *s, int mode) {
    if (!interrupt_error) { irq_enabled = mode == GPIO_INT_EDGE_TO_ACTIVE; }
    return interrupt_error;
}
static int gpio_pin_configure_dt(const struct gpio_dt_spec *s, int mode) { return gpio_error; }
static void gpio_init_callback(struct gpio_callback *cb,
                              void (*fn)(const struct device *, struct gpio_callback *, uint32_t),
                              uint32_t pins) {}
static int gpio_add_callback(const struct device *d, struct gpio_callback *cb) {
    assert(work_initialized && !irq_enabled);
    return callback_error;
}
enum pm_device_action { PM_DEVICE_ACTION_SUSPEND, PM_DEVICE_ACTION_RESUME };

static int rel_values[2], rel_reports, key_reports, input_delay_ms;
static int64_t k_uptime_get(void) { return now_ms; }
#ifdef TEST_ZMK_ACTIVITY
struct input_event { int unused; };
static void activity_input_listener(struct input_event *ev);
#endif
static int input_report_rel(const struct device *d, int code, int value, bool sync, int timeout) {
    assert(sync == (code == INPUT_REL_Y));
    now_ms += input_delay_ms;
    rel_values[code] = value; rel_reports++; return 0;
}
static int input_report_key(const struct device *d, int code, int value, bool sync, int timeout) {
    key_reports++; return 0;
}
"""

ACTIVITY_STUB = r"""
#define CONFIG_ZMK_POINTING 1
#define CONFIG_ZMK_SLEEP 1
#define CONFIG_USB_DEVICE_STACK 0
#define CONFIG_ZMK_IDLE_TIMEOUT 100
#define CONFIG_ZMK_IDLE_SLEEP_TIMEOUT 200
#define CONFIG_ZMK_LOG_LEVEL 0
#define LOG_MODULE_DECLARE(...)
#define SYS_INIT(...)
#define INPUT_CALLBACK_DEFINE(...)
#define K_SECONDS(n) ((n) * 1000)
#define K_WORK_DEFINE(name, callback) struct k_work name = {.fn = callback}
#define K_TIMER_DEFINE(name, ...) int name
struct k_timer { int unused; };
static void k_timer_start(int *timer, int delay, int period) {}
static struct k_work *activity_note_submitted;
static int k_work_submit(struct k_work *work) {
    activity_note_submitted = work;
    return 1;
}
"""

HARNESS = r"""
#include "input_pinnacle.c"
static const struct device dev;
#if IS_ENABLED(CONFIG_ZMK_TRACKPAD_IDLE_SLEEP)
#include "trackpad_idle.c"
#endif

static struct pinnacle_data data;
static uint8_t packet[3], status;
static int status_error, packet_error, ack_error, acks, reads, race_edge;
static uint8_t feed_cfg2;
static uint8_t registers[32], era[512];
static int fail_read_addr = -1, fail_write_addr = -1, era_busy, cal_busy, readback_bad;
static bool ignore_sleep_writes, packet_on_wake, fail_sleep_verify, wake_during_sleep_write;
static bool sensor_sleeping, ignore_feed_writes;
static int sensor_resets, calibrations;
static int read_reg(const struct device *dev, uint8_t addr, uint8_t *buf, uint8_t len) {
    reads++;
    if (addr == fail_read_addr) { return -EIO; }
    if (addr == PINNACLE_STATUS1) {
        if (status_error) { return status_error; }
        buf[0] = status;
    } else if (addr == PINNACLE_2_2_PACKET0) {
        if (packet_error) { return packet_error; }
        memcpy(buf, packet, len);
    } else if (addr == PINNACLE_REG_ERA_CONTROL && era_busy) {
        buf[0] = 1;
    } else if (addr == PINNACLE_CAL_CFG && cal_busy) {
        buf[0] = 1;
    } else if (addr == PINNACLE_REG_ERA_VALUE) {
        uint16_t address = ((uint16_t)registers[PINNACLE_REG_ERA_HIGH_BYTE] << 8) |
                           registers[PINNACLE_REG_ERA_LOW_BYTE];
        assert(address < sizeof(era));
        buf[0] = era[address];
    } else {
        memcpy(buf, registers + addr, len);
        if (readback_bad && addr == PINNACLE_Z_IDLE) { buf[0] ^= 1; }
    }
    return 0;
}
static int write_reg(const struct device *dev, uint8_t addr, uint8_t val) {
    if (addr == fail_write_addr) { return -EIO; }
    if (addr == PINNACLE_SYS_CFG && !(val & PINNACLE_SYS_CFG_RESET) && ignore_sleep_writes) {
        return 0;
    }
    if (addr == PINNACLE_FEED_CFG1 && ignore_feed_writes) {
        return 0;
    }
    registers[addr] = val;
    if (addr == PINNACLE_SYS_CFG) {
        if (val & PINNACLE_SYS_CFG_EN_SLEEP) {
            sensor_sleeping = true;
        }
    }
    if (addr == PINNACLE_SYS_CFG && fail_sleep_verify) {
        fail_read_addr = PINNACLE_SYS_CFG;
    }
#if IS_ENABLED(CONFIG_ZMK_TRACKPAD_IDLE_SLEEP)
    if (addr == PINNACLE_SYS_CFG && (val & PINNACLE_SYS_CFG_EN_SLEEP) &&
        wake_during_sleep_write) {
        wake_during_sleep_write = false;
        assert(pinnacle_request_sleep(dev, false) == 0);
    }
#endif
    if (addr == PINNACLE_SYS_CFG && (val & PINNACLE_SYS_CFG_RESET)) {
        sensor_resets++;
        sensor_sleeping = false;
        memset(registers, 0, sizeof(registers));
        status = PINNACLE_STATUS1_SW_CC;
    }
    if (addr == PINNACLE_CAL_CFG) {
        calibrations++;
        registers[addr] &= ~BIT(0);
        status |= PINNACLE_STATUS1_SW_CC;
    }
    if (addr == PINNACLE_REG_ERA_CONTROL) {
        uint16_t address = ((uint16_t)registers[PINNACLE_REG_ERA_HIGH_BYTE] << 8) |
                           registers[PINNACLE_REG_ERA_LOW_BYTE];
        assert(address < sizeof(era));
        if (val == PINNACLE_ERA_CONTROL_WRITE) {
            era[address] = registers[PINNACLE_REG_ERA_VALUE];
        }
        registers[addr] = 0;
    }
    if (addr == PINNACLE_FEED_CFG2) { feed_cfg2 = val; }
    if (addr == PINNACLE_STATUS1) {
        acks++;
        if (ack_error) { return ack_error; }
        status = 0;
        ready_pin = 0;
        if (race_edge) {
            ready_pin = 1;
            pinnacle_gpio_cb(NULL, &data.gpio_cb, 0);
        }
    }
    if (addr == PINNACLE_FEED_CFG1 && (val & PINNACLE_FEED_CFG1_EN_FEED) &&
        !sensor_sleeping && packet_on_wake) {
        packet_on_wake = false;
        status = PINNACLE_STATUS1_SW_DR;
        ready_pin = 1;
        packet[1] = 17;
    }
    return 0;
}
static bool test_bus_ready(const struct device *dev) { return bus_ready; }
static const struct pinnacle_config config = {
    .seq_read = read_reg, .write = write_reg, .sensitivity = PINNACLE_SENSITIVITY_1X,
    .is_ready = test_bus_ready,
};
static const struct device dev = {.config = &config, .data = &data};
static void reset(void) {
    memset(&data, 0, sizeof(data));
    data.dev = &dev;
    k_work_init_delayable(&data.work, pinnacle_work_cb);
    memset(packet, 0, sizeof(packet));
    packet[0] = BIT(3);
    status = PINNACLE_STATUS1_SW_DR;
    ready_pin = 1;
    status_error = packet_error = ack_error = errors = warnings = 0;
    rel_reports = key_reports = acks = reads = race_edge = interrupt_error = 0;
    schedules = reschedules = scheduled_delay = 0;
    schedule_error = sensor_resets = calibrations = 0;
    ignore_sleep_writes = packet_on_wake = false;
    fail_sleep_verify = wake_during_sleep_write = false;
    sensor_sleeping = ignore_feed_writes = false;
    memset(i2c_registers, 0, sizeof(i2c_registers));
    i2c_read_address = 0;
    i2c_writes = i2c_reads = i2c_bursts = i2c_write_error = i2c_read_error = 0;
    input_delay_ms = 0;
    now_ms = 0;
    memset(registers, 0, sizeof(registers));
    memset(era, 0, sizeof(era));
    registers[PINNACLE_FEED_CFG1] = pinnacle_feed_cfg1(&config);
    registers[PINNACLE_FEED_CFG2] = pinnacle_feed_cfg2(&config);
    fail_read_addr = fail_write_addr = -1;
    era_busy = cal_busy = readback_bad = 0;
    cancellations = worker_starts = gpio_error = callback_error = 0;
    bus_ready = gpio_ready = true;
    irq_enabled = own_worker = false;
    spi_error = 0;
    spi_bad_filler = false;
}
static void run_work(void) {
    data.work.pending = 0;
    pinnacle_work_cb(&data.work.work);
}
static void test_i2c_protocol(void) {
    reset();
    i2c_registers[PINNACLE_STATUS1] = PINNACLE_STATUS1_SW_DR;
    i2c_registers[PINNACLE_2_2_PACKET0] = BIT(3);
    i2c_registers[PINNACLE_2_2_PACKET0 + 1] = 200;
    i2c_registers[PINNACLE_2_2_PACKET0 + 2] = 17;
    uint8_t buf[3];
    assert(pinnacle_i2c_seq_read(&dev, PINNACLE_STATUS1, buf, 1) == 0);
    assert(i2c_writes == 1 && i2c_reads == 1 && i2c_bursts == 0);
    assert(buf[0] == PINNACLE_STATUS1_SW_DR);
    assert(pinnacle_i2c_seq_read(&dev, PINNACLE_2_2_PACKET0, buf, 3) == 0);
    assert(buf[0] == BIT(3) && buf[1] == 200 && buf[2] == 17);
    assert(i2c_writes == 2 && i2c_reads == 2 && i2c_bursts == 0);
    reset();
    i2c_write_error = -EBUSY;
    assert(pinnacle_i2c_seq_read(&dev, PINNACLE_STATUS1, buf, 1) == -EBUSY);
    assert(i2c_reads == 0);
    reset();
    i2c_read_error = -EIO;
    assert(pinnacle_i2c_seq_read(&dev, PINNACLE_STATUS1, buf, 1) == -EIO);
    assert(i2c_writes == 1 && i2c_reads == 1);
}
static void test_deltas(void) {
    /* Exhaust every byte and both independent sign flags, including signed zero. */
    for (int signs = 0; signs < 4; signs++) {
        for (int value = 0; value < 256; value++) {
            reset();
            packet[0] = BIT(3) | ((signs & 1) ? PINNACLE_PACKET0_X_SIGN : 0) |
                        ((signs & 2) ? PINNACLE_PACKET0_Y_SIGN : 0);
            packet[1] = value;
            packet[2] = 255 - value;
            assert(pinnacle_report_data(&dev) == 1);
            assert(rel_reports == 2 && acks == 1);
            assert(rel_values[0] == (value && (signs & 1) ? value - 256 : value));
            int y = 255 - value;
            assert(rel_values[1] == (y && (signs & 2) ? y - 256 : y));
        }
    }
}
static void test_errors(void) {
    for (int failure = 0; failure < 5; failure++) {
        reset();
        packet[1] = 25;
        switch (failure) {
        case 0: status_error = -EIO; break;
        case 1: status = 0xff; break;
        case 2: packet_error = -EIO; break;
        case 3: packet[0] = 0xff; break;
        case 4: ack_error = -EIO; break;
        }
        run_work();
        assert(errors > 0 && rel_reports == 0 && key_reports == 0);
        assert(data.work.pending && scheduled_delay == 5);
        /* Recover without a new GPIO edge, and report the pending sample once. */
        status_error = packet_error = ack_error = 0;
        status = PINNACLE_STATUS1_SW_DR;
        packet[0] = BIT(3);
        run_work();
        assert(rel_reports == 2 && rel_values[0] == 25 && !data.work.pending);
        assert(data.retry_ms == 0);
    }
    reset();
    packet_error = -EIO;
    for (int n = 0; n < 10; n++) { run_work(); }
    assert(scheduled_delay == 250 && rel_reports == 0);
    reset();
    ready_pin = -EIO;
    status = 0;
    run_work();
    assert(errors > 0 && scheduled_delay == 5);
}
static void test_headers_and_calibration(void) {
    for (int header = 0; header < 256; header++) {
        reset();
        packet[0] = header;
        packet[1] = 200;
        if ((header & 0xc8) == 0x08) {
            assert(pinnacle_report_data(&dev) == 1);
            assert(acks == 1 && rel_reports == 2 && errors == 0);
            assert(data.btn_cache == (header & 7));
            assert(key_reports == !!(header & 1) + !!(header & 2) + !!(header & 4));
            continue;
        }
        data.btn_cache = PINNACLE_PACKET0_BTN_PRIM;
        assert(pinnacle_report_data(&dev) == -EBADMSG);
        assert(errors == 1 && acks == 1 && ready_pin == 0);
        assert(rel_reports == 0 && key_reports == 0);
        assert(data.btn_cache == PINNACLE_PACKET0_BTN_PRIM);
        status = PINNACLE_STATUS1_SW_DR;
        packet[0] = BIT(3);
        assert(pinnacle_report_data(&dev) == 1);
        assert(rel_values[0] == 200 && key_reports == 1 && data.btn_cache == 0);
    }
    reset();
    packet[0] = 0;
    ack_error = -EIO;
    assert(pinnacle_report_data(&dev) == -EIO);
    assert(rel_reports == 0);
    reset();
    status = PINNACLE_STATUS1_SW_CC;
    run_work();
    assert(acks == 1 && ready_pin == 0 && !data.work.pending);
    assert(warnings == 1 && rel_reports == 0 && key_reports == 0);
    reset();
    status = PINNACLE_STATUS1_SW_CC;
    ack_error = -EIO;
    run_work();
    assert(data.work.pending && scheduled_delay == 5);
    ack_error = 0;
    run_work();
    assert(!data.work.pending && status == 0);
    reset();
    status |= PINNACLE_STATUS1_SW_CC;
    packet[1] = 12;
    run_work();
    assert(acks == 1 && rel_reports == 2 && rel_values[0] == 12);
}
static void test_edges_and_buttons(void) {
    reset();
    packet[1] = 1;
    input_delay_ms = 24;
    run_work();
    assert(warnings == 0 && rel_reports == 2);
    reset();
    packet[1] = 1;
    input_delay_ms = 25;
    run_work();
    assert(warnings == 1 && rel_reports == 2);
    reset();
    race_edge = 1;
    run_work();
    assert(reschedules == 1 && data.work.pending && scheduled_delay == 0);
    race_edge = 0;
    packet_error = -EIO;
    status = PINNACLE_STATUS1_SW_DR;
    run_work();
    assert(scheduled_delay == 5);
    reset();
    status = 0;
    ready_pin = 1;
    run_work();
    assert(data.work.pending && scheduled_delay == 5);
    reset();
    status = 0;
    ready_pin = 0;
    run_work();
    assert(!data.work.pending && rel_reports == 0);
    reset();
    packet[0] = BIT(3) | PINNACLE_PACKET0_BTN_PRIM;
    run_work();
    assert(key_reports == 1);
    status = PINNACLE_STATUS1_SW_DR;
    packet[0] = BIT(3);
    run_work();
    assert(key_reports == 2);
}
static void test_power_and_init(void) {
    reset();
    packet[1] = 1;
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_SUSPEND) == 0);
    assert(atomic_get(&data.suspended) && !data.work.pending);
    assert(cancellations == 1);
    run_work();
    pinnacle_gpio_cb(NULL, &data.gpio_cb, 0);
    assert(reads == 0 && !data.work.pending);
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_RESUME) == 0);
    assert(!atomic_get(&data.suspended) && data.work.pending && scheduled_delay == 0);
    run_work();
#if IS_ENABLED(CONFIG_ZMK_TRACKPAD_IDLE_SLEEP)
    assert(sensor_resets == 1 && calibrations == 1 && rel_reports == 0);
    packet[1] = 1;
    status = PINNACLE_STATUS1_SW_DR;
    run_work();
#endif
    assert(rel_reports == 2);
    reset();
    assert(pinnacle_init(&dev) == 0);
    assert(feed_cfg2 & PINNACLE_FEED_CFG2_DIS_GE);
    assert(feed_cfg2 & PINNACLE_FEED_CFG2_DIS_SCRL);
    assert(!(feed_cfg2 & (PINNACLE_FEED_CFG2_EN_IM | PINNACLE_FEED_CFG2_EN_BTN_SCRL)));
    assert(!(feed_cfg2 & PINNACLE_FEED_CFG2_DIS_TAP));
    assert(data.work.pending);
    reset();
    interrupt_error = -EIO;
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_SUSPEND) == -EIO);
    assert(!atomic_get(&data.suspended));
    reset();
    interrupt_error = -EIO;
    atomic_set(&data.suspended, 1);
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_RESUME) == -EIO);
    assert(atomic_get(&data.suspended) && !data.work.pending);
    assert(pinnacle_init(&dev) == -EIO);
}
static void test_faults_and_timeouts(void) {
    reset();
    status = 0xff;
    assert(pinnacle_wait(&dev, PINNACLE_STATUS1, PINNACLE_STATUS1_SW_CC,
                         PINNACLE_STATUS1_SW_CC, 500) == -EIO);
    assert(now_ms == 0 && errors == 1);
    reset();
    era_busy = 1;
    uint8_t value;
    assert(pinnacle_era_read(&dev, PINNACLE_ERA_REG_TRACKING_ADC_CONFIG, &value) == -ETIMEDOUT);
    assert(now_ms == 100);
    reset();
    cal_busy = 1;
    assert(pinnacle_force_recalibrate(&dev) == -ETIMEDOUT && now_ms == 500);
    reset();
    fail_read_addr = PINNACLE_CAL_CFG;
    assert(pinnacle_force_recalibrate(&dev) == -EIO && now_ms == 0);
    reset();
    fail_read_addr = PINNACLE_REG_ERA_CONTROL;
    assert(pinnacle_set_adc_tracking_sensitivity(&dev) == -EIO);
    reset();
    fail_write_addr = PINNACLE_REG_ERA_VALUE;
    assert(pinnacle_set_adc_tracking_sensitivity(&dev) == -EIO);
    for (int failure = 0; failure < 8; failure++) {
        reset();
        switch (failure) {
        case 0: bus_ready = false; break;
        case 1: gpio_ready = false; break;
        case 2: gpio_error = -EIO; break;
        case 3: callback_error = -EIO; break;
        case 4: fail_read_addr = PINNACLE_FW_ID; break;
        case 5: fail_write_addr = PINNACLE_FEED_CFG2; break;
        case 6: readback_bad = 1; break;
        case 7: fail_write_addr = PINNACLE_FEED_CFG1; break;
        }
        assert(pinnacle_init(&dev) < 0);
        assert(atomic_get(&data.suspended) && !data.work.pending);
    }
    reset();
    own_worker = true;
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_SUSPEND) == -EDEADLK);
    assert(!atomic_get(&data.suspended));
    reset();
    spi_error = -EBUSY;
    assert(pinnacle_spi_write(&dev, 0, 0) == -EBUSY);
    uint8_t spi_packet[3];
    assert(pinnacle_spi_seq_read(&dev, PINNACLE_2_2_PACKET0, spi_packet, 3) == -EBUSY);
    spi_error = 0;
    spi_bad_filler = true;
    assert(pinnacle_spi_write(&dev, 0, 0) == -EIO);
    spi_bad_filler = false;
    assert(pinnacle_spi_write(&dev, 0, 0) == 0);
    reset();
    assert(pinnacle_report_data(&dev) == 1 && rel_reports == 0 && key_reports == 0);
    reset();
    registers[PINNACLE_FEED_CFG1] = registers[PINNACLE_FEED_CFG2] = 0;
    data.btn_cache = PINNACLE_PACKET0_BTN_PRIM;
    status = PINNACLE_STATUS1_SW_CC;
    run_work();
    assert(registers[PINNACLE_FEED_CFG1] == pinnacle_feed_cfg1(&config));
    assert(registers[PINNACLE_FEED_CFG2] == pinnacle_feed_cfg2(&config));
    assert(registers[PINNACLE_CAL_CFG] == 0);
    assert(key_reports == 1 && rel_reports == 2 && data.btn_cache == 0);
}
#if IS_ENABLED(CONFIG_ZMK_TRACKPAD_IDLE_SLEEP)
static void activity(enum zmk_activity_state state) {
    zmk_event_t event = {.state = state};
    assert(trackpad_activity_changed(&event) == ZMK_EV_EVENT_BUBBLE);
}
static void test_idle_sleep(void) {
    reset();
    status = ready_pin = 0;
    assert(trackpad_activity_changed(NULL) == ZMK_EV_EVENT_BUBBLE);
    for (int n = 0; n < 20; n++) {
        int previous_reads = reads;
        activity(ZMK_ACTIVITY_IDLE);
        assert(reads == previous_reads && data.work.pending && scheduled_delay == 0);
        run_work();
        assert(registers[PINNACLE_SYS_CFG] == PINNACLE_SYS_CFG_EN_SLEEP);
        assert(data.sleep_enabled && !data.work.pending);
        assert(sensor_sleeping);
        activity(ZMK_ACTIVITY_ACTIVE);
        assert(reads > previous_reads && data.work.pending);
        run_work();
        assert(registers[PINNACLE_SYS_CFG] == 0);
        assert(registers[PINNACLE_FEED_CFG1] == pinnacle_feed_cfg1(&config));
        assert(registers[PINNACLE_FEED_CFG2] == pinnacle_feed_cfg2(&config));
        assert(!data.sleep_enabled && !data.work.pending);
        assert(!sensor_sleeping);
    }
    assert(sensor_resets == 20 && calibrations == 20 && worker_starts == 0);
    assert(rel_reports == 0 && key_reports == 0);

    /* A sample after reinitialization must not require another interrupt edge. */
    activity(ZMK_ACTIVITY_IDLE);
    run_work();
    packet_on_wake = true;
    activity(ZMK_ACTIVITY_ACTIVE);
    run_work();
    assert(rel_reports == 2 && rel_values[0] == 17 && !data.work.pending);

    /* A touch can leave idle through the normal input activity listener. */
    activity(ZMK_ACTIVITY_IDLE);
    run_work();
    status = PINNACLE_STATUS1_SW_DR;
    packet[1] = 3;
    pinnacle_gpio_cb(NULL, &data.gpio_cb, 0);
    run_work();
    assert(rel_values[0] == 3);
    activity(ZMK_ACTIVITY_ACTIVE);
    run_work();
    assert(!(registers[PINNACLE_SYS_CFG] & PINNACLE_SYS_CFG_EN_SLEEP));
    reset();
    status = ready_pin = 0;
    wake_during_sleep_write = true;
    activity(ZMK_ACTIVITY_IDLE);
    run_work();
    assert(data.sleep_enabled && data.work.pending && scheduled_delay == 0);
    run_work();
    assert(!data.sleep_enabled && !data.work.pending);
}
static void test_sleep_failures(void) {
    reset();
    status = ready_pin = 0;
    fail_sleep_verify = true;
    activity(ZMK_ACTIVITY_IDLE);
    run_work();
    assert(registers[PINNACLE_SYS_CFG] & PINNACLE_SYS_CFG_EN_SLEEP);
    assert(!data.sleep_enabled && !data.sleep_valid && data.work.pending);
    fail_sleep_verify = false;
    fail_read_addr = -1;
    activity(ZMK_ACTIVITY_ACTIVE);
    run_work();
    assert(registers[PINNACLE_SYS_CFG] == 0);
    assert(data.sleep_valid && !data.wake_needed && !data.work.pending && !sensor_sleeping);
    for (int waking = 0; waking < 2; waking++) {
        for (int failure = 0; failure < 4; failure++) {
            reset();
            status = ready_pin = 0;
            if (waking) {
                activity(ZMK_ACTIVITY_IDLE);
                run_work();
            }
            switch (failure) {
            case 0: fail_read_addr = PINNACLE_SYS_CFG; break;
            case 1: fail_write_addr = PINNACLE_SYS_CFG; break;
            case 2:
                ignore_sleep_writes = !waking;
                ignore_feed_writes = waking;
                break;
            case 3: registers[PINNACLE_SYS_CFG] = 0xff; break;
            }
            activity(waking ? ZMK_ACTIVITY_ACTIVE : ZMK_ACTIVITY_IDLE);
            for (int n = 0; n < 10; n++) { run_work(); }
            assert(errors > 0 && scheduled_delay == 250 && data.work.pending);
            assert(data.sleep_enabled == !!waking);
            fail_read_addr = fail_write_addr = -1;
            ignore_sleep_writes = ignore_feed_writes = false;
            registers[PINNACLE_SYS_CFG] = waking ? PINNACLE_SYS_CFG_EN_SLEEP : 0;
            run_work();
            assert(data.sleep_enabled == !waking && !data.work.pending);
        }
    }
    reset();
    status = ready_pin = 0;
    fail_write_addr = PINNACLE_SYS_CFG;
    activity(ZMK_ACTIVITY_IDLE);
    run_work();
    assert(scheduled_delay == 5);
    fail_write_addr = -1;
    activity(ZMK_ACTIVITY_ACTIVE);
    run_work();
    assert(!data.sleep_enabled && !data.work.pending);
    reset();
    schedule_error = -EBUSY;
    assert(pinnacle_request_sleep(&dev, true) == -EBUSY && errors == 1);
    activity(ZMK_ACTIVITY_IDLE);
    assert(errors == 3);
    reset();
    gpio_ready = false;
    activity(ZMK_ACTIVITY_IDLE);
    assert(errors == 1 && !data.work.pending);
}
static void test_partial_wake_reinitialization(void) {
    reset();
    status = ready_pin = 0;
    activity(ZMK_ACTIVITY_IDLE);
    run_work();
    assert(sensor_sleeping);
    fail_write_addr = PINNACLE_FEED_CFG1;
    packet_on_wake = true;
    activity(ZMK_ACTIVITY_ACTIVE);
    run_work();
    assert(!(registers[PINNACLE_SYS_CFG] & PINNACLE_SYS_CFG_EN_SLEEP));
    assert(!sensor_sleeping && !data.sleep_valid && data.wake_needed && data.wake_started);
    assert(errors > 0 && data.work.pending && scheduled_delay == 5 && rel_reports == 0);
    for (int n = 0; n < 10; n++) { run_work(); }
    assert(scheduled_delay == 250 && data.wake_started);
    fail_write_addr = -1;
    run_work();
    assert(!sensor_sleeping && data.sleep_valid && !data.wake_needed && !data.work.pending);
    assert(rel_reports == 2 && rel_values[0] == 17);
    assert(sensor_resets > 1 && calibrations == sensor_resets && worker_starts == 0);
}
static void test_wake_reinitialization_failures(void) {
    for (int failure = 0; failure < 7; failure++) {
        reset();
        status = ready_pin = 0;
        activity(ZMK_ACTIVITY_IDLE);
        run_work();
        switch (failure) {
        case 0: fail_read_addr = PINNACLE_FW_ID; break;
        case 1: status_error = -EIO; break;
        case 2: fail_write_addr = PINNACLE_FEED_CFG2; break;
        case 3: cal_busy = 1; break;
        case 4: readback_bad = 1; break;
        case 5: fail_write_addr = PINNACLE_REG_ERA_VALUE; break;
        case 6: fail_read_addr = PINNACLE_REG_ERA_CONTROL; break;
        }
        activity(ZMK_ACTIVITY_ACTIVE);
        run_work();
        assert(errors > 0 && data.wake_started && !data.sleep_valid);
        assert(data.work.pending && scheduled_delay == 5 && rel_reports == 0);
        fail_read_addr = fail_write_addr = -1;
        status_error = cal_busy = readback_bad = 0;
        run_work();
        assert(!data.sleep_enabled && data.sleep_valid && !data.wake_started);
        assert(!data.work.pending && registers[PINNACLE_SYS_CFG] == 0);
    }
    reset();
    status = ready_pin = 0;
    activity(ZMK_ACTIVITY_IDLE);
    run_work();
    data.btn_cache = PINNACLE_PACKET0_BTN_PRIM;
    activity(ZMK_ACTIVITY_ACTIVE);
    run_work();
    assert(key_reports == 1 && data.btn_cache == 0 && rel_reports == 2);
    assert(sensor_resets == 1 && calibrations == 1 && data.wake_report_pending);
    packet[1] = 9;
    status = PINNACLE_STATUS1_SW_DR;
    run_work();
    assert(rel_values[0] == 9 && !data.wake_report_pending);
}
static void test_sleep_suspend_and_boot(void) {
    reset();
    status = ready_pin = 0;
    activity(ZMK_ACTIVITY_IDLE);
    run_work();
    activity(ZMK_ACTIVITY_SLEEP);
    assert(!data.work.pending);
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_SUSPEND) == 0);
    int suspended_reads = reads;
    activity(ZMK_ACTIVITY_ACTIVE);
    run_work();
    assert(reads == suspended_reads && data.sleep_enabled);
    /* PM rollback must wake even if no ACTIVE event was delivered. */
    atomic_set(&data.sleep_requested, 1);
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_RESUME) == 0);
    fail_write_addr = PINNACLE_SYS_CFG;
    run_work();
    assert(data.work.pending && scheduled_delay == 5 && data.sleep_enabled);
    fail_write_addr = -1;
    packet_on_wake = true;
    run_work();
    assert(!data.sleep_enabled && rel_values[0] == 17);

    /* nRF52840 system-off wake reboots with the sensor potentially still powered. */
    activity(ZMK_ACTIVITY_IDLE);
    run_work();
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_SUSPEND) == 0);
    int previous_resets = sensor_resets, previous_calibrations = calibrations;
    memset(&data, 0, sizeof(data));
    assert(registers[PINNACLE_SYS_CFG] & PINNACLE_SYS_CFG_EN_SLEEP);
    assert(pinnacle_init(&dev) == 0);
    assert(sensor_resets == previous_resets + 1 && calibrations == previous_calibrations + 1);
    assert(!data.sleep_enabled && !atomic_get(&data.sleep_requested));
    assert(registers[PINNACLE_SYS_CFG] == 0 && irq_enabled && data.work.pending);
    packet[1] = 29;
    status = PINNACLE_STATUS1_SW_DR;
    ready_pin = 1;
    run_work();
    assert(rel_values[0] == 29 && !data.work.pending);

    reset();
    status = ready_pin = 0;
    run_work();
    assert(data.sleep_valid && !data.sleep_enabled);
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_SUSPEND) == 0);
    registers[PINNACLE_SYS_CFG] = PINNACLE_SYS_CFG_EN_SLEEP;
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_RESUME) == 0);
    run_work();
    assert(registers[PINNACLE_SYS_CFG] == 0);
    assert(data.sleep_valid && !data.wake_needed && !data.work.pending && !sensor_sleeping);
}
#endif
int main(void) {
    test_i2c_protocol();
    test_deltas();
    test_errors();
    test_headers_and_calibration();
    test_edges_and_buttons();
    test_power_and_init();
    test_faults_and_timeouts();
#if IS_ENABLED(CONFIG_ZMK_TRACKPAD_IDLE_SLEEP)
    test_idle_sleep();
    test_sleep_failures();
    test_partial_wake_reinitialization();
    test_wake_reinitialization_failures();
    test_sleep_suspend_and_boot();
#endif
    puts("Trackpad checks passed: decoding, recovery, edges, buttons, PM and init");
    return 0;
}
"""

ACTIVITY_HARNESS = r"""
static bool powered_off, fail_system_suspend;
static int raise_zmk_activity_state_changed(struct zmk_activity_state_changed event) {
    return trackpad_activity_changed(&event);
}
static int zmk_pm_suspend_devices(void) {
    int ret = pinnacle_pm_action(&dev, PM_DEVICE_ACTION_SUSPEND);
    return ret < 0 ? ret : fail_system_suspend ? -EIO : 0;
}
static void zmk_pm_resume_devices(void) {
    assert(pinnacle_pm_action(&dev, PM_DEVICE_ACTION_RESUME) == 0);
}
static void sys_poweroff(void) { powered_off = true; }
#include "activity.c"

static void reset_activity(void) {
    reset();
    status = ready_pin = 0;
    activity_state = ZMK_ACTIVITY_ACTIVE;
    activity_note_submitted = NULL;
    powered_off = fail_system_suspend = false;
    activity_init();
}
static void test_real_activity_wake(void) {
    reset_activity();
    now_ms = 100;
    activity_work_handler(NULL);
    assert(zmk_activity_get_state() == ZMK_ACTIVITY_ACTIVE && !data.work.pending);
    now_ms = 101;
    activity_work_handler(NULL);
    assert(zmk_activity_get_state() == ZMK_ACTIVITY_IDLE);
    run_work();
    assert(data.sleep_enabled);
    activity_event_listener(NULL);
    assert(zmk_activity_get_state() == ZMK_ACTIVITY_ACTIVE);
    run_work();
    assert(!data.sleep_enabled);

    now_ms += 101;
    activity_work_handler(NULL);
    run_work();
    packet[1] = 8;
    status = PINNACLE_STATUS1_SW_DR;
    run_work();
    struct input_event input = {0};
    activity_input_listener(&input);
    assert(activity_note_submitted);
    activity_note_submitted->fn(activity_note_submitted);
    run_work();
    assert(zmk_activity_get_state() == ZMK_ACTIVITY_ACTIVE && !data.sleep_enabled);

    now_ms += 101;
    activity_work_handler(NULL);
    run_work();
    assert(data.sleep_enabled);
    now_ms = activity_last_uptime + MAX_SLEEP_MS;
    activity_work_handler(NULL);
    assert(!powered_off && zmk_activity_get_state() == ZMK_ACTIVITY_IDLE);
    now_ms += 1;
    activity_work_handler(NULL);
    assert(powered_off && zmk_activity_get_state() == ZMK_ACTIVITY_SLEEP);
    assert(atomic_get(&data.suspended) && data.sleep_enabled && !data.work.pending);
    memset(&data, 0, sizeof(data));
    activity_state = ZMK_ACTIVITY_ACTIVE;
    assert(pinnacle_init(&dev) == 0);
    assert(!data.sleep_enabled && registers[PINNACLE_SYS_CFG] == 0);
    assert(irq_enabled && data.work.pending);
    packet[1] = 21;
    status = PINNACLE_STATUS1_SW_DR;
    run_work();
    assert(rel_values[0] == 21);

    reset_activity();
    now_ms = 101;
    activity_work_handler(NULL);
    run_work();
    fail_system_suspend = true;
    now_ms = 201;
    activity_work_handler(NULL);
    assert(!powered_off && zmk_activity_get_state() == ZMK_ACTIVITY_SLEEP);
    assert(!atomic_get(&data.suspended) && data.work.pending);
    run_work();
    assert(!data.sleep_enabled && registers[PINNACLE_SYS_CFG] == 0);
    assert(!sensor_sleeping);
}
"""

HEADERS = (
    "zephyr/device.h", "zephyr/drivers/i2c.h", "zephyr/drivers/spi.h",
    "zephyr/sys/atomic.h", "zephyr/dt-bindings/input/input-event-codes.h",
    "zephyr/init.h", "zephyr/input/input.h", "zephyr/pm/device.h", "zephyr/logging/log.h",
    "zephyr/devicetree.h", "zmk/event_manager.h", "zmk/events/activity_state_changed.h",
    "zephyr/kernel.h", "zephyr/sys/poweroff.h", "zmk/events/position_state_changed.h",
    "zmk/events/sensor_event.h", "zmk/pm.h", "zmk/activity.h",
)


class TrackpadTests(unittest.TestCase):
    def test_patched_driver(self):
        self.run_driver(activity_integration=False)

    def test_real_activity_sleep_wake(self):
        self.run_driver(activity_integration=True)

    def run_driver(self, activity_integration):
        module = os.environ.get("CIRQUE_MODULE_DIR")
        if not module:
            self.fail("Set CIRQUE_MODULE_DIR to the pinned cirque-input-module checkout")
        if os.environ.get("CC"):
            compiler = shlex.split(os.environ["CC"], posix=os.name != "nt")
        elif shutil.which("cc"):
            compiler = ["cc"]
        else:
            compiler = [sys.executable, "-m", "ziglang", "cc"]

        with tempfile.TemporaryDirectory(prefix="zmk-trackpad-tests-") as directory:
            workspace = Path(directory)
            init = subprocess.run(
                ["git", "init", "--quiet", str(workspace)], capture_output=True, text=True,
            )
            self.assertEqual(init.returncode, 0, init.stdout + init.stderr)
            temp = workspace / "build-copy"
            temp.mkdir()
            for name in ("input_pinnacle.c", "input_pinnacle.h"):
                shutil.copyfile(Path(module) / "drivers" / "input" / name, temp / name)
            shutil.copyfile(ROOT / "trackpad" / "src" / "trackpad_idle.c", temp / "trackpad_idle.c")
            patch = subprocess.run(
                [
                    "git", "--work-tree=" + str(temp), "apply",
                    str(ROOT / "trackpad" / "cirque-pinnacle.patch"),
                ],
                cwd=temp, capture_output=True, text=True,
            )
            self.assertEqual(patch.returncode, 0, patch.stdout + patch.stderr)
            stub, harness = STUB, HARNESS
            if activity_integration:
                zmk = os.environ.get("ZMK_MODULE_DIR")
                self.assertTrue(zmk, "Set ZMK_MODULE_DIR to the pinned ZMK checkout")
                shutil.copyfile(Path(zmk) / "app" / "src" / "activity.c", temp / "activity.c")
                stub += ACTIVITY_STUB
                harness = harness.replace("int main(void) {", ACTIVITY_HARNESS + """
int main(void) {
    test_real_activity_wake();
""")
            (temp / "stubs.h").write_text(stub, encoding="ascii")
            (temp / "test.c").write_text(harness, encoding="ascii")
            for name in HEADERS:
                header = temp.joinpath(*name.split("/"))
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text("", encoding="ascii")
            executable = temp / ("trackpad.exe" if os.name == "nt" else "trackpad")
            for idle_sleep in ((1,) if activity_integration else (0, 1)):
                with self.subTest(idle_sleep=idle_sleep):
                    build = subprocess.run(
                        compiler + (["-DTEST_ZMK_ACTIVITY"] if activity_integration else []) + [
                            f"-DCONFIG_ZMK_TRACKPAD_IDLE_SLEEP={idle_sleep}",
                            "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-parameter", "-Wno-unused-function",
                            "-include", str(temp / "stubs.h"), "-I", str(temp),
                            str(temp / "test.c"), "-o", str(executable),
                        ],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("Trackpad checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
