#!/usr/bin/env python3
"""Memory CLI — called by the agent via Bash to read/write persistent memory.

Usage:
  python3 cli.py log "deployed jellyfin 1.2.3" "ok" deploy kubernetes
  python3 cli.py note "jellyfin_version" "1.2.3"
  python3 cli.py note-delete "old_key"
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MEMORY_DIR = Path(__file__).parent
EVENTS_FILE = MEMORY_DIR / "events.jsonl"
NOTES_FILE = MEMORY_DIR / "notes.json"


def cmd_log(args: list[str]) -> None:
    if not args:
        print("Usage: cli.py log <action> [result] [tag1 tag2 ...]", file=sys.stderr)
        sys.exit(1)
    action = args[0]
    result = args[1] if len(args) > 1 else ""
    tags = args[2:] if len(args) > 2 else []
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "result": result[:500],
        "tags": tags,
    }
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")
    print(f"Logged: {action}")


def cmd_note(args: list[str]) -> None:
    if len(args) < 2:
        print("Usage: cli.py note <key> <value>", file=sys.stderr)
        sys.exit(1)
    key = args[0]
    value = " ".join(args[1:])
    notes = json.loads(NOTES_FILE.read_text()) if NOTES_FILE.exists() else {}
    notes[key] = {"value": value, "updated": datetime.now(timezone.utc).isoformat()}
    NOTES_FILE.write_text(json.dumps(notes, indent=2, ensure_ascii=False) + "\n")
    print(f"Note set: {key} = {value}")


def cmd_note_delete(args: list[str]) -> None:
    if not args:
        print("Usage: cli.py note-delete <key>", file=sys.stderr)
        sys.exit(1)
    key = args[0]
    notes = json.loads(NOTES_FILE.read_text()) if NOTES_FILE.exists() else {}
    if key in notes:
        del notes[key]
        NOTES_FILE.write_text(json.dumps(notes, indent=2, ensure_ascii=False) + "\n")
        print(f"Note deleted: {key}")
    else:
        print(f"Note not found: {key}", file=sys.stderr)
        sys.exit(1)


_COMMANDS = {"log": cmd_log, "note": cmd_note, "note-delete": cmd_note_delete}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        print(f"Usage: cli.py [{' | '.join(_COMMANDS)}] ...", file=sys.stderr)
        sys.exit(1)
    _COMMANDS[sys.argv[1]](sys.argv[2:])
