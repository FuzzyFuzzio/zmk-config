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
if(NOT original IN_LIST input_sources)
  message(FATAL_ERROR "Pinned Cirque driver source is missing from drivers__input")
endif()
list(REMOVE_ITEM input_sources "${original}")
set_property(TARGET drivers__input PROPERTY SOURCES "${input_sources}")
target_sources(drivers__input PRIVATE "${patched}/input_pinnacle.c")
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
  # ZMK registers app sources after module CMake runs. Mark the originals before registration.
  set_source_files_properties("${APPLICATION_SOURCE_DIR}/src/pointing/input_split.c"
    DIRECTORY "${APPLICATION_SOURCE_DIR}" PROPERTIES HEADER_FILE_ONLY TRUE)
  target_sources(app PRIVATE "${patched}/src/pointing/input_split.c")
  if(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    set_source_files_properties("${APPLICATION_SOURCE_DIR}/src/pointing/input_listener.c"
      DIRECTORY "${APPLICATION_SOURCE_DIR}" PROPERTIES HEADER_FILE_ONLY TRUE)
    target_sources(app PRIVATE "${patched}/src/pointing/input_listener.c")
    set(source src/split/bluetooth/central.c)
  else()
    set(source src/split/bluetooth/service.c)
  endif()
  set_source_files_properties("${APPLICATION_SOURCE_DIR}/${source}"
    DIRECTORY "${APPLICATION_SOURCE_DIR}" PROPERTIES HEADER_FILE_ONLY TRUE)
  target_sources(app PRIVATE "${patched}/${source}" src/trackpad_frames.c)
  zephyr_include_directories(include)
endif()
