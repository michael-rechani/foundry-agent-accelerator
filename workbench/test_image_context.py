import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parent


class ImageContextTests(unittest.TestCase):
    """The Dockerfile, .dockerignore, and build.ps1 each list the image's files and must agree."""

    def test_every_copied_backend_file_is_allowed_by_dockerignore(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        allowed = {line.strip()[1:] for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
                   if line.strip().startswith("!")}
        copied = set()
        for sources in re.findall(r"^COPY (?!--)(.+) \./$", dockerfile, re.MULTILINE):
            copied.update(name for name in sources.split() if "/" not in name)
        self.assertIn("library_preview.py", copied)
        self.assertEqual(sorted(copied - allowed), [], "Add these files to workbench/.dockerignore")

    def test_build_script_stages_every_copied_backend_file(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        script = (ROOT / "build.ps1").read_text(encoding="utf-8")
        staged = set(re.findall(r'"([A-Za-z_.]+)"', re.search(r"foreach \(\$name in @\(([^)]*)\)\)", script).group(1)))
        copied = set()
        for sources in re.findall(r"^COPY (?!--)(.+) \./$", dockerfile, re.MULTILINE):
            copied.update(name for name in sources.split() if "/" not in name)
        self.assertEqual(sorted(copied - staged), [], "Add these files to workbench/build.ps1")


if __name__ == "__main__":
    unittest.main()