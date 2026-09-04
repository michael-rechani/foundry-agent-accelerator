import sys
from pathlib import Path

SOURCE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE_DIRECTORY.parent))

from deployment import AgentProfile, run


if __name__ == "__main__":
    run(
        AgentProfile(
            source_directory=SOURCE_DIRECTORY,
            name="review-coordinator-agent",
            description="Routes review requests to evidence-grounded specialist agents.",
            instructions=(SOURCE_DIRECTORY / "instructions.md").read_text(
                encoding="utf-8"
            ),
            smoke_test_prompt=(
                "Route this application review: criterion CRIT-1 requires a budget, "
                "but source APP-1 contains no budget. Return the specialist's finding."
            ),
            delegation_checks=(
                (
                    "Review this application: CRIT-1 requires a budget; APP-1 has no budget. "
                    "Return the application specialist's finding with source identifiers.",
                    "review_application",
                ),
                (
                    "Review this case record: CASE-1 records intake on June 1; CASE-2 records "
                    "intake on June 3. Return the case specialist's finding about the conflict.",
                    "review_case",
                ),
            ),
        )
    )