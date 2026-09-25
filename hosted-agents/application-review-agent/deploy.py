import sys
from pathlib import Path

SOURCE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE_DIRECTORY.parent))

from deployment import AgentProfile, run


def default_profile() -> AgentProfile:
    return AgentProfile(
        source_directory=SOURCE_DIRECTORY,
        name="application-review-agent",
        description="Criteria-grounded application review assistant sample.",
        instructions=(SOURCE_DIRECTORY / "instructions.md").read_text(encoding="utf-8"),
        smoke_test_prompt=(
            "Review this synthetic application: criterion CRIT-1 requires "
            "a budget, but source APP-1 contains no budget. Report the gap "
            "without recommending approval or denial."
        ),
    )


if __name__ == "__main__":
    run(default_profile())
