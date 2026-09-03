import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from deployment import create_package


class DeploymentPackageTests(unittest.TestCase):
    def test_package_includes_reviewed_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            source.mkdir()
            (source / "main.py").write_text("print('ready')\n", encoding="utf-8")
            (source / "requirements.txt").write_text("example==1\n", encoding="utf-8")
            (source / "instructions.md").write_text("Use supplied facts.\n", encoding="utf-8")
            destination = Path(temporary) / "agent.zip"

            create_package(source, destination)

            with ZipFile(destination) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {"main.py", "requirements.txt", "instructions.md"},
                )

    def test_package_requires_runtime_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            destination = source / "agent.zip"

            with self.assertRaisesRegex(FileNotFoundError, "main.py"):
                create_package(source, destination)


if __name__ == "__main__":
    unittest.main()