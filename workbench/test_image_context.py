import ast
import fnmatch
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent


def in_context(rules, relative):
    """Whether .dockerignore lets a path in; the last matching rule wins and a rule matching a parent directory covers its files."""
    parts = relative.split("/")
    ignored = False
    for rule in rules:
        pattern = rule.lstrip("!").strip("/").split("/")
        if any(len(pattern) == end and all(fnmatch.fnmatchcase(part, glob) for part, glob in zip(parts[:end], pattern, strict=True))
               for end in range(1, len(parts) + 1)):
            ignored = not rule.startswith("!")
    return not ignored or relative in ("Dockerfile", ".dockerignore")


def dockerignore_rules(root):
    return [line.strip() for line in (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")]


def context_files(root):
    """Top-level files that .dockerignore lets into the build context."""
    rules = dockerignore_rules(root)
    return {path.name for path in root.iterdir() if path.is_file() and in_context(rules, path.name)}


def image_files(root):
    """Top-level files the Dockerfile copies out of the build context into the image."""
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    copied = set()
    for sources in re.findall(r"^COPY (?!--)(.+) \./$", dockerfile, re.MULTILINE):
        for pattern in sources.split():
            if "/" not in pattern:
                copied.update(path.name for path in root.glob(pattern) if path.is_file())
    return copied & context_files(root)


def image_packages(root):
    """Packages the Dockerfile copies whole, provided .dockerignore lets their modules in."""
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    rules = dockerignore_rules(root)
    return {name for name in re.findall(r"^COPY (\w+)/ \./\1/$", dockerfile, re.MULTILINE)
            if in_context(rules, f"{name}/__init__.py")}


def is_package(root, name):
    return (root / name / "__init__.py").is_file()


def imported_modules(root):
    """Modules and packages in root that app.py imports, directly or through another module, including lazy imports."""
    pending, seen = ["app"], set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        sources = sorted((root / name).rglob("*.py")) if is_package(root, name) else [root / f"{name}.py"]
        for source in sources:
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                else:
                    continue
                pending.extend(n for n in names if (root / f"{n}.py").is_file() or is_package(root, n))
    return seen


def modules_missing_from_image(root):
    modules, packages = image_files(root), image_packages(root)
    return sorted(f"{name}/" if is_package(root, name) else f"{name}.py" for name in imported_modules(root)
                  if not (name in packages if is_package(root, name) else f"{name}.py" in modules))


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

    def test_a_package_app_imports_is_reported_unless_copied_and_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pkg").mkdir()
            (root / "app.py").write_text("from pkg import thing\n", encoding="utf-8")
            (root / "pkg" / "__init__.py").write_text("thing = 1\n", encoding="utf-8")
            (root / "Dockerfile").write_text("COPY app.py ./\n", encoding="utf-8")
            (root / ".dockerignore").write_text("*\n!*.py\n", encoding="utf-8")
            self.assertEqual(modules_missing_from_image(root), ["pkg/"])
            (root / "Dockerfile").write_text("COPY app.py ./\nCOPY pkg/ ./pkg/\n", encoding="utf-8")
            self.assertEqual(modules_missing_from_image(root), ["pkg/"])
            (root / ".dockerignore").write_text("*\n!*.py\n!pkg/\npkg/*\n!pkg/*.py\n", encoding="utf-8")
            self.assertEqual(modules_missing_from_image(root), [])

    def test_every_copied_package_is_allowed_by_dockerignore_and_staged_by_build_script(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        allowed = {line.strip()[1:] for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
                   if line.strip().startswith("!")}
        script = (ROOT / "build.ps1").read_text(encoding="utf-8")
        packages = set(re.findall(r"^COPY (\w+)/ \./\1/$", dockerfile, re.MULTILINE))
        self.assertIn("agent_templates", packages)
        self.assertIn("agent_templates", image_packages(ROOT))
        for package in sorted(packages):
            with self.subTest(package=package):
                self.assertIn(f"{package}/", allowed, "Add this package to workbench/.dockerignore")
                self.assertIn(f'"{package}"', script, "Stage this package in workbench/build.ps1")

    def test_every_library_agent_file_is_allowed_by_dockerignore_and_staged_by_build_script(self):
        rules = dockerignore_rules(ROOT)
        files = sorted(path.name for path in (ROOT / "agent_templates" / "agents").glob("*.json"))
        self.assertGreater(len(files), 1)
        for name in files:
            with self.subTest(file=name):
                self.assertTrue(in_context(rules, f"agent_templates/agents/{name}"), "Allow library agent files in workbench/.dockerignore")
        self.assertFalse(in_context(rules, "agent_templates/agents/notes.txt"))
        self.assertFalse(in_context(rules, "agent_templates/agents/__pycache__/x.json"))
        self.assertIn("agent_templates/agents/*.json", (ROOT / "build.ps1").read_text(encoding="utf-8"),
                      "Stage library agent files in workbench/build.ps1")


if __name__ == "__main__":
    unittest.main()
