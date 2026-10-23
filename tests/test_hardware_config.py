"""Check both layout transforms against actual six-column-per-half scan coordinates."""

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_trackpad_frames import ROOT
from test_trackpad_split import function_source


def transform_definitions():
    path = ROOT / "boards" / "shields" / "hillside_view" / "hillside_view.dtsi"
    source = path.read_text()
    transforms = {}
    for name in ("default_transform", "five_column_transform"):
        body = re.search(name + r":\s*\w+\s*\{(.*?)\n\s*\};", source, re.S).group(1)
        columns = int(re.search(r"columns\s*=\s*<(\d+)>", body).group(1))
        rows = int(re.search(r"rows\s*=\s*<(\d+)>", body).group(1))
        mapping = re.search(r"\bmap\s*=\s*<(.*?)>", body, re.S).group(1)
        coordinates = [tuple(map(int, pair)) for pair in re.findall(r"RC\((\d+),\s*(\d+)\)", mapping)]
        transforms[name] = (rows, columns, coordinates)
    return transforms


class HardwareConfigTests(unittest.TestCase):
    def test_all_firmware_roles_are_exposed_in_metadata(self):
        source = (
            ROOT / "boards" / "shields" / "hillside_view" / "hillside_view.zmk.yml"
        ).read_text().split("siblings:", 1)[1]
        siblings = set(re.findall(r"(?m)^\s+-\s+(hillside_view_[a-z_]+)\s*$", source))
        self.assertEqual(siblings, {
            "hillside_view_left", "hillside_view_right", "hillside_view_left_central",
        })

    def test_layout_and_keymap_cardinality(self):
        transforms = transform_definitions()
        editor = json.loads((ROOT / "config" / "hillside_view.json").read_text())
        for name, (_, _, coordinates) in transforms.items():
            self.assertEqual(len(coordinates), len(editor["layouts"][name]["layout"]))
            self.assertEqual(len(coordinates), len(set(coordinates)))
        keymap = (ROOT / "config" / "hillside_view.keymap").read_text().split("keymap {", 1)[1]
        layers = re.findall(r"(?ms)^\s*bindings\s*=\s*<(.*?)>\s*;", keymap)
        self.assertEqual(len(layers), 5)
        for bindings in layers:
            self.assertEqual(bindings.count("&"), len(transforms["default_transform"][2]))

    def test_real_matrix_transform_for_both_halves(self):
        module = os.environ.get("ZMK_MODULE_DIR")
        self.assertTrue(module, "Set ZMK_MODULE_DIR to the pinned ZMK checkout")
        source = (Path(module) / "app" / "src" / "matrix_transform.c").read_text()
        structure = re.search(r"struct zmk_matrix_transform \{.*?\n\};", source, re.S).group(0)
        convert = function_source(source, "zmk_matrix_transform_row_column_to_position", "int32_t")
        overlay = (
            ROOT / "boards" / "shields" / "hillside_view" / "hillside_view_right.overlay"
        ).read_text()
        tests = []
        tables = []
        for index, (name, (rows, columns, coordinates)) in enumerate(transform_definitions().items()):
            right = re.search(r"&" + name + r"\s*\{(.*?)\};", overlay, re.S)
            offset = (
                int(re.search(r"col-offset\s*=\s*<(\d+)>", right.group(1)).group(1))
                if right else 0
            )
            lookup = [0] * (max(row * columns + column for row, column in coordinates) + 1)
            for position, (row, column) in enumerate(coordinates):
                lookup[row * columns + column] = position + 1
            expected = [
                coordinates.index((row, column)) if (row, column) in coordinates else "-EINVAL"
                for row in range(4) for column in range(12)
            ]
            tables.append(
                f"static const uint32_t lookup_{index}[] = "
                "{" + ",".join(map(str, lookup)) + "};\n"
                f"static const int expected_{index}[] = "
                "{" + ",".join(map(str, expected)) + "};\n"
            )
            tests.append(f"""
    {{
        struct zmk_matrix_transform mt = {{
            .lookup_table=lookup_{index}, .len=sizeof(lookup_{index})/sizeof(uint32_t),
            .rows={rows}, .columns={columns},
        }};
        for (int half = 0; half < 2; half++) {{
            mt.col_offset = half ? {offset} : 0;
            for (int row = 0; row < 4; row++) {{
                for (int column = 0; column < 6; column++) {{
                    int expected = expected_{index}[row * 12 + column + half * 6];
                    int actual = zmk_matrix_transform_row_column_to_position(&mt, row, column);
                    if (actual != expected) {{
                        fprintf(stderr, "{name}: half %d row %d col %d -> %d, expected %d\\n",
                                half, row, column, actual, expected);
                        return 1;
                    }}
                }}
            }}
        }}
    }}
""")
        harness = (
            "#include <stdint.h>\n#include <stddef.h>\n#include <errno.h>\n#include <stdio.h>\n"
            "#define INDEX_OFFSET 1\n" + structure +
            "\ntypedef const struct zmk_matrix_transform *zmk_matrix_transform_t;\n" +
            convert + "".join(tables) + "\nint main(void) {\n" + "".join(tests) + "return 0;\n}\n"
        )
        compiler = (
            shlex.split(os.environ["CC"], posix=os.name != "nt") if os.environ.get("CC")
            else ["cc"] if shutil.which("cc")
            else [sys.executable, "-m", "ziglang", "cc"]
        )
        with tempfile.TemporaryDirectory(prefix="zmk-matrix-contract-") as directory:
            temp = Path(directory)
            (temp / "test.c").write_text(harness, encoding="ascii")
            executable = temp / ("matrix.exe" if os.name == "nt" else "matrix")
            build = subprocess.run(
                compiler + ["-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(temp / "test.c"), "-o", str(executable)],
                capture_output=True, text=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
