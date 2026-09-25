import sys
from pathlib import Path

SOURCE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE_DIRECTORY.parent))

from deployment import AgentProfile, run


def default_profile() -> AgentProfile:
    return AgentProfile(
        source_directory=SOURCE_DIRECTORY,
        name="basic-responses-agent",
        description="Python SDK deployment of the basic Responses agent.",
        instructions=(
            "You are a concise assistant. Use only information available to "
            "you and clearly identify uncertainty."
        ),
        smoke_test_prompt=(
            "Reply with a short confirmation that the hosted agent is ready."
        ),
    )


if __name__ == "__main__":
    run(default_profile())
