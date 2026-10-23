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
The left display shows `left / right` percentages inside the battery image, for example
`25 / 18`. The fill level and lightning bolt still refer to the left half; the bolt
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
The right half's Cirque glidepoint uses ZMK split input devices
(`zmk,input-split`, `reg = <1>` on both sides). The peripheral inverts Y before sending; the central's
input listener scales movement 2x and turns it into scrolling on layer 3 (Mouse).

The pinned driver and ZMK input paths are patched by [trackpad/CMakeLists.txt](trackpad/CMakeLists.txt)
using [cirque-pinnacle.patch](trackpad/cirque-pinnacle.patch) and
[zmk-input-frames.patch](trackpad/zmk-input-frames.patch). Patching happens in a
private build-directory copy, never in the west module checkout, and fails the build
if the patch cannot be applied. The module dependency ensures the original driver is
registered before its source is replaced, so only the patched copy is compiled.
The fixes:

- Follow Cirque's STOP-delimited I2C register-read sequence, rather than using a
  combined write/repeated-START/read transaction. See section 8.1 of
  [Cirque's Pinnacle interface guide](https://www.dropbox.com/s/0g2b2ysrly41hi8/GT-AN-090620%20InterfacingtoPinnacle_I2C-SPI.pdf?dl=0).
- Validate the relative packet's fixed header bits before decoding it. Malformed
  samples are acknowledged and discarded, not forwarded as movement or clicks
  and not retried indefinitely as the same corrupt packet.
- Clear command-complete interrupts even when no movement packet is ready.
  Calibration and power-on reset can assert the same hardware data-ready line as
  pointer data; leaving that flag set prevents the next rising edge.
- Decode relative X/Y using the separate sign flags and full movement bytes, rather
  than narrowing to `int8_t`. Large positive movements previously reversed direction.
  Signed zero stays zero.
- Retry failed reads and status acknowledgements even if data-ready remains high
  without another interrupt edge. Retries back off from 5 ms to 250 ms on persistent
  errors; valid packets are emitted only after acknowledgement succeeds. A data-ready
  check also catches samples arriving during processing, startup, or device resume.
- Disable GlideExtend, which otherwise continues movement at the pad edge. Normal
  tap-to-click, Y orientation, 2x pointer scaling, and layer-3 scrolling are unchanged.
- Bound extended-register polling to 100 ms and calibration/reset polling to 500 ms,
  sleeping between polls and propagating read errors. A poll deadline can overshoot
  by an in-flight bus transfer's own timeout; it is not a hard real-time guarantee.
- Check required writes/readbacks, bus/GPIO readiness, and GPIO/callback setup.
  Work/state are initialized before callbacks, interrupts remain disabled throughout
  setup, and the data feed is enabled last. Missing data-ready pins or out-of-byte-range
  edge thresholds fail compilation instead of using invalid defaults.
- Run sensor I/O on a dedicated worker. Suspend disables interrupts and synchronously
  drains that worker; resume polls for an already-pending sample. Sleep register
  access is serialized with report reads. SPI write failures return before inspecting
  an undefined receive buffer.
- Inspect command-complete events for lost feed settings, restore pointer/feature
  registers, discard the old sample, and release cached buttons after recovery.
  This is feed recovery, not a new sensor calibration or a guarantee that a reset
  under a finger produced a good analog calibration.
- Disable the unused IntelliMouse/hardware scrolling modes. Hardware wheel bytes
  were not consumed by this driver; scrolling is still provided by layer 3.
- Acknowledge but do not forward unchanged zero-motion frames.

The protocol and hardening fixes do not change ADC sensitivity, hardware filtering,
sample rate, or automatic compensation. They do not force calibration during use:
Cirque warns that calibrating with a finger on the pad can itself spoil tracking.

#### Complete-frame split delivery

[trackpad_frames.c](trackpad/src/trackpad_frames.c) sends each sample as one versioned,
12-byte BLE notification containing both axes, the complete button state, and a
sequence number. This fits the default ATT payload without increasing the MTU.
The relay is intentionally limited to one split trackpad; multiple split input
devices fail compilation rather than sharing one overflow/button-state snapshot.
Normal movement needs one notification rather than separate X and Y notifications;
button changes do not need extra notifications. Duplicate frames are ignored and
sequence gaps are logged. The new central still accepts legacy 8-byte events, but
the complete-frame reliability guarantees require updated firmware at both ends.
Input and unsubscribe callbacks must still belong to the active connection, so
late callbacks cannot inject motion or clear a newly reused subscription.

Each side has a dedicated delivery worker, a 32-frame queue, and one latest-overflow
snapshot. Congestion never blocks the sensor worker on Bluetooth. Failed delivery
is retried with 5-250 ms backoff. Motion already 50 ms old when the delivery worker
attempts it is discarded, while button state is retained. This limits replay from
our queue, not time spent inside Bluetooth or host stacks. Stale snapshots coalesce
to the latest button state too, rather than replaying historical taps as phantom
clicks after a stalled link. Queue overflow is
logged and coalesces the overflow to the latest complete snapshot: under sustained
overload or stale delivery, intermediate movement and clicks may be lost, but a queued final release
is not silently replaced by a held-button default. This bounded policy does not
promise lossless delivery during an indefinitely broken radio/host connection.
An enqueue concurrent with a failed send cannot bypass the retry backoff: an
absolute retry deadline also rejects callbacks that Zephyr had already submitted.

At the central, complete frames cannot lose a final sync through a non-blocking
queue insertion. A partial downstream input failure is explicitly cleared from the
listener before retry, preventing duplicated movement. A split disconnect queues
a button-release snapshot. Zephyr's Bluetooth/input calls can still wait inside the
dedicated delivery worker; queue/stale-motion diagnostics expose congestion without
stalling unrelated system work.

#### Bluetooth startup order

Patched ZMK application sources must replace their original positions in the app
source list, not be prepended during module configuration. Same-priority `SYS_INIT`
entries follow object link order. In `383a171`, prepending the split central source
made `zmk_split_bt_central_init()` run before `zmk_ble_init()` at application priority
50. The split registered its dynamic settings handler, then `bt_enable()` initialized
the settings subsystem and cleared that registration. The split's commit callback
never ran, `settings_loaded` remained false, and the dongle never enabled scanning.
This prevented both halves connecting even though compilation and unit tests passed.

Source replacement is now deferred until ZMK has registered its application sources,
then performed in place. [check_init_order.py](trackpad/check_init_order.py) checks
the actual linked ELF startup entries after every affected firmware build. Centrals
require core Bluetooth before split initialization; peripherals require their
notification service before peripheral initialization (which enables Bluetooth).

**Flash the updated central first, then the right half:** the dongle in dongle mode,
or the left-central half in no-dongle mode. The left peripheral does not need flashing
for these trackpad changes. An old central cannot decode the new right-half frames.
No bond reset is required. Hardware testing is still needed to validate the complete
motion path, tapping/dragging, scrolling, congestion recovery, and deep-sleep/wake.

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
Recheck both local trackpad patches and their regression tests before updating the pins.
CI runs the host suites against both manifest-selected upstream checkouts before
starting firmware builds.

Host regression tests for the battery relay and label formatting are in
[tests/test_battery_sync.py](tests/test_battery_sync.py). Run
`python -m unittest discover -s tests -p test_battery_sync.py` with a GCC/Clang-compatible
`CC`, or the `ziglang` Python package installed. These simulate Zephyr/Bluetooth calls
and do not replace the firmware builds or a hardware connection test.

Trackpad regression tests in [tests/test_trackpad.py](tests/test_trackpad.py) compile
the real patched driver against simulated I/O. Set `CIRQUE_MODULE_DIR` to the pinned
`cirque-input-module` checkout and `ZMK_MODULE_DIR` to the ZMK checkout, then run
`python -m unittest discover -s tests -v` to run all suites. Git and the same host
compiler support are required. Missing upstream paths fail the tests rather than
silently skipping coverage. The driver suite checks all movement-byte/sign
combinations, signed zero, read/acknowledgement failures, recovery without a new edge,
retry backoff, interrupt races, button release, startup, and device suspend/resume.
They also exercise the actual I2C read helper, all 256 packet headers, command-complete
interrupts with and without pointer data, and slow input delivery diagnostics. The
STOP-sequence regression fails against the first version of the trackpad patch.
It also checks busy-register deadlines, setup/readback failures, readiness, safe
callback ordering, synchronous cancellation, SPI errors, lost-feed recovery and empty
frames. [Frame tests](tests/test_trackpad_frames.py) exercise peripheral and central
queue roles, exact 12-byte format, duplicate/wrapping/gapped sequences, the 49/50 ms
stale-motion boundary, backoff, overflow coalescing and retained button releases.
[Split tests](tests/test_trackpad_split.py) compile the real patched ZMK proxy and
listener functions and inject a failure between X and Y/sync to check clean replay.
[Startup tests](tests/test_trackpad_init.py) exercise the real module CMake source
registration and the real Zephyr settings initialization/registration functions,
including the lost-handler failure from `383a171`. They require CMake, Ninja and
the manifest-selected Zephyr checkout (`ZEPHYR_MODULE_DIR`; a sibling `zephyr`
checkout is also detected). CI checks out the exact settings source and does not
skip this regression. The firmware build additionally checks actual ELF ordering;
host mocks alone cannot validate device startup order.

For a right-half USB diagnostic build, use ZMK's existing `zmk-usb-logging` snippet
(`west build -S zmk-usb-logging`) to supply the CDC UART devicetree node, and add
`-DEXTRA_CONF_FILE=<repository-root>/trackpad/diagnostics.conf` to its CMake arguments.
This opt-in configuration enables warning/error-only USB serial logs without the
per-packet debug stream. Flash that right-half build, connect it to a USB data port,
and open its serial console (115200 baud) to capture a failure. Normal firmware does
not enable USB logging. With logging enabled, the driver also warns if local input
delivery takes at least 50 ms; this can expose backpressure between the trackpad and
split forwarding without changing report delivery or dropping half of an X/Y pair.

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
- Neither half connects to the dongle with `383a171`: update the dongle to the
  startup-order fix, then power-cycle the halves. The failure was loss of the
  split settings handler during boot, not evidence of corrupt bonds. Do not use
  `settings_reset` for this regression. Halves already using the matching firmware
  roles do not need reflashing to correct the dongle startup failure.
- Host sees two keyboards: remove the old bond to a former central (e.g. the left half) from the OS Bluetooth settings.
- No trackpad input: check that both halves show connected and that the `reg` values in the right and central overlays match.
- Erratic paths or a freeze followed by a large jump: flash the patched right-half
  and active-central firmware, then test slow straight lines, fast swipes in both directions, edge
  movement, repeated lift/re-touch after a second, and pointer use while typing.
  Verify tap-to-click and layer-3 scrolling still work. Test in the mode you use
  (dongle or left central); latency and pointer speed were not intentionally changed.
  If it persists, record whether right-half keys still respond during the freeze,
  whether it happens on USB power or battery, and whether it occurs away from the
  pad edges. With right-half USB logging enabled, look for `read status`,
  `read packet`, `Invalid STATUS1`, `Invalid relative packet`, or
  `Failed to clear STATUS1` errors. Persistent errors can indicate an I2C, power,
  or physical connection problem; software retries cannot repair a broken link.
- Tracking that only recovers after lifting the finger for 2-3 seconds is not yet a
  confirmed software diagnosis. Use the hardened right-half and active-central builds.
  Keep the pad untouched during startup calibration. If the issue remains, capture
  the diagnostic USB logs and whether right-half keys continue to respond.
  `Pinnacle command complete` records a calibration/reset interrupt, not proof of
  which event caused it; `Pinnacle input delivery blocked` records local queue
  backpressure, not a measurement of host cursor latency. Clean logs do not rule
  out a sensor/overlay/grounding problem or loss farther down the split link.
- Trackpad stops until the right half is power-cycled: the disabled Cirque idle-sleep
  integration is a mitigation, not a confirmed diagnosis. After flashing the right half,
  test continuous pointer use, typing/scrolling together, more than 30 minutes idle
  followed by a right-half keypress and pointer movement, and a battery-powered
  deep-sleep/wake cycle (more than two hours idle, then wake with a key).
  If it recurs, record whether right-half keys still work, whether it followed idle
  or deep sleep, and whether typing on the right half restores the pointer.
  Working right-half keys with a dead pointer helps distinguish a local trackpad
  failure from loss of the whole split connection. Do not reset bonds just for this test.
