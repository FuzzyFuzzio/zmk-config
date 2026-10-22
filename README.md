# README

Layout tool: https://nickcoutsos.github.io/keymap-editor/

![layer0](<./visualization/default layer.png>)
![layer1](<./visualization/game layer.png>)
![layer2](<./visualization/left layer.png>)
![layer3](<./visualization/right layer.png>)
![layer4](<./visualization/func layer.png>)

## Setup

Firmware is built for two modes by [build.yaml](build.yaml) (ZMK v0.3, see [config/west.yml](config/west.yml)).
The right half is the same in both.

### Repository layout
Hardware definitions live in the root-level Zephyr module declared by
[zephyr/module.yml](zephyr/module.yml): [boards/shields](boards/shields) contains the shields,
[dts](dts) contains custom devicetree bindings, and
[dongle_split_recovery](dongle_split_recovery) and [layer_sync](layer_sync) contain custom firmware code.
User keymaps, configuration, and the west manifest remain in [config](config).
The ZMK v0.3 reusable build workflow detects this module automatically. For local builds, pass
`-DZMK_EXTRA_MODULES=<repository-root>` alongside `-DZMK_CONFIG=<repository-root>/config` to CMake.

| Mode | Device | Board | Shield |
| ---- | ------ | ----- | ------ |
| Dongle | Dongle (central, USB to host) | `nrf52840_mdk_usb_dongle` | `keyboard_dongle` |
| Dongle | Left half (peripheral, nice!view) | `nice_nano_v2` | `hillside_view_left nice_view_battery` |
| No dongle | Left half (central, BLE to host, nice!view) | `nice_nano_v2` | `hillside_view_left_central nice_view_battery` |
| Both | Right half (peripheral, Cirque trackpad) | `nice_nano_v2` | `hillside_view_right` |
| Utility | Settings reset | `nice_nano_v2` / `nrf52840_mdk_usb_dongle` | `settings_reset` |

The right half has no display; its display stack and nice!view SPI bus are disabled.

### Battery display
The left display shows `(left / right)` percentages inside the battery image, for example
`(25 / 18)`. The fill level and lightning bolt still refer to the left half; the bolt
means USB power is present, not that the charger has confirmed current into the battery.
`--` means the right reading is not available.

This works in both modes. The right half exposes a read-only, encrypted battery
characteristic. The central (dongle or left half) reads it approximately once per minute
and mirrors it to the left display using [battery_sync](battery_sync). Identifying the
right half by its characteristic avoids relying on BLE pairing order. Battery telemetry
does not generate key or pointer activity and does not keep the keyboard awake.
The right reading is cleared when its link to the central is lost, or when the left
peripheral loses its link to the dongle.

Flash the new firmware to **both halves and the dongle** for dongle mode, or to **both
halves** for no-dongle mode. Older right-half firmware will show `--` on the new display.
Battery values remain ZMK's voltage-based estimates; ZMK v0.3 pauses local battery
sampling while idle, so press a key on a half to refresh its reading after charging.
With the standard HillSideView battery wiring, the half's switch must be **ON** to charge.

### Trackpad
The right half's Cirque glidepoint is forwarded to the central with native ZMK split input
(`zmk,input-split`, `reg = <1>` on both sides). The peripheral inverts Y before sending; the central's
input listener scales movement 2x and turns it into scrolling on layer 3 (Mouse).

The Cirque driver's ZMK idle-sleep integration is disabled on the right half.
Upstream [disabled it by default](https://github.com/petejohanson/cirque-input-module/commit/b4c4f8135ed2)
because wake is unreliable. The trackpad's devicetree `sleep` option is also absent.
This avoids trackpad sleep transitions during normal operation; ZMK's keyboard-level
deep sleep remains enabled. Keeping the trackpad awake may increase idle battery use.

### Layer display
The central mirrors its highest active layer to the peripherals ([layer_sync](layer_sync)),
so the left half's nice!view shows the current layer in dongle mode too.
In no-dongle mode, the left central reads its own layer directly and mirroring is disabled.

### Event queue headroom
The halves use a 32-entry scan-event queue so a scan can report all 23 local keys before
the consumer runs. Both centrals use 32-entry split-event and downstream input queues.
These settings improve burst capacity; they do not increase radio throughput or eliminate
the possibility of overflow under sustained overload.

### Firmware builds
The build workflow produces one `firmware` archive with the six targets in
[build.yaml](build.yaml), covering both modes and settings-reset utilities.
BLE interval, latency, PHY, and TX buffer settings retain their baseline values.
The Cirque driver is pinned in [config/west.yml](config/west.yml) for reproducible builds.

Host regression tests for the battery relay and label formatting are in
[tests/test_battery_sync.py](tests/test_battery_sync.py). Run
`python -m unittest discover -s tests -p test_battery_sync.py` with a GCC/Clang-compatible
`CC`, or the `ziglang` Python package installed. These simulate Zephyr/Bluetooth calls
and do not replace the firmware builds or a hardware connection test.

### Flashing
1. (Optional) Flash `settings_reset` to every device that should forget old bonds, then re-flash its normal firmware.
2. Flash the halves, then the central (dongle or left central).
3. Power everything on; the halves bond to the central automatically. In dongle mode the host only needs USB.

### Bond recovery
- **Dongle (automatic)**: on key errors, MIC failures or repeated disconnects before encryption, the dongle drops
  that half's bond so the next connection re-pairs ([dongle_bond_autoheal.c](dongle_split_recovery/src/dongle_bond_autoheal.c)).
- **Peripheral halves (manual)**: hold the half's top and bottom outer-column keys while switching it on, or
  hold them for 5 s at any time, to wipe its bonds and re-pair
  ([peripheral_boot_bondclear.c](dongle_split_recovery/src/peripheral_boot_bondclear.c)).
- If all else fails, flash `settings_reset` to the halves and the dongle.

### Troubleshooting
- Host sees two keyboards: remove the old bond to a former central (e.g. the left half) from the OS Bluetooth settings.
- No trackpad input: check that both halves show connected and that the `reg` values in the right and central overlays match.
- Trackpad stops until the right half is power-cycled: the disabled Cirque idle-sleep
  integration is a mitigation, not a confirmed diagnosis. After flashing the right half,
  test continuous pointer use, typing/scrolling together, more than 30 minutes idle
  followed by a right-half keypress and pointer movement, and a battery-powered
  deep-sleep/wake cycle (more than two hours idle, then wake with a key).
  If it recurs, record whether right-half keys still work, whether it followed idle
  or deep sleep, and whether typing on the right half restores the pointer.
  Working right-half keys with a dead pointer helps distinguish a local trackpad
  failure from loss of the whole split connection. Do not reset bonds just for this test.