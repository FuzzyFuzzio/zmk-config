if(NOT CONFIG_INPUT_PINNACLE AND NOT CONFIG_ZMK_TRACKPAD_RELIABLE_SPLIT)
  return()
endif()

find_package(Git REQUIRED)
function(trackpad_apply_patch directory patch)
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${patch}")
  execute_process(
    COMMAND "${GIT_EXECUTABLE}" "--work-tree=${directory}" apply --check "${patch}"
    WORKING_DIRECTORY "${directory}"
    RESULT_VARIABLE result ERROR_VARIABLE error
  )
  if(NOT result EQUAL 0)
    message(FATAL_ERROR "Trackpad patch no longer applies: ${error}")
  endif()
  execute_process(
    COMMAND "${GIT_EXECUTABLE}" "--work-tree=${directory}" apply "${patch}"
    WORKING_DIRECTORY "${directory}"
    RESULT_VARIABLE result ERROR_VARIABLE error
  )
  if(NOT result EQUAL 0)
    message(FATAL_ERROR "Failed to apply trackpad patch: ${error}")
  endif()
endfunction()

function(trackpad_finalize_app_sources)
  get_target_property(patched app ZMK_TRACKPAD_PATCH_DIR)
  get_target_property(original_root app ZMK_TRACKPAD_SOURCE_DIR)
  get_target_property(replacements app ZMK_TRACKPAD_REPLACEMENTS)
  get_target_property(split_init app ZMK_TRACKPAD_SPLIT_INIT)
  get_target_property(base app SOURCE_DIR)
  get_target_property(sources app SOURCES)
  list(LENGTH sources source_count)
  math(EXPR last_source "${source_count} - 1")
  foreach(relative IN LISTS replacements)
    set(found 0)
    foreach(index RANGE 0 ${last_source})
      list(GET sources ${index} source)
      get_filename_component(absolute "${source}" ABSOLUTE BASE_DIR "${base}")
      if(absolute STREQUAL "${original_root}/${relative}")
        list(REMOVE_AT sources ${index})
        list(INSERT sources ${index} "${patched}/${relative}")
        math(EXPR found "${found} + 1")
      endif()
    endforeach()
    if(NOT found EQUAL 1)
      message(FATAL_ERROR "Expected exactly one original trackpad source ${relative}, found ${found}")
    endif()
  endforeach()
  set_property(TARGET app PROPERTY SOURCES "${sources}")

  add_custom_target(trackpad_init_order ALL
    COMMAND "${PYTHON_EXECUTABLE}" "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/check_init_order.py"
            --elf "$<TARGET_FILE:zephyr_final>" --split-init "${split_init}"
    DEPENDS zephyr_final "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/check_init_order.py"
    VERBATIM
  )
endfunction()

if(CONFIG_INPUT_PINNACLE)
  set(upstream "${ZEPHYR_CIRQUE_INPUT_MODULE_MODULE_DIR}/drivers/input")
  set(patched "${CMAKE_CURRENT_BINARY_DIR}/driver")

  # Patch a private build copy; never modify west's shared module checkout.
  file(MAKE_DIRECTORY "${patched}")
  configure_file("${upstream}/input_pinnacle.c" "${patched}/input_pinnacle.c" COPYONLY)
  configure_file("${upstream}/input_pinnacle.h" "${patched}/input_pinnacle.h" COPYONLY)
  trackpad_apply_patch("${patched}" "${CMAKE_CURRENT_SOURCE_DIR}/cirque-pinnacle.patch")

  get_target_property(input_sources drivers__input SOURCES)
  set(original "${upstream}/input_pinnacle.c")
  list(FIND input_sources "${original}" index)
  if(index LESS 0)
    message(FATAL_ERROR "Pinned Cirque driver source is missing from drivers__input")
  endif()
  list(REMOVE_AT input_sources ${index})
  list(INSERT input_sources ${index} "${patched}/input_pinnacle.c")
  set_property(TARGET drivers__input PROPERTY SOURCES "${input_sources}")
endif()

if(CONFIG_ZMK_TRACKPAD_RELIABLE_SPLIT)
  set(patched "${CMAKE_CURRENT_BINARY_DIR}/zmk")
  set(sources src/pointing/input_split.c src/pointing/input_listener.c src/split/bluetooth/service.c
              src/split/bluetooth/central.c)
  foreach(source IN LISTS sources)
    configure_file("${APPLICATION_SOURCE_DIR}/${source}" "${patched}/${source}" COPYONLY)
  endforeach()
  file(GLOB headers "${APPLICATION_SOURCE_DIR}/src/split/bluetooth/*.h")
  foreach(header IN LISTS headers)
    get_filename_component(name "${header}" NAME)
    configure_file("${header}" "${patched}/src/split/bluetooth/${name}" COPYONLY)
  endforeach()
  trackpad_apply_patch("${patched}" "${CMAKE_CURRENT_SOURCE_DIR}/zmk-input-frames.patch")
  set(replacements src/pointing/input_split.c)
  if(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    list(APPEND replacements src/pointing/input_listener.c src/split/bluetooth/central.c)
    set(split_init zmk_split_bt_central_init)
  else()
    list(APPEND replacements src/split/bluetooth/service.c)
    set(split_init zmk_peripheral_ble_init)
  endif()
  set_property(TARGET app PROPERTY ZMK_TRACKPAD_PATCH_DIR "${patched}")
  set_property(TARGET app PROPERTY ZMK_TRACKPAD_SOURCE_DIR "${APPLICATION_SOURCE_DIR}")
  set_property(TARGET app PROPERTY ZMK_TRACKPAD_REPLACEMENTS "${replacements}")
  set_property(TARGET app PROPERTY ZMK_TRACKPAD_SPLIT_INIT "${split_init}")
  # Same-priority SYS_INIT order follows object link order. Replace in place, never prepend.
  cmake_language(DEFER DIRECTORY "${APPLICATION_SOURCE_DIR}" CALL trackpad_finalize_app_sources)
  target_sources(app PRIVATE src/trackpad_frames.c)
  zephyr_include_directories(include)
endif()
