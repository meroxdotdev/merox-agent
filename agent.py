#!/usr/bin/env python3
"""
Merox Infrastructure Agent
Manages the Oracle Cloud server, Kubernetes cluster, and merox.dev website.

Usage:
    python3 agent.py                        # interactive chat
    python3 agent.py "what pods are down?"  # one-shot

Requirements:
    pip install anthropic
    export ANTHROPIC_API_KEY='sk-ant-...'

For remote use: connect to Tailscale first, then SSH to the server.
"""
import json
import os
import sys

import anthropic

from config import MODEL, MAX_TOKENS
from prompt import SYSTEM_PROMPT
from tools import kubernetes, server, git_tools

# ─── Build unified tool registry ──────────────────────────────────────────────

ALL_TOOLS = (
    kubernetes.DEFINITIONS
    + server.DEFINITIONS
    + git_tools.DEFINITIONS
)

_HANDLERS = {
    **{t["name"]: lambda i, _n=t["name"]: kubernetes.handle(_n, i) for t in kubernetes.DEFINITIONS},
    **{t["name"]: lambda i, _n=t["name"]: server.handle(_n, i)     for t in server.DEFINITIONS},
    **{t["name"]: lambda i, _n=t["name"]: git_tools.handle(_n, i)  for t in git_tools.DEFINITIONS},
}


def dispatch(name: str, inp: dict) -> str:
    handler = _HANDLERS.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    try:
        return handler(inp)
    except Exception as e:
        return f"Tool error ({name}): {e}"


# ─── Agent loop ───────────────────────────────────────────────────────────────

def run_turn(client: anthropic.Anthropic, conversation: list, user_msg: str) -> tuple[str, list]:
    """Send a user message and handle tool calls until a final text response."""
    conversation = conversation + [{"role": "user", "content": user_msg}]

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=conversation,
        )
        conversation.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if b.type == "text"), "")
            return text, conversation

        if response.stop_reason == "tool_use":
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    _print_tool_call(block.name, block.input)
                    result = dispatch(block.name, block.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            conversation.append({"role": "user", "content": results})
        else:
            text = next((b.text for b in response.content if b.type == "text"), "")
            return text, conversation


# ─── CLI helpers ──────────────────────────────────────────────────────────────

CYAN  = "\033[1;36m"
DIM   = "\033[2m"
BOLD  = "\033[1m"
RED   = "\033[1;31m"
RESET = "\033[0m"


def _print_tool_call(name: str, inp: dict) -> None:
    preview = json.dumps(inp)
    if len(preview) > 80:
        preview = preview[:77] + "..."
    print(f"{DIM}  [{name}({preview})]{RESET}")


def _check_env() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"{RED}Error:{RESET} ANTHROPIC_API_KEY is not set.")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)


def _banner() -> None:
    print(f"{CYAN}╔══════════════════════════════════════╗")
    print(f"║     Merox Infrastructure Agent       ║")
    print(f"╚══════════════════════════════════════╝{RESET}")
    print("Type 'exit' to quit, 'clear' to reset conversation.\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    _check_env()
    client = anthropic.Anthropic()

    # One-shot mode
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(f"{BOLD}You:{RESET} {question}")
        answer, _ = run_turn(client, [], question)
        print(f"\n{CYAN}Agent:{RESET} {answer}\n")
        return

    # Interactive mode
    _banner()
    conversation: list = []

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
            conversation = []
            print("Conversation cleared.\n")
            continue

        try:
            answer, conversation = run_turn(client, conversation, user_input)
            print(f"\n{CYAN}Agent:{RESET} {answer}\n")
        except anthropic.APIError as e:
            print(f"\n{RED}API Error:{RESET} {e}\n")
        except KeyboardInterrupt:
            print("\n(interrupted)\n")


if __name__ == "__main__":
    main()
