# Dongle / split BLE bond recovery sources.
#
# Both translation units are guarded by their own Kconfig and by ZMK/BT
# Kconfigs so they compile out completely on builds that don't need them
# (notably the hillside_view_left_central / no-dongle image).

if(CONFIG_DONGLE_BOND_AUTOHEAL OR CONFIG_PERIPHERAL_BOOT_BONDCLEAR)
    zephyr_library()

    zephyr_library_sources_ifdef(CONFIG_DONGLE_BOND_AUTOHEAL
        src/dongle_bond_autoheal.c)

    zephyr_library_sources_ifdef(CONFIG_PERIPHERAL_BOOT_BONDCLEAR
        src/peripheral_boot_bondclear.c)
endif()
