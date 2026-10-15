#pragma once

#include <zephyr/kernel.h>
#include <zmk/event_manager.h>

/* Raised on a split peripheral when the central reports a new toggled layer index. */
struct zmk_layer_sync_changed {
    uint8_t layer;
};

ZMK_EVENT_DECLARE(zmk_layer_sync_changed);

uint8_t zmk_layer_sync_get(void);
