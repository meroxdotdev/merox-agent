"""Runbook loader — auto-discovers YAML runbooks and formats them for the prompt."""
import yaml
from pathlib import Path

RUNBOOK_DIR = Path(__file__).parent


def load_runbooks() -> list[dict]:
    """Load all runbook YAML files."""
    runbooks = []
    for f in sorted(RUNBOOK_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text())
            if data and isinstance(data, dict):
                runbooks.append(data)
        except Exception:
            continue
    return runbooks


def runbooks_to_prompt() -> str:
    """Format runbooks as a summary for the system prompt."""
    runbooks = load_runbooks()
    if not runbooks:
        return ""

    lines = ["━━━ AVAILABLE RUNBOOKS ━━━",
             "Use these standard procedures when handling the corresponding tasks:"]
    for rb in runbooks:
        name = rb.get("name", "unknown")
        desc = rb.get("description", "")
        trigger = rb.get("trigger", "")
        step_names = [s.get("name", "?") for s in rb.get("steps", [])]
        lines.append(f"  - {name}: {desc}")
        lines.append(f"    Trigger: {trigger}")
        lines.append(f"    Steps: {' -> '.join(step_names)}")
    return "\n".join(lines)
