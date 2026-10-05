"""Writes the data the Lab's Add-ons tab shows from the add-on manifests.

The tab imports workbench/frontend/src/add-on-catalog.json, so the Lab's image builds without the addons
folder. `python addons/build_catalog.py --write` regenerates it after a manifest changes; `check_addons.py`
fails when it is out of date.
"""

import argparse
import json
import sys
from pathlib import Path

from addon_manifest import ADDONS_DIRECTORY, AddOnFileError, load_add_ons

CATALOG_PATH = ADDONS_DIRECTORY.parent / "workbench" / "frontend" / "src" / "add-on-catalog.json"
_SOURCE_NOTE = "Generated from addons/*/addon.json by addons/build_catalog.py. Do not edit by hand."


def render(add_ons):
    catalog = {"generated_from": _SOURCE_NOTE, "add_ons": [add_on.catalog_entry() for add_on in add_ons]}
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"


def is_current(add_ons, path):
    return path.is_file() and path.read_text(encoding="utf-8") == render(add_ons)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the catalog instead of checking it")
    arguments = parser.parse_args(argv)
    try:
        add_ons = load_add_ons()
    except AddOnFileError as problem:
        print(problem, file=sys.stderr)
        return 1
    if arguments.write:
        Path(CATALOG_PATH).write_text(render(add_ons), encoding="utf-8", newline="\n")
        print(f"Wrote {CATALOG_PATH.relative_to(ADDONS_DIRECTORY.parent)} for {len(add_ons)} add-ons.")
        return 0
    if not is_current(add_ons, CATALOG_PATH):
        print(f"{CATALOG_PATH.name} is out of date. Run: python addons/build_catalog.py --write", file=sys.stderr)
        return 1
    print(f"{CATALOG_PATH.name} matches {len(add_ons)} manifests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
