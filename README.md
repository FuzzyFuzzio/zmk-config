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

| Mode | Device | Board | Shield |
| ---- | ------ | ----- | ------ |
| Dongle | Dongle (central, USB to host) | `nrf52840_mdk_usb_dongle` | `keyboard_dongle` |
| Dongle | Left half (peripheral, nice!view) | `nice_nano_v2` | `hillside_view_left nice_view_battery` |
| No dongle | Left half (central, BLE to host, nice!view) | `nice_nano_v2` | `hillside_view_left_central nice_view_battery` |
| Both | Right half (peripheral, Cirque trackpad) | `nice_nano_v2` | `hillside_view_right` |
| Utility | Settings reset | `nice_nano_v2` / `nrf52840_mdk_usb_dongle` | `settings_reset` |

### Trackpad
The right half's Cirque glidepoint is forwarded to the central with native ZMK split input
(`zmk,input-split`, `reg = <1>` on both sides). The peripheral inverts Y before sending; the central's
input listener scales movement 2x and turns it into scrolling on layer 3 (Mouse).

### Layer display
The central mirrors its highest active layer to the peripherals ([config/layer_sync](config/layer_sync)),
so the left half's nice!view shows the current layer in dongle mode too.

### Flashing
1. (Optional) Flash `settings_reset` to every device that should forget old bonds, then re-flash its normal firmware.
2. Flash the halves, then the central (dongle or left central).
3. Power everything on; the halves bond to the central automatically. In dongle mode the host only needs USB.

### Bond recovery
- **Dongle (automatic)**: on key errors, MIC failures or repeated disconnects before encryption, the dongle drops
  that half's bond so the next connection re-pairs ([dongle_bond_autoheal.c](config/dongle_split_recovery/src/dongle_bond_autoheal.c)).
- **Peripheral halves (manual)**: hold the half's top and bottom outer-column keys while switching it on, or
  hold them for 5 s at any time, to wipe its bonds and re-pair
  ([peripheral_boot_bondclear.c](config/dongle_split_recovery/src/peripheral_boot_bondclear.c)).
- If all else fails, flash `settings_reset` to the halves and the dongle.

### Troubleshooting
- Host sees two keyboards: remove the old bond to a former central (e.g. the left half) from the OS Bluetooth settings.
- No trackpad input: check that both halves show connected and that the `reg` values in the right and central overlays match.