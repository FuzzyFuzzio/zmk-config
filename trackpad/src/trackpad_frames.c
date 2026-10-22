#include <zephyr/kernel.h>
#include <zephyr/devicetree.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/byteorder.h>
#include <trackpad_frames.h>

LOG_MODULE_REGISTER(trackpad_frames, CONFIG_INPUT_LOG_LEVEL);

#define FRAME_MAX_AGE_MS 50
#define FRAME_QUEUE_SIZE 32

BUILD_ASSERT(DT_NUM_INST_STATUS_OKAY(zmk_input_split) == 1,
             "Reliable trackpad relay requires exactly one split input device");

struct queued_frame {
    struct trackpad_wire_frame frame;
    int64_t timestamp;
    uint8_t reg;
};

K_MSGQ_DEFINE(frame_queue, sizeof(struct queued_frame), FRAME_QUEUE_SIZE, 4);
static struct k_spinlock pending_lock;
static struct queued_frame pending_frame;
static bool pending;
static struct k_work_q frame_work_q;
K_THREAD_STACK_DEFINE(frame_stack, 2048);
static struct k_work_delayable frame_work;
static struct queued_frame current;
static bool have_current;
static uint16_t retry_ms;
static int64_t retry_at;
static bool stale_warned;

static void enqueue_frame(uint8_t reg, const struct trackpad_wire_frame *frame) {
    struct queued_frame queued = {.frame = *frame, .timestamp = k_uptime_get(), .reg = reg};
    bool overflow = false;
    k_spinlock_key_t key = k_spin_lock(&pending_lock);
    if (pending || k_msgq_put(&frame_queue, &queued, K_NO_WAIT) < 0) {
        overflow = !pending;
        pending_frame = queued;
        pending = true;
    }
    k_spin_unlock(&pending_lock, key);
    if (overflow) {
        LOG_ERR("Trackpad frame queue full; coalescing overflow to latest button/motion snapshot");
    }
    k_work_schedule_for_queue(&frame_work_q, &frame_work, K_NO_WAIT);
}

static bool next_frame(struct queued_frame *frame) {
    if (k_msgq_get(&frame_queue, frame, K_NO_WAIT) == 0) {
        return true;
    }
    k_spinlock_key_t key = k_spin_lock(&pending_lock);
    bool found = pending;
    if (found) {
        *frame = pending_frame;
        pending = false;
    }
    k_spin_unlock(&pending_lock, key);
    return found;
}

static void frame_work_cb(struct k_work *work) {
    int64_t remaining = retry_at - k_uptime_get();
    if (remaining > 0) {
        /* Rescheduling cannot unsubmit a callback already queued by a producer. */
        k_work_reschedule_for_queue(&frame_work_q, &frame_work, K_MSEC(remaining));
        return;
    }
    /* Bound each turn so a steady stream cannot monopolize this worker. */
    for (int count = 0; count < 32; count++) {
        if (!have_current) {
            have_current = next_frame(&current);
            if (!have_current) {
                return;
            }
        }
        int64_t age = k_uptime_get() - current.timestamp;
        if (age >= FRAME_MAX_AGE_MS) {
            current.frame.x = current.frame.y = 0;
            /* Do not replay historical clicks after a stalled link either. */
            for (int discarded = 0; discarded < FRAME_QUEUE_SIZE + 1; discarded++) {
                struct queued_frame newer;
                if (!next_frame(&newer)) {
                    break;
                }
                current = newer;
                if (k_uptime_get() - current.timestamp < FRAME_MAX_AGE_MS) {
                    break;
                }
                current.frame.x = current.frame.y = 0;
            }
            if (!stale_warned) {
                LOG_WRN("Coalescing stale trackpad samples (age %lld ms); retaining latest buttons",
                        (long long)age);
                stale_warned = true;
            }
        } else {
            stale_warned = false;
        }

#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
        int ret = trackpad_deliver_frame(current.reg, &current.frame);
#else
        struct trackpad_wire_frame wire = current.frame;
        wire.x = sys_cpu_to_le32(wire.x);
        wire.y = sys_cpu_to_le32(wire.y);
        wire.sequence = sys_cpu_to_le16(wire.sequence);
        int ret = trackpad_bt_send_frame(current.reg, &wire);
#endif
        if (ret < 0) {
            if (ret == -ENODEV || ret == -EINVAL || ret == -ENOTSUP || ret == -ERANGE) {
                LOG_ERR("Dropping unroutable/invalid complete trackpad frame: %d", ret);
                have_current = false;
                retry_ms = 0;
                retry_at = 0;
                continue;
            }
            if (retry_ms == 0) {
                LOG_ERR("Trackpad frame delivery failed: %d", ret);
            }
            retry_ms = MIN(retry_ms < 5 ? 5 : retry_ms * 2, 250);
            retry_at = k_uptime_get() + retry_ms;
            k_work_reschedule_for_queue(&frame_work_q, &frame_work, K_MSEC(retry_ms));
            return;
        }
        retry_ms = 0;
        retry_at = 0;
        have_current = false;
    }
    k_work_schedule_for_queue(&frame_work_q, &frame_work, K_NO_WAIT);
}

int trackpad_capture_event(uint8_t reg, struct trackpad_frame_builder *builder,
                          const struct input_event *event) {
    struct trackpad_wire_frame *frame = &builder->frame;
    if (event->type == INPUT_EV_KEY && event->code >= INPUT_BTN_0 &&
        event->code < INPUT_BTN_0 + 5) {
        WRITE_BIT(frame->buttons, event->code - INPUT_BTN_0, event->value != 0);
    } else if (event->type == INPUT_EV_REL) {
        switch (event->code) {
        case INPUT_REL_X: frame->x = event->value; break;
        case INPUT_REL_Y: frame->y = event->value; break;
        default:
            LOG_ERR("Unsupported trackpad relative code %u", event->code);
            return -ENOTSUP;
        }
    } else {
        LOG_ERR("Unsupported trackpad event %u/%u", event->type, event->code);
        return -ENOTSUP;
    }
    if (event->sync) {
        frame->version = TRACKPAD_FRAME_VERSION;
        enqueue_frame(reg, frame);
        frame->sequence++;
        frame->x = frame->y = 0;
    }
    return 0;
}

int trackpad_receive_frame(uint8_t reg, struct trackpad_receiver *receiver,
                          const void *data, size_t length) {
    if (!receiver || !data || length != sizeof(struct trackpad_wire_frame)) {
        LOG_ERR("Invalid trackpad frame length %u", (unsigned int)length);
        return -EINVAL;
    }
    struct trackpad_wire_frame frame;
    memcpy(&frame, data, sizeof(frame));
    if (frame.version != TRACKPAD_FRAME_VERSION || (frame.buttons & ~TRACKPAD_BUTTON_MASK)) {
        LOG_ERR("Invalid trackpad frame version/buttons %u/%u", frame.version, frame.buttons);
        return -EINVAL;
    }
    frame.x = sys_le32_to_cpu(frame.x);
    frame.y = sys_le32_to_cpu(frame.y);
    frame.sequence = sys_le16_to_cpu(frame.sequence);
    /* Current device is a relative Cirque: reject corrupted/unbounded motion before scaling. */
    if (frame.x < -255 || frame.x > 255 || frame.y < -255 || frame.y > 255) {
        LOG_ERR("Trackpad frame has invalid motion");
        return -ERANGE;
    }
    if (receiver->valid && receiver->sequence == frame.sequence) {
        return 0;
    }
    if (receiver->valid && frame.sequence != (uint16_t)(receiver->sequence + 1)) {
        LOG_WRN("Trackpad frame sequence gap: %u -> %u", receiver->sequence, frame.sequence);
    }
    receiver->valid = true;
    receiver->sequence = frame.sequence;
    enqueue_frame(reg, &frame);
    return 0;
}

void trackpad_release(uint8_t reg) {
    struct trackpad_wire_frame frame = {.version = TRACKPAD_FRAME_VERSION};
    enqueue_frame(reg, &frame);
}

static int frame_init(void) {
    k_work_init_delayable(&frame_work, frame_work_cb);
    k_work_queue_start(&frame_work_q, frame_stack, K_THREAD_STACK_SIZEOF(frame_stack), 5, NULL);
    return 0;
}

SYS_INIT(frame_init, POST_KERNEL, CONFIG_KERNEL_INIT_PRIORITY_DEFAULT);
