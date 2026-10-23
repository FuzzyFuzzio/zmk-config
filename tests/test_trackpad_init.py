"""Regress source registration and the real settings-handler loss behind failed BLE links."""

import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_trackpad_frames import ROOT
from test_trackpad_split import function_source


spec = importlib.util.spec_from_file_location(
    "trackpad_init_check", ROOT / "trackpad" / "check_init_order.py"
)
init_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init_check)


CMAKE = r"""
cmake_minimum_required(VERSION 3.20)
project(trackpad_source_order NONE)
set(APPLICATION_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
set(CONFIG_ZMK_TRACKPAD_RELIABLE_SPLIT TRUE)
set(CONFIG_ZMK_SPLIT_ROLE_CENTRAL @CENTRAL@)
file(TO_CMAKE_PATH [[@ROOT@]] repository)
file(TO_CMAKE_PATH [[@PYTHON@]] PYTHON_EXECUTABLE)
add_custom_target(app)
add_executable(zephyr_final IMPORTED GLOBAL)
set_property(TARGET zephyr_final PROPERTY IMPORTED_LOCATION "${CMAKE_BINARY_DIR}/not-built.elf")
function(zephyr_include_directories)
endfunction()
add_subdirectory("${repository}/trackpad" "${CMAKE_BINARY_DIR}/trackpad")
# Mirror ZMK: module code runs before application sources are registered.
target_sources(app PRIVATE src/behaviors/behavior_reset.c
                           "${APPLICATION_SOURCE_DIR}/src/pointing/input_split.c")
if(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
  target_sources(app PRIVATE src/ble.c "${APPLICATION_SOURCE_DIR}/src/pointing/input_listener.c"
                            "${APPLICATION_SOURCE_DIR}/src/split/bluetooth/central.c")
else()
  target_sources(app PRIVATE "${APPLICATION_SOURCE_DIR}/src/split/bluetooth/service.c"
                            "${APPLICATION_SOURCE_DIR}/src/split/bluetooth/peripheral.c")
endif()
function(check_source_order)
  get_target_property(sources app SOURCES)
  get_target_property(base app SOURCE_DIR)
  set(active)
  foreach(source IN LISTS sources)
    get_filename_component(absolute "${source}" ABSOLUTE BASE_DIR "${base}")
    get_source_file_property(header "${absolute}" DIRECTORY "${base}" HEADER_FILE_ONLY)
    if(NOT header)
      list(APPEND active "${absolute}")
    endif()
  endforeach()
  set(expected "${repository}/trackpad/src/trackpad_frames.c"
               "${APPLICATION_SOURCE_DIR}/src/behaviors/behavior_reset.c"
               "${CMAKE_BINARY_DIR}/trackpad/zmk/src/pointing/input_split.c")
  if(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    list(APPEND expected "${APPLICATION_SOURCE_DIR}/src/ble.c"
                         "${CMAKE_BINARY_DIR}/trackpad/zmk/src/pointing/input_listener.c"
                         "${CMAKE_BINARY_DIR}/trackpad/zmk/src/split/bluetooth/central.c")
  else()
    list(APPEND expected "${CMAKE_BINARY_DIR}/trackpad/zmk/src/split/bluetooth/service.c"
                         "${APPLICATION_SOURCE_DIR}/src/split/bluetooth/peripheral.c")
  endif()
  if(NOT "${active}" STREQUAL "${expected}")
    message(FATAL_ERROR "Patched sources did not preserve their original registration positions")
  endif()
  list(FIND active "${APPLICATION_SOURCE_DIR}/src/behaviors/behavior_reset.c" anchor)
  list(FIND active "${CMAKE_BINARY_DIR}/trackpad/zmk/src/pointing/input_split.c" input)
  if(anchor LESS 0 OR input LESS 0 OR NOT anchor LESS input)
    message(FATAL_ERROR "Patched source was prepended ahead of original application sources")
  endif()
  if(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    set(before "${APPLICATION_SOURCE_DIR}/src/ble.c")
  else()
    set(before "${CMAKE_BINARY_DIR}/trackpad/zmk/src/split/bluetooth/service.c")
  endif()
  list(FIND active "${before}" first)
  list(FIND active "${CMAKE_BINARY_DIR}/trackpad/zmk/src/split/bluetooth/@SPLIT_FILE@" split)
  if(CONFIG_ZMK_SPLIT_ROLE_CENTRAL AND (first LESS 0 OR split LESS 0 OR NOT first LESS split))
    message(FATAL_ERROR "Patched split startup source moved before Bluetooth core")
  elseif(NOT CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    list(FIND active "${APPLICATION_SOURCE_DIR}/src/split/bluetooth/peripheral.c" peripheral)
    if(first LESS 0 OR peripheral LESS 0 OR NOT first LESS peripheral)
      message(FATAL_ERROR "Peripheral source moved before its notification service")
    endif()
  endif()
  list(FIND active "${APPLICATION_SOURCE_DIR}/src/split/bluetooth/@SPLIT_FILE@" original)
  if(NOT original EQUAL -1)
    message(FATAL_ERROR "Original and patched split sources are both active")
  endif()
endfunction()
cmake_language(DEFER CALL check_source_order)
"""

DRIVER_CMAKE = r"""
cmake_minimum_required(VERSION 3.20)
project(trackpad_driver_order NONE)
set(CONFIG_INPUT_PINNACLE TRUE)
set(CONFIG_ZMK_TRACKPAD_RELIABLE_SPLIT FALSE)
file(TO_CMAKE_PATH [[@ROOT@]] repository)
file(TO_CMAKE_PATH [[@CIRQUE@]] ZEPHYR_CIRQUE_INPUT_MODULE_MODULE_DIR)
add_custom_target(drivers__input)
target_sources(drivers__input PRIVATE before.c
  "${ZEPHYR_CIRQUE_INPUT_MODULE_MODULE_DIR}/drivers/input/input_pinnacle.c" after.c)
add_subdirectory("${repository}/trackpad" "${CMAKE_BINARY_DIR}/trackpad")
get_target_property(sources drivers__input SOURCES)
set(actual)
foreach(source IN LISTS sources)
  get_filename_component(absolute "${source}" ABSOLUTE BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
  list(APPEND actual "${absolute}")
endforeach()
set(expected "${CMAKE_CURRENT_SOURCE_DIR}/before.c"
             "${CMAKE_BINARY_DIR}/trackpad/driver/input_pinnacle.c"
             "${CMAKE_CURRENT_SOURCE_DIR}/after.c")
if(NOT "${actual}" STREQUAL "${expected}")
  message(FATAL_ERROR "Patched driver changed original library source order: ${actual}")
endif()
"""

SETTINGS_STUB = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#include <string.h>
#define CONFIG_SETTINGS_DYNAMIC_HANDLERS 1
#define K_FOREVER -1
struct node { struct node *next; };
struct list { struct node *head, *tail; };
struct settings_handler { struct node node; const char *name; int (*h_commit)(void); };
static struct list settings_handlers;
static int settings_lock;
static void k_mutex_lock(int *lock, int timeout) {}
static void k_mutex_unlock(int *lock) {}
static void settings_store_init(void) {}
static void sys_slist_init(struct list *list) { list->head = list->tail = NULL; }
static void sys_slist_append(struct list *list, struct node *node) {
    node->next = NULL;
    if (list->tail) { list->tail->next = node; } else { list->head = node; }
    list->tail = node;
}
#define STRUCT_SECTION_FOREACH(type, ch) \
    for (struct settings_handler *ch = NULL; ch; ch = NULL)
#define SYS_SLIST_FOR_EACH_CONTAINER(list, ch, member) \
    for (struct node *item = (list)->head; \
         item && ((ch) = (struct settings_handler *)((char *)item - offsetof(struct settings_handler, member)), true); \
         item = item->next)
static bool settings_loaded;
static int callbacks;
struct zmk_split_transport_central { int unused; };
struct zmk_split_transport_status { bool available; };
static struct zmk_split_transport_central bt_central;
static struct zmk_split_transport_status split_central_bt_get_status(void) {
    return (struct zmk_split_transport_status){.available=settings_loaded};
}
static int on_status(const struct zmk_split_transport_central *central,
                     struct zmk_split_transport_status status) {
    assert(status.available); callbacks++; return 0;
}
static int (*transport_status_cb)(const struct zmk_split_transport_central *,
                                   struct zmk_split_transport_status) = on_status;
"""

SETTINGS_MAIN = r"""
static void load_settings(void) {
    struct settings_handler *handler;
    SYS_SLIST_FOR_EACH_CONTAINER(&settings_handlers, handler, node) {
        if (handler->h_commit) { handler->h_commit(); }
    }
}
int main(void) {
    struct settings_handler central = {.name="ble_central", .h_commit=finish_init};
    struct settings_handler profiles = {.name="ble"};
    /* Broken link order: split init first, then bt_enable initializes settings. */
    assert(settings_register(&central) == 0);
    settings_init();
    assert(settings_register(&profiles) == 0);
    load_settings();
    assert(!settings_loaded && callbacks == 0);
    /* Original/fixed link order: bt_enable first, then split settings registration. */
    settings_init();
    assert(settings_register(&profiles) == 0);
    assert(settings_register(&central) == 0);
    load_settings();
    assert(settings_loaded && callbacks == 1);
    return 0;
}
"""


class TrackpadInitTests(unittest.TestCase):
    def test_driver_library_source_order(self):
        module = os.environ.get("CIRQUE_MODULE_DIR")
        self.assertTrue(module, "Set CIRQUE_MODULE_DIR to the pinned Cirque checkout")
        with tempfile.TemporaryDirectory(prefix="zmk-driver-order-") as directory:
            temp = Path(directory)
            cmake = DRIVER_CMAKE.replace("@ROOT@", str(ROOT)).replace("@CIRQUE@", module)
            (temp / "CMakeLists.txt").write_text(cmake, encoding="ascii")
            (temp / "before.c").write_text("", encoding="ascii")
            (temp / "after.c").write_text("", encoding="ascii")
            result = subprocess.run(
                ["cmake", "-G", "Ninja", "-S", str(temp), "-B", str(temp / "build")],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_elf_order_guard(self):
        for split, before in init_check.PREDECESSORS.items():
            with self.subTest(split=split):
                init_check.check_init_order(
                    {"__init_" + before: 100, "__init_" + split: 108}, split
                )
                with self.assertRaisesRegex(ValueError, "initializes before"):
                    init_check.check_init_order(
                        {"__init_" + before: 108, "__init_" + split: 100}, split
                    )
                with self.assertRaisesRegex(ValueError, "Missing"):
                    init_check.check_init_order({}, split)

    def test_real_module_source_order(self):
        module = os.environ.get("ZMK_MODULE_DIR")
        self.assertTrue(module, "Set ZMK_MODULE_DIR to the pinned ZMK checkout")
        with tempfile.TemporaryDirectory(prefix="zmk-init-cmake-") as directory:
            temp = Path(directory)
            for central in (False, True):
                app = temp / str(central) / "app"
                for name in (
                    "src/ble.c", "src/behaviors/behavior_reset.c",
                    "src/pointing/input_split.c", "src/pointing/input_listener.c",
                    "src/split/bluetooth/central.c", "src/split/bluetooth/service.c",
                    "src/split/bluetooth/peripheral.c",
                ):
                    target = app / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(Path(module) / "app" / name, target)
                cmake = CMAKE.replace("@ROOT@", str(ROOT)).replace("@PYTHON@", sys.executable)
                cmake = cmake.replace("@CENTRAL@", "TRUE" if central else "FALSE")
                cmake = cmake.replace("@SPLIT_FILE@", "central.c" if central else "service.c")
                (app / "CMakeLists.txt").write_text(cmake, encoding="ascii")
                result = subprocess.run(
                    ["cmake", "-G", "Ninja", "-S", str(app), "-B", str(app.parent / "build")],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_settings_registration_loss(self):
        zmk = os.environ.get("ZMK_MODULE_DIR")
        self.assertTrue(zmk, "Set ZMK_MODULE_DIR to the pinned ZMK checkout")
        zephyr = Path(os.environ.get("ZEPHYR_MODULE_DIR", str(Path(zmk).parent / "zephyr")))
        settings_path = zephyr / "subsys" / "settings" / "src" / "settings.c"
        self.assertTrue(
            settings_path.is_file(),
            "Set ZEPHYR_MODULE_DIR to the Zephyr checkout selected by ZMK's manifest",
        )
        settings = settings_path.read_text()
        central = (Path(zmk) / "app" / "src" / "split" / "bluetooth" / "central.c").read_text()
        central = central[central.rindex("static int finish_init()"):]
        source = SETTINGS_STUB + function_source(settings, "settings_init", "void")
        source += function_source(settings, "settings_register", "int")
        source += function_source(central, "finish_init", "static int") + SETTINGS_MAIN
        compiler = (
            shlex.split(os.environ["CC"], posix=os.name != "nt") if os.environ.get("CC")
            else ["cc"] if shutil.which("cc")
            else [sys.executable, "-m", "ziglang", "cc"]
        )
        with tempfile.TemporaryDirectory(prefix="zmk-settings-init-") as directory:
            temp = Path(directory)
            (temp / "test.c").write_text(source, encoding="ascii")
            executable = temp / ("settings.exe" if os.name == "nt" else "settings")
            build = subprocess.run(
                compiler + ["-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                            str(temp / "test.c"), "-o", str(executable)],
                capture_output=True, text=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
