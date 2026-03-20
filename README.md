# merox-agent

An AI infrastructure agent for homelabs — chat with your server, Kubernetes cluster, and services via Telegram or CLI.

Built with [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python). The agent runs on your server and has full shell access — it can check pod status, restart services, tail logs, run kubectl commands, commit GitOps changes, and anything else you'd do in a terminal.

**Interfaces:** Telegram bot (phone) · CLI client (laptop) · HTTP API (SSE streaming)

---

## How it works

```
Phone / Laptop
    │
    ├── Telegram bot ──────────────────────┐
    └── client.py ─── HTTP (Tailscale) ───►│
                                           │  service.py  (FastAPI)
                                           │    └── Claude Agent SDK
                                           │          └── Claude Code CLI
                                           │                └── Bash
                                           │                      ├── kubectl / flux / talosctl
                                           │                      ├── docker / docker compose
                                           │                      └── git, systemctl, ...
                                    Oracle Cloud / VPS
```

The agent uses Claude Code CLI as its execution engine — no custom tool definitions needed. The system prompt describes your infrastructure; the agent figures out which commands to run.

---

## Quick start

### Prerequisites

- A Linux server (Oracle Cloud Free Tier works great)
- [Tailscale](https://tailscale.com) on the server (recommended, keeps port 8765 off the internet)
- Python 3.11+
- Node.js 20+ and Claude Code CLI, authenticated

```bash
# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install and authenticate Claude Code
sudo npm install -g @anthropic-ai/claude-code
claude  # follow the OAuth prompt
```

### Server setup

```bash
# Clone
sudo git clone https://github.com/meroxdotdev/merox-agent /srv/merox-agent
cd /srv/merox-agent

# Configure
cp .env.example .env
nano .env  # fill in SERVER_TS_IP, INFRA_REPO, TELEGRAM_BOT_TOKEN, etc.

# Install (virtualenv + systemd service)
sudo bash install.sh
```

That's it. Check it's running:

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

Or just use the Telegram bot — no laptop setup needed at all.

---

## Adapting for your own homelab

The only file you need to edit is **`prompt.py`**. Change the infrastructure description to match your setup — what servers you have, where your repos live, what services you run.

Everything else (memory, runbooks, service wiring) works out of the box.

**Runbooks** — add YAML files in `runbooks/` for standard procedures you want the agent to follow consistently (restart sequences, maintenance steps, etc.). See the existing ones for the format.

**Memory** — the agent reads/writes `memory/notes.json` and `memory/events.jsonl` via Bash. It persists decisions, incidents, and preferences across sessions automatically.

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
├── service.py          # FastAPI server — HTTP endpoint + Telegram bot
├── agent.py            # Interactive CLI (runs directly on the server)
├── client.py           # Thin CLI client for laptop (connects to service.py via HTTP)
├── config.py           # All settings, loaded from .env
├── prompt.py           # System prompt — edit this to describe your infrastructure
├── memory/
│   ├── cli.py          # Memory read/write CLI (called by the agent via Bash)
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
# 1. Provision Ubuntu 22.04+ (Oracle Cloud Free Tier, VPS, etc.)
# 2. Install Tailscale: curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up
# 3. Install Python: sudo apt update && sudo apt install -y python3 python3-venv git
# 4. Install Node.js + Claude Code (see Prerequisites above)
# 5. Clone + configure + install (see Quick start above)
```

### New laptop

```bash
# 1. Connect Tailscale
# 2. pip install httpx
# 3. Clone repo, set AGENT_SERVER_URL in .env, run python3 client.py
```

### What lives where

| What | Where | Backed up? |
|------|-------|------------|
| Agent code | GitHub (this repo) | ✅ |
| Infra manifests | GitHub (your infra repo) | ✅ |
| Server `.env` | Only on server | ⚠️ Save it somewhere safe |
| K8s secrets (SOPS) | Git-encrypted | ✅ (need AGE key) |
| AGE key | `/srv/kubernetes/infrastructure/age.key` | ⚠️ Back this up — losing it = losing all secrets |

---

## License

MIT
