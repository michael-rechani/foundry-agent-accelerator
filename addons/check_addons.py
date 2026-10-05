"""Checks every add-on manifest and package in addons/. CI runs this; it contacts nothing.

Reports each problem with the file it is in and exits 1 if there is any. See docs/addon-package-format.md.
"""

import sys

import build_catalog
from addon_manifest import ADDONS_DIRECTORY, AddOnFileError, load_add_ons

# Folders in addons/ that hold no add-on.
_NOT_ADD_ONS = {"testdata", "__pycache__"}


def problems():
    found = [f"{folder.name}/: no addon.json" for folder in sorted(ADDONS_DIRECTORY.iterdir())
             if folder.is_dir() and folder.name not in _NOT_ADD_ONS and not folder.name.startswith(".")
             and not (folder / "addon.json").is_file()]
    try:
        add_ons = load_add_ons(ADDONS_DIRECTORY)
    except AddOnFileError as problem:
        return [*found, str(problem)], []
    if not build_catalog.is_current(add_ons, build_catalog.CATALOG_PATH):
        found.append(f"{build_catalog.CATALOG_PATH.name} is out of date. Run: python addons/build_catalog.py --write")
    return found, add_ons


def main():
    found, add_ons = problems()
    for problem in found:
        print(problem, file=sys.stderr)
    if found:
        return 1
    for add_on in add_ons:
        print(f"{add_on.id}: ok ({add_on.kind}, {'package' if add_on.package else 'card only'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
