import tempfile
import unittest
from pathlib import Path

import check_markdown_links as checker


class MarkdownLinkCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / "docs" / "images").mkdir(parents=True)
        (self.root / "docs" / "images" / "a.svg").write_text("<svg/>", encoding="utf-8")
        self.guide = self.root / "docs" / "guide.md"
        self.guide.write_text(
            "# Guide\n\n## How it works\n\n## How it works\n\n### Use `inspect_case` (default)\n\n"
            '<a id="quick-start"></a>\n\n```md\n## Not a heading\n```\n',
            encoding="utf-8",
        )
        checker._anchor_cache.clear()

    def tearDown(self):
        self.temp.cleanup()

    def check(self, target, source=None):
        return checker.check_target(self.root, source or self.guide, target)

    def test_existing_files_and_anchors_pass(self):
        self.assertIsNone(self.check("images/a.svg"))
        self.assertIsNone(self.check("#how-it-works"))
        self.assertIsNone(self.check("#how-it-works-1"))
        self.assertIsNone(self.check("#use-inspect_case-default"))
        self.assertIsNone(self.check("guide.md#quick-start"))
        self.assertIsNone(self.check("/docs/guide.md#guide"))

    def test_missing_files_and_anchors_fail(self):
        self.assertEqual(self.check("images/b.svg"), "missing file: images/b.svg")
        self.assertEqual(self.check("#missing"), "missing anchor: #missing")
        self.assertEqual(self.check("#not-a-heading"), "missing anchor: #not-a-heading")

    def test_external_and_line_links_are_skipped(self):
        self.assertIsNone(self.check("https://learn.microsoft.com/azure/#nothing"))
        self.assertIsNone(self.check("mailto:someone@example.com"))
        self.assertIsNone(self.check("images/a.svg#L10"))

    def test_targets_cover_markdown_html_and_srcset(self):
        line = (
            '[Guide](guide.md#guide) ![Diagram](<images/a.svg>) <img src="images/a.svg"> '
            '<source srcset="images/a-dark.svg 1x, images/b-dark.svg 2x">'
        )
        self.assertEqual(
            checker.targets(line),
            ["guide.md#guide", "images/a.svg", "images/a.svg", "images/a-dark.svg", "images/b-dark.svg"],
        )

    def test_code_is_not_checked(self):
        lines = checker.prose_lines("`[x](missing.md)`\n```\n[y](missing.md)\n```\n[z](ok.md)\n")
        self.assertEqual(lines, [(1, ""), (5, "[z](ok.md)")])


if __name__ == "__main__":
    unittest.main()
