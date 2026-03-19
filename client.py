#!/usr/bin/env python3
"""
Merox Agent — client CLI.

Install on any device connected to Tailscale, then run: python3 client.py
No API key needed here — the server handles everything.

Requirements (minimal):
    pip install httpx

Usage:
    python3 client.py                        # interactive chat
    python3 client.py "what pods are down?"  # one-shot
    python3 client.py --session abc123 "..."  # resume session
"""
import argparse
import json
import os
import sys

try:
    import httpx
except ImportError:
    print("Missing dependency: pip install httpx")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────

def _load_env():
    """Load .env from same directory as this file."""
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        for line in open(env_file).read().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

SERVER_URL  = os.getenv("AGENT_SERVER_URL", "http://100.72.22.38:8765")
SESSION_FILE = os.path.expanduser("~/.merox_session")

# ── Colors ────────────────────────────────────────────────────────────────────

CYAN  = "\033[1;36m"
DIM   = "\033[2m"
BOLD  = "\033[1m"
RED   = "\033[1;31m"
RESET = "\033[0m"

# ── Session persistence ───────────────────────────────────────────────────────

def load_session() -> str:
    try:
        return open(SESSION_FILE).read().strip()
    except FileNotFoundError:
        return ""


def save_session(sid: str):
    with open(SESSION_FILE, "w") as f:
        f.write(sid)


def clear_session():
    try:
        os.remove(SESSION_FILE)
    except FileNotFoundError:
        pass

# ── HTTP ──────────────────────────────────────────────────────────────────────

def check_server():
    try:
        r = httpx.get(f"{SERVER_URL}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def send_message(message: str, session_id: str) -> str:
    """Send a message and print the streamed response. Returns the session_id."""
    returned_session = session_id
    buffer = ""

    with httpx.stream(
        "POST",
        f"{SERVER_URL}/chat",
        json={"message": message, "session_id": session_id},
        timeout=120,
    ) as response:
        if response.status_code != 200:
            raise RuntimeError(f"Server error {response.status_code}: {response.text}")

        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            t = event.get("type")

            if t == "session":
                returned_session = event["session_id"]

            elif t == "tool":
                name = event["name"]
                preview = json.dumps(event.get("input", {}))
                if len(preview) > 70:
                    preview = preview[:67] + "..."
                print(f"{DIM}  [{name}({preview})]{RESET}")

            elif t == "text":
                buffer = event["content"]

            elif t == "done":
                break

    return returned_session, buffer


# ── CLI ───────────────────────────────────────────────────────────────────────

def banner():
    print(f"{CYAN}╔══════════════════════════════════════╗")
    print(f"║     Merox Infrastructure Agent       ║")
    print(f"╚══════════════════════════════════════╝{RESET}")
    print(f"Server: {SERVER_URL}")
    print("Type 'exit' to quit, 'clear' to reset session.\n")


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--session", default="", help="Resume a specific session ID")
    parser.add_argument("message", nargs="*", help="One-shot message")
    args = parser.parse_args()

    if not check_server():
        print(f"{RED}Cannot reach agent server at {SERVER_URL}{RESET}")
        print("Make sure:")
        print("  1. Tailscale is connected")
        print(f"  2. Agent service is running on the server")
        print(f"  3. AGENT_SERVER_URL is correct (currently: {SERVER_URL})")
        sys.exit(1)

    session_id = args.session or load_session()

    # One-shot mode
    if args.message:
        question = " ".join(args.message)
        print(f"{BOLD}You:{RESET} {question}")
        try:
            session_id, answer = send_message(question, session_id)
            save_session(session_id)
            print(f"\n{CYAN}Agent:{RESET} {answer}\n")
        except Exception as e:
            print(f"{RED}Error:{RESET} {e}")
            sys.exit(1)
        return

    # Interactive mode
    banner()
    if session_id:
        print(f"{DIM}Resuming session {session_id[:8]}...{RESET}\n")

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
            clear_session()
            session_id = ""
            print("Session cleared.\n")
            continue
        if user_input.lower() == "session":
            print(f"Current session: {session_id or '(none)'}\n")
            continue

        try:
            session_id, answer = send_message(user_input, session_id)
            save_session(session_id)
            print(f"\n{CYAN}Agent:{RESET} {answer}\n")
        except httpx.ReadTimeout:
            print(f"{RED}Timeout{RESET} — server is taking too long. Try again.\n")
        except Exception as e:
            print(f"{RED}Error:{RESET} {e}\n")


if __name__ == "__main__":
    main()
