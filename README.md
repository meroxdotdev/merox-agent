# merox-agent

An AI infrastructure agent for homelabs — chat with your server, Kubernetes cluster, and services via Telegram or CLI.

Built with the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python). The agent runs on your server with a single `bash` tool — it can check pod status, restart services, tail logs, run kubectl commands, commit GitOps changes, and anything else you'd do in a terminal.

**Interfaces:** Telegram bot (phone) · CLI client (laptop) · HTTP API (SSE streaming)

---

## How it works

```
Phone / Laptop
    │
    ├── Telegram bot ──────────────────────┐
    └── client.py ─── HTTP (Tailscale) ───►│
                                           │  service.py  (FastAPI)
                                           │    └── Anthropic Python SDK
                                           │          └── bash tool
                                           │                ├── kubectl / flux / talosctl
                                           │                ├── docker / docker compose
                                           │                └── git, systemctl, ...
                                    Oracle Cloud / VPS
```

One tool: `bash`. The agent runs shell commands directly on the server. Security is enforced both in `tools.py` (dangerous pattern blocking) and in the system prompt (behavioral rules for secrets, destructive ops, GitOps preference).

Responses stream in real time — Telegram edits the message live as chunks arrive.

---

## Quick start

### Prerequisites

- A Linux server (Oracle Cloud Free Tier works great)
- [Tailscale](https://tailscale.com) on the server
- Python 3.11+
- An Anthropic API key — [console.anthropic.com](https://console.anthropic.com/)

### Server setup

```bash
sudo git clone https://github.com/meroxdotdev/merox-agent /srv/merox-agent
cd /srv/merox-agent

cp .env.example .env
nano .env  # fill in ANTHROPIC_API_KEY, SERVER_TS_IP, TELEGRAM_BOT_TOKEN, etc.

sudo bash install.sh
```

Verify:

```bash
systemctl status merox-agent
journalctl -u merox-agent -f
```

### Client setup (laptop)

```bash
pip install httpx
git clone https://github.com/meroxdotdev/merox-agent
cd merox-agent
echo "AGENT_SERVER_URL=http://<SERVER_TAILSCALE_IP>:8765" > .env
python3 client.py
```

Or just use the Telegram bot — no laptop setup needed.

---

## Adapting for your own homelab

Edit **`prompt.py`** to describe your infrastructure. That's the only file you need to change — what servers you have, where repos live, what services run.

**Runbooks** — add YAML files in `runbooks/` for standard procedures you want followed consistently (restart sequences, maintenance steps, etc.).

**Memory** — the agent reads/writes persistent notes and an action log via Bash:

```bash
# The agent calls these itself:
python3 memory/cli.py log "restarted jellyfin" "ok" restart kubernetes
python3 memory/cli.py note "jellyfin_issue" "recurring OOMKill, bump memory limit"

# And reads them when relevant:
cat memory/notes.json
tail -20 memory/events.jsonl
```

---

## Why a bash tool and not MCP?

[MCP (Model Context Protocol)](https://modelcontextprotocol.io) is the standard protocol for connecting AI models to external tools and data sources. It's the right choice when you want structured, typed interfaces to specific services — a Grafana MCP server for dashboards, a GitHub MCP server for PRs, etc.

This agent takes a different approach: one `bash` tool with full shell access. The reasons:

- **Infrastructure management maps naturally to shell commands.** `kubectl`, `docker`, `flux`, `talosctl`, `git` — these all have rich CLIs. Wrapping each in an MCP server adds complexity without adding capability.
- **Bash is composable.** Pipes, redirects, `jq`, `awk` — the agent can do multi-step operations in one call that would require multiple MCP round-trips.
- **Simpler setup.** No MCP servers to install or maintain. One API key, one Python process.

The trade-off: the bash tool is less structured than MCP — the agent decides what commands to run based on the system prompt and context, rather than calling explicitly defined functions. For a personal homelab with a trusted operator, this is fine.

If you want to add MCP servers on top (e.g., a Grafana MCP for metrics, or a Prometheus MCP for alerts), the Anthropic SDK supports connecting to MCP servers alongside custom tools.

---

## Usage

### Telegram

Message your bot — ask anything about your infra. `/clear` resets the conversation.

```
what is the status of the cluster?
which pods are not running?
show me traefik logs
how much disk is left?
reconcile flux-system
restart jellyfin
what changed in the infra repo this week?
```

### CLI client (laptop → server)

```bash
python3 client.py                        # interactive
python3 client.py "what pods are down?"  # one-shot
```

### CLI agent (on the server directly)

```bash
cd /srv/merox-agent
python3 agent.py                         # interactive
python3 agent.py "check cluster health"  # one-shot
```

---

## Project structure

```
merox-agent/
├── service.py          # FastAPI server — HTTP SSE endpoint + Telegram bot
├── agent.py            # Interactive CLI (runs directly on the server)
├── client.py           # Thin CLI client for laptop (connects via HTTP)
├── config.py           # All settings, loaded from .env
├── prompt.py           # System prompt — edit this for your infrastructure
├── tools.py            # Bash tool definition + executor (safety checks here)
├── memory/
│   ├── cli.py          # Memory CLI — agent calls this via bash to log/note
│   ├── events.jsonl    # Action log (gitignored)
│   └── notes.json      # Key-value notes (gitignored)
├── runbooks/
│   └── *.yaml          # Standard procedures (restart, flux reconcile, etc.)
├── install.sh          # Server setup — virtualenv + systemd service
├── requirements.txt
└── .env.example
```

---

## Disaster recovery

### New server

```bash
# 1. Provision Ubuntu 22.04+ (Oracle Cloud Free Tier, any VPS)
# 2. Install Tailscale: curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up
# 3. Install Python: sudo apt update && sudo apt install -y python3 python3-venv git
# 4. Clone + configure + install (see Quick start above)
```

### What lives where

| What | Where | Backed up? |
|------|-------|------------|
| Agent code | GitHub (this repo) | ✅ |
| Infra manifests | GitHub (your infra repo) | ✅ |
| Server `.env` | Only on server | ⚠️ Save it somewhere safe |
| K8s secrets (SOPS) | Git-encrypted | ✅ (need AGE key) |
| AGE key | `/srv/kubernetes/infrastructure/age.key` | ⚠️ Back this up |

---

## License

MIT
