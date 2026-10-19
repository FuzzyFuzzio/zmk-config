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

### Trackpad
The right half's Cirque glidepoint is forwarded to the central with native ZMK split input
(`zmk,input-split`, `reg = <1>` on both sides). The peripheral inverts Y before sending; the central's
input listener scales movement 2x and turns it into scrolling on layer 3 (Mouse).

### Layer display
The central mirrors its highest active layer to the peripherals ([layer_sync](layer_sync)),
so the left half's nice!view shows the current layer in dongle mode too.
In no-dongle mode, the left central reads its own layer directly and mirroring is disabled.

### Event queue headroom
The halves use a 32-entry scan-event queue so a scan can report all 23 local keys before
the consumer runs. Both centrals use 32-entry split-event and downstream input queues.
These settings improve burst capacity; they do not increase radio throughput or eliminate
the possibility of overflow under sustained overload.

### Opt-in BLE experiments
Normal [build.yaml](build.yaml) builds retain the existing BLE interval, latency, PHY, and TX
buffer settings. The Cirque driver is pinned to the previously built revision in
[config/west.yml](config/west.yml) so A/B builds use the same driver.

To build the experiments, run the build workflow manually with `ble_experiments` enabled.
The run produces the normal `firmware` baseline archive and a separate
`firmware-ble-experiments` archive using [build-experiments.yaml](build-experiments.yaml).
The workflow change must first be available on the default branch for GitHub's manual
dispatch UI to expose this input; then select the branch being tested.

| Trial | Central firmware suffix | Right-half firmware | Changed from baseline |
| ----- | ----------------------- | ------------------- | --------------------- |
| A: baseline | Normal firmware from `firmware` | Normal right firmware | None |
| B: latency only | `-ble-low-latency` | Normal right firmware | Split peripheral latency 30 -> 0 |
| C: TX headroom only | `-ble-tx-headroom` | `hillside_view_right-ble-tx-headroom` | L2CAP TX, ACL TX, and connection TX contexts -> 6 on both devices |
| D: combined | `-ble-combined` | Same TX-headroom right firmware as C | B and C together |

Use the `keyboard_dongle` central files for dongle mode or `hillside_view_left_central` for
no-dongle mode. The dongle-mode left peripheral always uses its normal firmware.
The headroom trial intentionally treats the three related TX capacities as one factor;
it does not identify which individual buffer pool is limiting.

The snippets are [ble-low-latency](snippets/ble-low-latency/snippet.yml) (central only) and
[ble-tx-headroom](snippets/ble-tx-headroom/snippet.yml) (central and right half).
For local builds, add `-S ble-low-latency`, `-S ble-tx-headroom`, or
`-S "ble-low-latency ble-tx-headroom"` to `west build`, along with the module/config arguments
above. Use a pristine build when changing snippets.

Before flashing, check each build log's generated Kconfig:
- Both central types: `ZMK_SPLIT_BLE_CENTRAL_POSITION_QUEUE_SIZE=32`,
  `INPUT_QUEUE_MAX_MSGS=32`; halves: `ZMK_KSCAN_EVENT_QUEUE_SIZE=32`.
- Trial B/D centrals: `ZMK_SPLIT_BLE_PREF_LATENCY=0`; A/C remain `30`.
- Trial C/D centrals and the TX-headroom right: `BT_L2CAP_TX_BUF_COUNT=6`,
  `BT_BUF_ACL_TX_COUNT=6`, `BT_CONN_TX_MAX=6`.
- Every trial retains `ZMK_SPLIT_BLE_PREF_INT=6` (7.5 ms) on centrals,
  `ZMK_SPLIT_BLE_PREF_TIMEOUT=400`, disabled `BT_CTLR_PHY_2M`, the same TX power,
  and unchanged host BLE connection preferences, hold-taps, debounce, and trackpad scaling.

Run A/B/A, then A/C/A, before D. Flash the matching right firmware when switching between
baseline and TX trials, and power-cycle/reconnect the halves after changing central latency
so the new connection parameters take effect. Do not reset bonds between ordinary trials.
Keep distance, dongle placement, host transport, battery charge, and workload comparable.
Test both modes separately; no-dongle BLE adds a host connection that dongle USB does not.

For each trial, record the firmware commit, mode, host transport, actual negotiated interval
and latency when instrumentation is available, pointer report gaps/stalls during simultaneous
typing and scrolling, missed/stuck keys, reconnects, post-idle first-touch behavior, and
battery runtime. Use equal-duration sessions and compare repeated runs, not one subjective
pass. Typing Lab can compare typing errors but cannot measure physical switch-to-host latency.
Retain a candidate only if the target symptom improves repeatedly without new missed/stuck
inputs, reconnect failures, or unacceptable battery cost. Otherwise restore both normal files.

Latency zero can increase peripheral power consumption; it is not guaranteed to reduce
active-input latency. Extra buffers consume RAM and can allow a longer backlog; they do not
increase radio bandwidth. These are unproven opt-in trials, not a new recommended preset.

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