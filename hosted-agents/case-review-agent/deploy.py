import sys
from pathlib import Path

SOURCE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE_DIRECTORY.parent))

from deployment import AgentProfile, run


if __name__ == "__main__":
    run(
        AgentProfile(
            source_directory=SOURCE_DIRECTORY,
            name="case-review-agent",
            description="Evidence-grounded case review assistant sample.",
            instructions=(SOURCE_DIRECTORY / "instructions.md").read_text(
                encoding="utf-8"
            ),
            smoke_test_prompt=(
                "Review this synthetic case: source CASE-1 says an application "
                "was received. Identify what evidence is missing without making "
                "an eligibility decision."
            ),
        )
    )