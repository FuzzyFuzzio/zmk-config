# Dongle / split BLE bond recovery sources.
#
# Both translation units are guarded by their own Kconfig and by ZMK/BT
# Kconfigs so they compile out completely on builds that don't need them
# (notably the hillside_view_left_central / no-dongle image).

if(CONFIG_DONGLE_BOND_AUTOHEAL OR CONFIG_PERIPHERAL_BOOT_BONDCLEAR)
    zephyr_library()

    # ZMK app headers (zmk/event_manager.h, zmk/events/*.h) live in the
    # ZMK app's include/ directory, which isn't propagated to module
    # libraries by default. In ZMK builds CMAKE_SOURCE_DIR is `zmk/app`,
    # so ${CMAKE_SOURCE_DIR}/include resolves to ZMK's public app headers.
    zephyr_library_include_directories(${CMAKE_SOURCE_DIR}/include)

    zephyr_library_sources_ifdef(CONFIG_DONGLE_BOND_AUTOHEAL
        src/dongle_bond_autoheal.c)

    zephyr_library_sources_ifdef(CONFIG_PERIPHERAL_BOOT_BONDCLEAR
        src/peripheral_boot_bondclear.c)
endif()
