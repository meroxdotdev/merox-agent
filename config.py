"""Agent configuration — loaded from environment variables.

Copy .env.example to .env and fill in your values.
All settings can be overridden via environment variables.
"""
import os
from pathlib import Path

# Auto-load .env from the same directory as this file
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# ── Repos ──────────────────────────────────────────────────────────────────────
INFRA_REPO   = os.getenv("INFRA_REPO",   "/srv/kubernetes/infrastructure")
WEBSITE_REPO = os.getenv("WEBSITE_REPO", "/srv/merox")

# ── Kubernetes ─────────────────────────────────────────────────────────────────
KUBECONFIG   = os.getenv("KUBECONFIG",   f"{INFRA_REPO}/kubeconfig")
TALOSCONFIG  = os.getenv("TALOSCONFIG",  f"{INFRA_REPO}/talos/clusterconfig/talosconfig")

# ── Claude ─────────────────────────────────────────────────────────────────────
MODEL        = os.getenv("AGENT_MODEL",  "claude-opus-4-6")
MAX_TOKENS   = int(os.getenv("AGENT_MAX_TOKENS", "4096"))

# ── Server ─────────────────────────────────────────────────────────────────────
SERVER_NAME        = os.getenv("SERVER_NAME",        "my-server")
SERVER_TS_IP       = os.getenv("SERVER_TS_IP",        "")          # Tailscale IP
DOCKER_COMPOSE_DIR = os.getenv("DOCKER_COMPOSE_DIR", "/srv/docker")
MEDIA_COMPOSE_FILE = os.getenv("MEDIA_COMPOSE_FILE", "/srv/kubernetes/docker-compose.yml")
