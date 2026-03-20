"""Bash tool — the single tool exposed to the agent.

The agent has full shell access on the server. Security is enforced here
(dangerous pattern blocking) and in the system prompt (behavioral rules).
"""
import subprocess

# Patterns that are never allowed, regardless of context
_DANGEROUS = [
    "rm -rf /",
    "rm -rf ~",
    "mkfs",
    "dd if=",
    "> /dev/sd",
    ":(){ :|:& };:",
]

# Tool definition for the Anthropic API
DEFINITIONS = [
    {
        "name": "bash",
        "description": (
            "Run a shell command on the server. "
            "Has full access to kubectl, flux, talosctl, docker, git, systemctl, "
            "and all standard Linux tools. Returns stdout + stderr."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
            },
            "required": ["command"],
        },
    }
]


def run_bash(command: str) -> str:
    """Execute a shell command with safety checks. Returns output string."""
    for pattern in _DANGEROUS:
        if pattern in command:
            return f"REFUSED: dangerous pattern detected ('{pattern}')"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60
        )
        output = (result.stdout + result.stderr).strip()
        if not output:
            return f"(exit code {result.returncode}, no output)"
        if len(output) > 8000:
            return output[:8000] + f"\n... (truncated, {len(output)} total chars)"
        return output
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 60s"
    except Exception as e:
        return f"Error: {e}"
