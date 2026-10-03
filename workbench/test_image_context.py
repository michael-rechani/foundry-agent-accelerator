import ast
import fnmatch
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent


def context_files(root):
    """Top-level files that .dockerignore lets into the build context; the last matching rule wins."""
    rules = [line.strip() for line in (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.strip().startswith("#")]
    files = set()
    for path in root.iterdir():
        if not path.is_file():
            continue
        ignored = False
        for rule in rules:
            if fnmatch.fnmatchcase(path.name, rule.lstrip("!")):
                ignored = not rule.startswith("!")
        if not ignored or path.name in ("Dockerfile", ".dockerignore"):
            files.add(path.name)
    return files


def image_files(root):
    """Top-level files the Dockerfile copies out of the build context into the image."""
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    copied = set()
    for sources in re.findall(r"^COPY (?!--)(.+) \./$", dockerfile, re.MULTILINE):
        for pattern in sources.split():
            if "/" not in pattern:
                copied.update(path.name for path in root.glob(pattern) if path.is_file())
    return copied & context_files(root)


def imported_modules(root):
    """Modules in root that app.py imports, directly or through another module, including lazy imports."""
    pending, seen = ["app"], set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        for node in ast.walk(ast.parse((root / f"{name}.py").read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            pending.extend(n for n in names if (root / f"{n}.py").is_file())
    return seen


def modules_missing_from_image(root):
    return sorted(f"{name}.py" for name in imported_modules(root) if f"{name}.py" not in image_files(root))


class ImageContextTests(unittest.TestCase):
    """The image copies Python modules by pattern, so a new module can't be left out by a forgotten list."""

    def test_every_module_app_imports_is_in_the_image(self):
        self.assertIn("library_preview", imported_modules(ROOT))
        self.assertEqual(modules_missing_from_image(ROOT), [], "These modules are imported by app.py but not in the image")

    def test_tests_and_private_verification_stay_out_of_the_image(self):
        shipped = image_files(ROOT)
        self.assertIn("app.py", shipped)
        self.assertEqual(sorted(name for name in shipped if name.startswith("test_") or name == "verify_private.py"), [])

    def test_a_module_app_imports_but_the_image_lacks_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("import helper\n", encoding="utf-8")
            (root / "helper.py").write_text("def late():\n    import lazy\n", encoding="utf-8")
            (root / "lazy.py").write_text("", encoding="utf-8")
            (root / "Dockerfile").write_text("COPY app.py helper.py ./\n", encoding="utf-8")
            (root / ".dockerignore").write_text("*\n!*.py\n", encoding="utf-8")
            self.assertEqual(modules_missing_from_image(root), ["lazy.py"])
            (root / ".dockerignore").write_text("*\n!*.py\nhelper.py\n", encoding="utf-8")
            self.assertEqual(modules_missing_from_image(root), ["helper.py", "lazy.py"])


if __name__ == "__main__":
    unittest.main()
