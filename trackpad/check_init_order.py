"""Validate linked Bluetooth startup dependencies after source replacement."""

import argparse
from pathlib import Path


PREDECESSORS = {
    "zmk_split_bt_central_init": "zmk_ble_init",
    "zmk_peripheral_ble_init": "service_init",
}


def check_init_order(addresses, split_init):
    if split_init not in PREDECESSORS:
        raise ValueError(f"Unsupported split initialization entry: {split_init}")
    predecessor = PREDECESSORS[split_init]
    before = "__init_" + predecessor
    split = "__init_" + split_init
    for name in (before, split):
        if name not in addresses:
            raise ValueError(f"Missing firmware initialization entry: {name}")
    if addresses[before] >= addresses[split]:
        reason = (
            "bt_enable() will erase the split settings handler and the transport will never become available"
            if predecessor == "zmk_ble_init"
            else "the peripheral notification service is not initialized"
        )
        raise ValueError(f"{split_init} initializes before {predecessor}; {reason}")
    return predecessor


def read_init_addresses(path):
    # pyelftools is already required by Zephyr's firmware build tools.
    from elftools.elf.elffile import ELFFile

    with path.open("rb") as stream:
        symbols = ELFFile(stream).get_section_by_name(".symtab")
        if symbols is None:
            raise ValueError("Firmware has no ELF symbol table")
        required = {"__init_" + name for name in (*PREDECESSORS, *PREDECESSORS.values())}
        addresses = {}
        for symbol in symbols.iter_symbols():
            if symbol.name in required:
                if symbol.name in addresses:
                    raise ValueError(f"Ambiguous firmware initialization entry: {symbol.name}")
                addresses[symbol.name] = symbol["st_value"]
        return addresses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument(
        "--split-init",
        choices=("zmk_split_bt_central_init", "zmk_peripheral_ble_init"),
        required=True,
    )
    arguments = parser.parse_args()
    try:
        predecessor = check_init_order(read_init_addresses(arguments.elf), arguments.split_init)
    except ValueError as error:
        parser.exit(1, f"Trackpad startup-order check failed: {error}\n")
    print(f"Verified startup order: {predecessor} before {arguments.split_init}")


if __name__ == "__main__":
    main()
