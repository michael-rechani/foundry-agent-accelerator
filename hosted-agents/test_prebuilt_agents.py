import re
import unittest
from pathlib import Path

from deployment import PREBUILT_AGENTS, REVIEW_SAMPLES, SAMPLES, SHARED_FILES

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FOLDERS = sorted(path.parent.name for path in HERE.glob("*/main.py"))


class PrebuiltAgentListTests(unittest.TestCase):
    """An agent folder is named in deployment.py, validate.yml and dependabot.yml, and a forgotten one fails here."""

    def test_every_agent_folder_is_listed_once_in_deployment(self):
        self.assertEqual(FOLDERS, sorted(PREBUILT_AGENTS),
                         "Add the hosted-agents/ folder to PREBUILT_AGENTS in hosted-agents/deployment.py")
        self.assertEqual(sorted(SAMPLES), FOLDERS)
        self.assertEqual(len(SAMPLES), len(set(SAMPLES)))

    def test_agents_that_import_the_shared_files_are_the_ones_that_ship_them(self):
        modules = "|".join(re.escape(Path(name).stem) for name in SHARED_FILES)
        imports_shared = {
            folder for folder in FOLDERS
            if re.search(rf"^(?:from|import) (?:{modules})\b", (HERE / folder / "main.py").read_text(encoding="utf-8"),
                         re.MULTILINE)
        }
        self.assertEqual(imports_shared, set(REVIEW_SAMPLES),
                         "PREBUILT_AGENTS says True only for agents whose main.py imports a shared file")

    def test_the_workflow_installs_and_checks_every_agent_folder(self):
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        lines = {line.strip() for line in workflow.splitlines()}
        for folder in FOLDERS:
            with self.subTest(folder=folder):
                for requirements in sorted((HERE / folder).glob("requirements*.txt")):
                    self.assertIn(f"-r hosted-agents/{folder}/{requirements.name}", lines,
                                  f"Install {requirements.name} for {folder} in .github/workflows/validate.yml")
                if (HERE / folder / "deploy.py").is_file():
                    self.assertIn(f"python hosted-agents/{folder}/deploy.py --help", lines,
                                  f"Run {folder}/deploy.py --help in .github/workflows/validate.yml")

    def test_dependabot_watches_every_agent_folder(self):
        config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        lines = {line.strip() for line in config.splitlines()}
        for folder in FOLDERS:
            with self.subTest(folder=folder):
                self.assertIn(f"- /hosted-agents/{folder}", lines, f"Add {folder} to .github/dependabot.yml")


if __name__ == "__main__":
    unittest.main()
