import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from agent_runtime.demo_tools import TEMPLATE_IDS
from agent_templates import TEMPLATES
from agent_templates import runtime_ids

STALE = '"""Sample tools."""\n\nTEMPLATE_IDS = frozenset({\n    "first", "gone",\n})\n_EXAMPLE = "kept"\n'


def run(arguments, path, identifiers):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = runtime_ids.main(arguments, path=path, identifiers=identifiers)
    return code, out.getvalue(), err.getvalue()


class RuntimeIdsTests(unittest.TestCase):
    def test_the_runtime_list_matches_the_library(self):
        code, _, problem = run(["--check"], runtime_ids.DEMO_TOOLS, TEMPLATES)
        self.assertEqual(code, 0, problem)
        self.assertEqual(TEMPLATE_IDS, frozenset(TEMPLATES))

    def test_adding_an_agent_file_changes_the_generated_list_and_nothing_else(self):
        source = runtime_ids.DEMO_TOOLS.read_bytes().decode("utf-8")
        longer = runtime_ids.updated(source, [*TEMPLATES, "a-new-text-only-agent"])
        self.assertIn('"a-new-text-only-agent",', longer)
        self.assertEqual(runtime_ids.updated(longer, TEMPLATES), source)

    def test_a_stale_list_fails_the_check_until_it_is_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo_tools.py"
            path.write_bytes(STALE.encode("utf-8"))
            code, _, problem = run(["--check"], path, ["first", "second"])
            self.assertEqual(code, 1)
            self.assertIn("python -m agent_templates.runtime_ids", problem)
            self.assertEqual(path.read_bytes().decode("utf-8"), STALE)
            code, message, _ = run([], path, ["first", "second"])
            self.assertEqual((code, message), (0, "Rewrote TEMPLATE_IDS in agent_runtime/demo_tools.py.\n"))
            self.assertEqual(
                path.read_bytes().decode("utf-8"),
                STALE.replace('"first", "gone",', '"first", "second",'),
            )
            self.assertEqual(run(["--check"], path, ["first", "second"])[0], 0)

    def test_the_rewrite_keeps_the_files_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo_tools.py"
            path.write_bytes(STALE.replace("\n", "\r\n").encode("utf-8"))
            self.assertEqual(run([], path, ["first", "second"])[0], 0)
            written = path.read_bytes()
            self.assertEqual(written.count(b"\r\n"), written.count(b"\n"))
            self.assertIn(b'"first", "second",\r\n', written)

    def test_the_list_wraps_long_ids_without_splitting_them(self):
        rows = runtime_ids.render([f"agent-number-{number}-with-a-long-name" for number in range(12)]).splitlines()
        self.assertTrue(all(len(row) <= runtime_ids.LINE_WIDTH for row in rows))
        self.assertGreater(len(rows), 3)
        self.assertTrue(all(row.endswith(",") for row in rows[1:-1]))

    def test_a_file_without_exactly_one_list_is_refused(self):
        for source in ("x = 1\n", STALE + STALE):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    runtime_ids.updated(source, ["first"])

    def test_an_unknown_argument_is_refused(self):
        code, _, problem = run(["--fix"], runtime_ids.DEMO_TOOLS, TEMPLATES)
        self.assertEqual(code, 2)
        self.assertIn("--fix", problem)


if __name__ == "__main__":
    unittest.main()
