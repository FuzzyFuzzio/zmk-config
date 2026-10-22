#pragma once

#include <zephyr/input/input.h>
#include <zephyr/dt-bindings/input/input-event-codes.h>
#include <zephyr/sys/util.h>

#define TRACKPAD_FRAME_VERSION 1
#define TRACKPAD_BUTTON_MASK 0x1f
#define TRACKPAD_INPUT_RESET_TYPE 0xff

struct trackpad_wire_frame {
    int32_t x, y;
    uint16_t sequence;
    uint8_t buttons;
    uint8_t version;
} __packed;

BUILD_ASSERT(sizeof(struct trackpad_wire_frame) == 12);

struct trackpad_frame_builder {
    struct trackpad_wire_frame frame;
};

struct trackpad_receiver {
    bool valid;
    uint16_t sequence;
};

int trackpad_capture_event(uint8_t reg, struct trackpad_frame_builder *builder,
                          const struct input_event *event);
int trackpad_receive_frame(uint8_t reg, struct trackpad_receiver *receiver,
                          const void *data, size_t length);
void trackpad_release(uint8_t reg);
int trackpad_bt_send_frame(uint8_t reg, const struct trackpad_wire_frame *frame);
int trackpad_deliver_frame(uint8_t reg, const struct trackpad_wire_frame *frame);
