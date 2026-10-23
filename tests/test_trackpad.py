"""Compile and exercise the patched Cirque driver with simulated I/O.

Set CIRQUE_MODULE_DIR to the cirque-input-module checkout from config/west.yml.
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
#define CONFIG_LOG 1
#define IS_ENABLED(x) x
#define LOG_MODULE_REGISTER(...)
#define LOG_HEXDUMP_DBG(...)
#define LOG_DBG(...)
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
static int scheduled_delay, schedules, reschedules, ready_pin, interrupt_error;
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
static int input_report_rel(const struct device *d, int code, int value, bool sync, int timeout) {
    assert(sync == (code == INPUT_REL_Y));
    now_ms += input_delay_ms;
    rel_values[code] = value; rel_reports++; return 0;
}
static int input_report_key(const struct device *d, int code, int value, bool sync, int timeout) {
    key_reports++; return 0;
}
"""

HARNESS = r"""
#include "input_pinnacle.c"

static struct pinnacle_data data;
static uint8_t packet[3], status;
static int status_error, packet_error, ack_error, acks, reads, race_edge;
static uint8_t feed_cfg2;
static uint8_t registers[32], era[512];
static int fail_read_addr = -1, fail_write_addr = -1, era_busy, cal_busy, readback_bad;
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
    registers[addr] = val;
    if (addr == PINNACLE_SYS_CFG && (val & PINNACLE_SYS_CFG_RESET)) {
        memset(registers, 0, sizeof(registers));
        status = PINNACLE_STATUS1_SW_CC;
    }
    if (addr == PINNACLE_CAL_CFG) {
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
int main(void) {
    test_i2c_protocol();
    test_deltas();
    test_errors();
    test_headers_and_calibration();
    test_edges_and_buttons();
    test_power_and_init();
    test_faults_and_timeouts();
    puts("Trackpad checks passed: decoding, recovery, edges, buttons, PM and init");
    return 0;
}
"""

HEADERS = (
    "zephyr/device.h", "zephyr/drivers/i2c.h", "zephyr/drivers/spi.h",
    "zephyr/sys/atomic.h", "zephyr/dt-bindings/input/input-event-codes.h",
    "zephyr/init.h", "zephyr/input/input.h", "zephyr/pm/device.h", "zephyr/logging/log.h",
)


class TrackpadTests(unittest.TestCase):
    def test_patched_driver(self):
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
            patch = subprocess.run(
                [
                    "git", "--work-tree=" + str(temp), "apply",
                    str(ROOT / "trackpad" / "cirque-pinnacle.patch"),
                ],
                cwd=temp, capture_output=True, text=True,
            )
            self.assertEqual(patch.returncode, 0, patch.stdout + patch.stderr)
            (temp / "stubs.h").write_text(STUB, encoding="ascii")
            (temp / "test.c").write_text(HARNESS, encoding="ascii")
            for name in HEADERS:
                header = temp.joinpath(*name.split("/"))
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text("", encoding="ascii")
            executable = temp / ("trackpad.exe" if os.name == "nt" else "trackpad")
            build = subprocess.run(
                compiler + [
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
