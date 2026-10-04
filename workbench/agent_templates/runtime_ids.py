"""Writes the hosted runtime's list of library agent ids from `agents/*.json`.

The runtime ships inside a created agent's package (`main.py`, `demo_tools.py`, `requirements.txt`) and can't
import the catalog, so `agent_runtime/demo_tools.py` holds the ids it accepts as a literal. That literal is
generated, not edited by hand. From the `workbench` directory:

    python -m agent_templates.runtime_ids           # rewrite the literal from the catalog
    python -m agent_templates.runtime_ids --check   # exit 1 if it is out of date, changing nothing

The rewrite changes only the literal, and leaves the file's line endings alone. A test runs the check.
"""

import re
import sys
import textwrap
from pathlib import Path

from .catalog import TEMPLATES

DEMO_TOOLS = Path(__file__).resolve().parents[1] / "agent_runtime" / "demo_tools.py"
LINE_WIDTH = 120
_LITERAL = re.compile(r"^TEMPLATE_IDS = frozenset\(\{\r?\n.*?\r?\n\}\)\r?\n", re.MULTILINE | re.DOTALL)


def render(identifiers, newline="\n"):
    """The `TEMPLATE_IDS` statement for `identifiers`, in the order given."""
    words = ", ".join(f'"{identifier}"' for identifier in identifiers) + ","
    rows = textwrap.wrap(words, width=LINE_WIDTH, initial_indent="    ", subsequent_indent="    ",
                         break_long_words=False, break_on_hyphens=False)
    return newline.join(["TEMPLATE_IDS = frozenset({", *rows, "})"]) + newline


def updated(source, identifiers):
    """`source` with its `TEMPLATE_IDS` statement written from `identifiers`."""
    found = _LITERAL.findall(source)
    if len(found) != 1:
        raise ValueError("demo_tools.py must hold exactly one 'TEMPLATE_IDS = frozenset({ ... })' statement")
    newline = "\r\n" if "\r\n" in found[0] else "\n"
    return _LITERAL.sub(lambda _: render(identifiers, newline), source)


def main(arguments, path=DEMO_TOOLS, identifiers=None):
    unknown = [argument for argument in arguments if argument != "--check"]
    if unknown:
        print(f"Unknown argument {unknown[0]}. Use --check to test without writing.", file=sys.stderr)
        return 2
    # `newline=""` keeps the file's own line endings, so the rewrite is byte-for-byte except the literal.
    with path.open(encoding="utf-8", newline="") as stream:
        source = stream.read()
    expected = updated(source, TEMPLATES if identifiers is None else identifiers)
    if expected == source:
        print("TEMPLATE_IDS in agent_runtime/demo_tools.py is up to date.")
        return 0
    if "--check" in arguments:
        print("TEMPLATE_IDS in agent_runtime/demo_tools.py is out of date. From the workbench directory run: "
              "python -m agent_templates.runtime_ids", file=sys.stderr)
        return 1
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(expected)
    print("Rewrote TEMPLATE_IDS in agent_runtime/demo_tools.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
