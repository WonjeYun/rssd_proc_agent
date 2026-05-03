#!/usr/bin/env python3
"""
FFIEC RSSD Lookup Agent — interactive CLI.

Usage:
    python -m ffiec_rssd_agent.agent

Requires ANTHROPIC_API_KEY in the environment or in a .env file at the project root.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from .system_prompt import SYSTEM_PROMPT
from .tools import ALLOWED_TOOL_NAMES

# Built-in Claude Code tools we expose and pre-approve (no permission prompt).
# Must also appear in `tools=[...]` or they stay disabled.
FILE_AND_SHELL_TOOLS = ("Read", "Write", "Bash")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(__file__).resolve().parent / "ffiec_nic.db"

# .env is not read by Python automatically; load project-root .env into os.environ.
load_dotenv(_PROJECT_ROOT / ".env")

HELP_TEXT = """
FFIEC RSSD Lookup Agent
========================
Ask natural-language questions about U.S. financial institutions.

Example queries:
  What is the RSSD ID for JPMorgan Chase?
  Show me the ownership tree for RSSD 1039502
  What happened to Washington Mutual?
  Match this file: bank_list.xlsx

Commands:
  /help   - show this message
  /quit   - exit the agent
""".strip()


def _check_prerequisites() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        print("Get an API key at https://console.anthropic.com/ and run:")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        return False

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run the data loader first:")
        print("  python -m ffiec_rssd_agent.load_data")
        return False

    return True


async def run_agent() -> None:
    if not _check_prerequisites():
        sys.exit(1)

    # Built-ins: enable only Read/Write/Bash and pre-approve them.
    # NIC data access is via Python scripts run in Bash (see system_prompt), not MCP tools.
    # Other built-ins (Edit, Glob, Grep, …) stay off to limit scope.
    allowed = list(FILE_AND_SHELL_TOOLS) + list(ALLOWED_TOOL_NAMES)

    options = ClaudeAgentOptions(
        tools=list(FILE_AND_SHELL_TOOLS),
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=allowed,
        setting_sources=[],
    )

    print(HELP_TEXT)
    print()

    async with ClaudeSDKClient(options=options) as client:
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            cmd = user_input.lower()
            if cmd in ("/quit", "/exit", "/q"):
                print("Goodbye!")
                break
            if cmd == "/help":
                print(HELP_TEXT)
                continue

            await client.query(user_input)

            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(f"\n{block.text}")
                        elif isinstance(block, ToolUseBlock):
                            print(f"  [calling {block.name}...]")

                elif isinstance(msg, ResultMessage):
                    if msg.total_cost_usd:
                        print(f"  [cost: ${msg.total_cost_usd:.6f}]")

            print()


def main() -> None:
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
