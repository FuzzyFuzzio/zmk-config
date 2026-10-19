if(CONFIG_ZMK_LAYER_SYNC)
    zephyr_library()
    zephyr_library_include_directories(${CMAKE_SOURCE_DIR}/include)
    # Global so the nice_view_battery shield can include layer_sync.h
    zephyr_include_directories(include)

    zephyr_library_sources(src/behavior_layer_sync.c)
    zephyr_library_sources_ifdef(CONFIG_ZMK_SPLIT_ROLE_CENTRAL src/layer_sync_central.c)
endif()
