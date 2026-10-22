#pragma once

#include <stdint.h>
#include <zmk/event_manager.h>

#define ZMK_BATTERY_SYNC_UNKNOWN UINT8_MAX

struct zmk_battery_sync_changed {
    uint8_t level;
};

ZMK_EVENT_DECLARE(zmk_battery_sync_changed);

uint8_t zmk_battery_sync_get(void);
