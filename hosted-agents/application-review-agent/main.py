import asyncio
from pathlib import Path

from azure.identity import DefaultAzureCredential

from hosted_runtime import agent_settings, build_agent, serve
from review_output import quotation_middleware

DEFAULT_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(
    encoding="utf-8"
)


async def main() -> None:
    settings = agent_settings("application-review-agent", DEFAULT_INSTRUCTIONS)

    with DefaultAzureCredential() as credential:
        agent = build_agent(credential, settings, middleware=[quotation_middleware()])
        await serve(agent)


if __name__ == "__main__":
    asyncio.run(main())
