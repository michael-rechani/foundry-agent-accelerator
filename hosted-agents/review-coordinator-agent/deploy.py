import argparse
import json
import os
import sys
from pathlib import Path

SOURCE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE_DIRECTORY.parent))

from deployment import AgentProfile, run
from configuration import validate_profile


def profile_from_file(path: Path) -> AgentProfile:
    configuration = validate_profile(json.loads(path.read_text(encoding="utf-8")))
    bindings = {item["tool"]: item["agent"] for item in configuration["specialists"]}
    return AgentProfile(
        source_directory=SOURCE_DIRECTORY,
        name=configuration["name"],
        description=configuration["description"],
        instructions=configuration["instructions"],
        smoke_test_prompt="",
        delegation_checks=tuple(
            (test["prompt"], test["tool"], bindings[test["tool"]])
            for test in configuration["smoke_tests"]
        ),
        environment_variables=(("SPECIALIST_CONFIG", json.dumps(configuration["specialists"])),),
    )


if __name__ == "__main__":
    profile_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    profile_parser.add_argument("--profile", type=Path)
    profile_parser.add_argument("--validate-profile", action="store_true")
    profile_args, remaining = profile_parser.parse_known_args()
    if profile_args.validate_profile and profile_args.profile is None:
        profile_parser.error("--validate-profile requires --profile")
    if profile_args.profile is not None:
        selected = profile_from_file(profile_args.profile)
        if any(argument.split("=", 1)[0] in {"--instructions", "--agent-name"} for argument in remaining):
            profile_parser.error("Set coordinator name and instructions in the profile, not CLI overrides")
        if "FOUNDRY_HOSTED_AGENT_NAME" in os.environ:
            profile_parser.error("Unset FOUNDRY_HOSTED_AGENT_NAME when using a profile")
        if profile_args.validate_profile:
            if remaining:
                profile_parser.error("--validate-profile does not accept deployment arguments")
            print(f"Valid profile: {selected.name}")
            for _, tool, agent in selected.delegation_checks:
                print(f"  {tool} -> {agent}")
            sys.exit(0)
        run(selected, remaining)
        sys.exit(0)
    if "--help" in remaining or "-h" in remaining:
        print("Use --profile PATH to select a customer profile; add --validate-profile to check it without Azure.\n")
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
                    "application-review-agent",
                ),
                (
                    "Review this case record: CASE-1 records intake on June 1; CASE-2 records "
                    "intake on June 3. Return the case specialist's finding about the conflict.",
                    "review_case",
                    "case-review-agent",
                ),
            ),
        )
    )