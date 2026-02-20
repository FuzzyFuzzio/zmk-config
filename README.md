# README

Layout tool: https://nickcoutsos.github.io/keymap-editor/

![layer0](<./visualization/default layer.png>)
![layer1](<./visualization/game layer.png>)
![layer2](<./visualization/left layer.png>)
![layer3](<./visualization/right layer.png>)
![layer4](<./visualization/func layer.png>)

## Dongle-Based Split Setup

This configuration uses an `nrf52840_mdk_usb_dongle` as the central, with both halves (`hillside_view_left` and `hillside_view_right`) acting as peripherals. Pointer events (glidepoint/cirque) and keys are relayed to the dongle via **native ZMK split input support**.

### Architecture
- **Central**: USB dongle (connects to host via USB only, no BLE to host)
- **Peripherals**: Left and right halves (connect to central via BLE split protocol)
- **Pointer relay**: Uses native `CONFIG_ZMK_INPUT_SPLIT` (ZMK PR #2477) instead of external relay modules
  - Right physical glidepoint: `reg = <1>` 
  - Left virtual input: `reg = <0>` (for keymap binding symmetry)

### Build Targets
| Device | Board | Shield |
| ------ | ------ | ------ |
| Left half | `nice_nano_v2` | `hillside_view_left nice_view_battery` |
| Right half | `nice_nano_v2` | `hillside_view_right nice_view_battery` |
| Dongle | `nrf52840_mdk_usb_dongle` | `keyboard_dongle` |
| Settings reset (optional) | `nice_nano_v2` | `settings_reset` |

### Flash Order
1. (Optional) Flash `settings_reset` onto each half to clear prior bonds. Then re-flash their normal firmware.
2. Flash left and right halves.
3. Flash dongle.

### Pairing Steps
1. Plug in dongle (central) via USB.
2. Power both halves. They will attempt to connect to the central automatically (split bond creation).
3. Put the dongle into BLE pairing mode (use a key mapped to `&bluetooth` or bootloader/pair combo if defined; otherwise temporarily build a keymap with a pairing key).
4. Pair the host computer to the dongle. Do NOT pair the halves directly to the host.
5. After pairing, key presses and pointing events from both halves should appear on the host.

### Verifying Pointer Relay
Right side: physical glidepoint (`glidepoint0`) -> split input `reg=<1>` -> resurrected as `glidepoint_right` on dongle.
Left side: virtual input only (no hardware) -> split input `reg=<0>` -> resurrected as `glidepoint_left` on dongle for keymap binding symmetry.

If pointer input from the right half is missing:
- Confirm both halves show connected status (LED behavior or via logs if enabled).
- Ensure `reg` values match between peripheral and central overlays.
- Confirm `CONFIG_ZMK_INPUT_SPLIT=y` and `CONFIG_ZMK_POINTING=y` are set.

### Troubleshooting
- Stale bonds: Use `settings_reset` target and re-flash.
- Host sees two devices: Remove old bond to a former central (e.g., left half) from OS BT settings.
- No USB output: Verify dongle shield config has `CONFIG_ZMK_USB=y` and board supports USB (it does).

### Future Enhancements
- Add a pairing/status key or LED to the dongle (would then create a `keyboard_dongle.dtsi`).
- Add a battery reporting behavior if powering the dongle from a battery (currently USB powered).

