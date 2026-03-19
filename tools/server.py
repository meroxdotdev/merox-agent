"""Oracle server management tools (runs locally on the server)."""
import re
from tools.shell import run

# Sensitive paths that must never be read/written
_BLOCKED = [
    ".sops.yaml", "age.key", "kubeconfig", "talosconfig",
    ".env", "id_rsa", "id_ed25519", "id_ecdsa", ".pem", ".key",
]

DEFINITIONS = [
    {
        "name": "server_status",
        "description": "Get server health: CPU load, memory, disk usage, uptime.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "docker_status",
        "description": "List running Docker containers with name, status, and image.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "Optional container name filter, e.g. 'jellyfin'"},
            },
            "required": [],
        },
    },
    {
        "name": "docker_logs",
        "description": "Get recent logs from a Docker container.",
        "input_schema": {
            "type": "object",
            "properties": {
                "container": {"type": "string", "description": "Container name, e.g. 'traefik'"},
                "lines": {"type": "integer", "description": "Number of lines (default 50)"},
            },
            "required": ["container"],
        },
    },
    {
        "name": "docker_compose",
        "description": "Run a docker compose command in a specific service directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "e.g. 'up -d', 'down', 'pull', 'ps'"},
                "service_dir": {"type": "string", "description": "Directory containing docker-compose.yml, e.g. '/srv/docker/traefik'"},
            },
            "required": ["command", "service_dir"],
        },
    },
    {
        "name": "systemctl",
        "description": "Manage or query systemd services.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "'status', 'start', 'stop', 'restart', 'list'"},
                "service": {"type": "string", "description": "Service name, e.g. 'docker' or 'tailscaled'. Not needed for 'list'."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the filesystem. Sensitive files (secrets, keys, configs) are blocked.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Sensitive files are blocked.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to write"},
                "content": {"type": "string", "description": "File content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_dir",
        "description": "List contents of a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to directory"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_shell",
        "description": "Run a general shell command on the Oracle server (task, helm, yq, jq, curl, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "working_dir": {"type": "string", "description": "Optional working directory"},
            },
            "required": ["command"],
        },
    },
]

_DANGEROUS = ["rm -rf /", "mkfs", "dd if=", "> /dev/sd", ":(){ :|:& };:"]
_SAFE_NAME = re.compile(r'^[a-zA-Z0-9_.\-]+$')  # safe container/service names


def _is_blocked(path: str) -> bool:
    return any(b in path for b in _BLOCKED)


def _safe_name(value: str, label: str) -> str | None:
    """Return value if safe, else None."""
    return value if _SAFE_NAME.match(value) else None


def handle(name: str, inp: dict) -> str:
    if name == "server_status":
        return run(
            "echo '=== Uptime ===' && uptime && "
            "echo '=== Memory ===' && free -h && "
            "echo '=== Disk ===' && df -h --output=source,size,used,avail,pcent,target | grep -v tmpfs | grep -v udev && "
            "echo '=== CPU ===' && grep 'cpu cores' /proc/cpuinfo | head -1 && top -bn1 | grep 'Cpu(s)'"
        )

    elif name == "docker_status":
        fmt = "table {{.Names}}\\t{{.Status}}\\t{{.Image}}"
        f = inp.get("filter", "")
        cmd = f"docker ps --format '{fmt}'"
        if f:
            if not _SAFE_NAME.match(f):
                return "Error: invalid filter — only alphanumeric, dash, underscore, dot allowed"
            cmd += f" | grep -i {re.escape(f)}"
        return run(cmd)

    elif name == "docker_logs":
        container = inp["container"]
        if not _safe_name(container, "container"):
            return "Error: invalid container name"
        lines = inp.get("lines", 50)
        lines = max(1, min(int(lines), 500))  # clamp 1-500
        return run(f"docker logs --tail {lines} {container} 2>&1")

    elif name == "docker_compose":
        cmd = inp["command"]
        service_dir = inp["service_dir"]
        return run(f"docker compose {cmd}", cwd=service_dir, timeout=60)

    elif name == "systemctl":
        action = inp["action"]
        service = inp.get("service", "")
        if action == "list":
            return run("systemctl list-units --type=service --state=running --no-pager | head -40")
        if not service:
            return "Error: 'service' is required for actions other than 'list'"
        if not _safe_name(service, "service"):
            return "Error: invalid service name"
        if action in ("start", "stop", "restart"):
            return run(f"systemctl {action} {service}")
        return run(f"systemctl status {service} --no-pager")

    elif name == "read_file":
        path = inp["path"]
        if _is_blocked(path):
            return f"REFUSED: sensitive file blocked"
        try:
            with open(path) as f:
                content = f.read()
            if len(content) > 8000:
                return content[:8000] + f"\n... (truncated, {len(content)} total chars)"
            return content
        except FileNotFoundError:
            return f"File not found: {path}"
        except Exception as e:
            return f"Error: {e}"

    elif name == "write_file":
        path = inp["path"]
        if _is_blocked(path):
            return f"REFUSED: sensitive file blocked"
        try:
            import os
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w") as f:
                f.write(inp["content"])
            return f"Written: {path}"
        except Exception as e:
            return f"Error: {e}"

    elif name == "list_dir":
        import os
        path = inp["path"]
        try:
            entries = []
            for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name)):
                entries.append(entry.name + ("/" if entry.is_dir() else ""))
            return "\n".join(entries) or "(empty)"
        except Exception as e:
            return f"Error: {e}"

    elif name == "run_shell":
        cmd = inp["command"]
        for d in _DANGEROUS:
            if d in cmd:
                return f"REFUSED: dangerous command pattern '{d}'"
        return run(cmd, cwd=inp.get("working_dir"), timeout=60)

    return f"Unknown tool: {name}"
