#!/usr/bin/env python3
"""
Merox Agent — interactive CLI.

Runs directly on the server. Uses the Anthropic Python SDK.

Usage:
    python3 agent.py                        # interactive chat
    python3 agent.py "what pods are down?"  # one-shot
"""
import os
import sys

import anthropic

from config import MODEL, MAX_TOKENS
from prompt import build_system_prompt
from tools import DEFINITIONS as TOOLS, run_bash

# ── Colors ────────────────────────────────────────────────────────────────────

CYAN  = "\033[1;36m"
DIM   = "\033[2m"
BOLD  = "\033[1m"
RED   = "\033[1;31m"
RESET = "\033[0m"

# ── Agent ─────────────────────────────────────────────────────────────────────

_client = anthropic.Anthropic()


def run_turn(conversation: list, user_msg: str) -> tuple[str, list]:
    """
    Send a user message and return (response_text, updated_conversation).
    Handles multi-turn tool use. Streams text to stdout in real time.
    """
    conversation = conversation + [{"role": "user", "content": user_msg}]

    while True:
        text = ""

        with _client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=build_system_prompt(),
            tools=TOOLS,
            messages=conversation,
        ) as stream:
            for chunk in stream.text_stream:
                print(chunk, end="", flush=True)
                text += chunk

            final = stream.get_final_message()

        assistant_content = []
        for block in final.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        conversation.append({"role": "assistant", "content": assistant_content})

        if final.stop_reason == "end_turn":
            print()  # newline after streamed text
            return text, conversation

        if final.stop_reason == "tool_use":
            tool_results = []
            for block in final.content:
                if block.type == "tool_use":
                    preview = str(block.input)
                    if len(preview) > 70:
                        preview = preview[:67] + "..."
                    print(f"\n{DIM}  [{block.name}({preview})]{RESET}", end="", flush=True)
                    result = run_bash(block.input.get("command", ""))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            conversation.append({"role": "user", "content": tool_results})
        else:
            print()
            return text, conversation


# ── CLI ───────────────────────────────────────────────────────────────────────

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


def main() -> None:
    _check_env()

    # One-shot mode
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(f"{BOLD}You:{RESET} {question}")
        print(f"\n{CYAN}Agent:{RESET} ", end="")
        run_turn([], question)
        print()
        return

    # Interactive mode
    _banner()
    conversation: list = []

    while True:
        try:
            user_input = input(f"\n{BOLD}You:{RESET} ").strip()
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
            print("Conversation cleared.")
            continue

        try:
            print(f"\n{CYAN}Agent:{RESET} ", end="")
            _, conversation = run_turn(conversation, user_input)
        except anthropic.APIError as e:
            print(f"\n{RED}API Error:{RESET} {e}")
        except KeyboardInterrupt:
            print("\n(interrupted)")


if __name__ == "__main__":
    main()
