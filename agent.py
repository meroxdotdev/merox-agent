#!/usr/bin/env python3
"""
Merox Agent — interactive CLI.

Runs directly on the server (no Tailscale needed).
Uses Claude Code under the hood — requires Claude Code CLI to be installed
and authenticated (claude login).

Usage:
    python3 agent.py                        # interactive chat
    python3 agent.py "what pods are down?"  # one-shot
"""
import asyncio
import sys

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ResultMessage,
    SystemMessage,
    CLINotFoundError,
    CLIConnectionError,
)

from config import MODEL
from prompt import build_system_prompt

# ── Colors ────────────────────────────────────────────────────────────────────

CYAN  = "\033[1;36m"
DIM   = "\033[2m"
BOLD  = "\033[1m"
RED   = "\033[1;31m"
RESET = "\033[0m"

# ── Agent ─────────────────────────────────────────────────────────────────────

async def run_turn(prompt: str, session_id: str | None = None) -> tuple[str, str | None]:
    """Run one turn. Prints tool calls live. Returns (response_text, session_id)."""
    options = ClaudeAgentOptions(
        system_prompt=build_system_prompt(),
        allowed_tools=["Bash"],
        permission_mode="default",
        model=MODEL,
        resume=session_id,
    )

    text = ""
    captured_session = session_id

    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, SystemMessage) and msg.subtype == "init":
                captured_session = msg.data.get("session_id", session_id)
            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text:
                        text += block.text
                    elif isinstance(block, ToolUseBlock):
                        preview = str(block.input)
                        if len(preview) > 70:
                            preview = preview[:67] + "..."
                        print(f"{DIM}  [{block.name}({preview})]{RESET}")
            elif isinstance(msg, ResultMessage):
                if getattr(msg, "is_error", False):
                    text = f"Error: {msg.result}"
                elif msg.result and not text:
                    text = msg.result

    except CLINotFoundError:
        text = f"{RED}Claude CLI not found.{RESET} Run: npm install -g @anthropic-ai/claude-code"
    except CLIConnectionError as e:
        text = f"{RED}CLI connection error:{RESET} {e}"

    return text or "No response.", captured_session


# ── CLI ───────────────────────────────────────────────────────────────────────

def _banner() -> None:
    print(f"{CYAN}╔══════════════════════════════════════╗")
    print(f"║     Merox Infrastructure Agent       ║")
    print(f"╚══════════════════════════════════════╝{RESET}")
    print("Type 'exit' to quit, 'clear' to reset session.\n")


def main() -> None:
    session_id: str | None = None

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(f"{BOLD}You:{RESET} {question}")
        text, _ = asyncio.run(run_turn(question))
        print(f"\n{CYAN}Agent:{RESET} {text}\n")
        return

    _banner()
    while True:
        try:
            user_input = input(f"{BOLD}You:{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        if user_input.lower() == "clear":
            session_id = None
            print("Session cleared.\n")
            continue

        try:
            text, session_id = asyncio.run(run_turn(user_input, session_id))
            print(f"\n{CYAN}Agent:{RESET} {text}\n")
        except KeyboardInterrupt:
            print("\n(interrupted)\n")


if __name__ == "__main__":
    main()
