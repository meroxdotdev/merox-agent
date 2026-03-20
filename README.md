# merox-agent

An AI infrastructure agent for homelabs — chat with your server, Kubernetes cluster, and services via Telegram or CLI.

Built with the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python), backed by your Claude Pro subscription. No separate API key or per-token billing.

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
                                           │                └── Bash tool
                                           │                      ├── kubectl / flux / talosctl
                                           │                      ├── docker / docker compose
                                           │                      └── git, systemctl, ...
                                    Oracle Cloud / VPS
```

The Claude Agent SDK runs Claude Code as a subprocess with a Bash tool and a static system prompt describing your infrastructure. Claude figures out which commands to run, executes them, and returns a response.

Telegram responses stream live — the message is edited in real time as chunks arrive.

---

## Prerequisites

- A Linux server (Oracle Cloud Free Tier works great)
- [Tailscale](https://tailscale.com) on the server
- Python 3.11+, Node.js 20+
- Claude Code CLI installed and authenticated (`claude login`)
- A Claude Pro or Team subscription (used by Claude Code)
- A Telegram bot token from [@BotFather](https://t.me/BotFather) *(optional)*

---

## Setup

```bash
# 1. Install Node.js and Claude Code CLI
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g @anthropic-ai/claude-code
claude login   # authenticate with your Claude account

# 2. Clone and configure
sudo git clone https://github.com/meroxdotdev/merox-agent /srv/merox-agent
cd /srv/merox-agent
cp .env.example .env
nano .env   # fill in SERVER_TS_IP, TELEGRAM_BOT_TOKEN, etc.

# 3. Install (virtualenv + systemd service)
sudo bash install.sh
```

Verify:

```bash
systemctl status merox-agent
journalctl -u merox-agent -f
```

---

## Adapting for your own homelab

Edit **`prompt.py`** — describe your infrastructure: what servers you have, where repos live, what services run. That's the only file you need to change.

**Runbooks** — add YAML files in `runbooks/` for standard procedures (restart sequences, maintenance steps). The agent follows them when a task matches.

**Memory** — the agent reads/writes persistent notes and an action log via Bash:

```bash
python3 memory/cli.py log "restarted jellyfin" "ok" restart kubernetes
python3 memory/cli.py note "jellyfin_issue" "recurring OOMKill, bump memory limit"

cat memory/notes.json
tail -20 memory/events.jsonl
```

---

## Usage

**Telegram** — message your bot, `/clear` resets the conversation.

```
what is the status of the cluster?
which pods are not running?
show me traefik logs
how much disk is left?
reconcile flux-system
restart jellyfin
what changed in the infra repo this week?
```

**CLI client (laptop)**

```bash
pip install httpx
echo "AGENT_SERVER_URL=http://<SERVER_TS_IP>:8765" > .env
python3 client.py
```

**CLI agent (on the server directly)**

```bash
python3 agent.py
python3 agent.py "check cluster health"
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
├── memory/
│   ├── cli.py          # Memory CLI — agent calls this via Bash to log/note
│   ├── events.jsonl    # Action log (gitignored)
│   └── notes.json      # Key-value notes (gitignored)
├── runbooks/
│   └── *.yaml          # Standard procedures
├── install.sh          # Server setup — Node.js + Claude Code + virtualenv + systemd
├── requirements.txt
└── .env.example
```

---

## Security

- **Tailscale only** — port 8765 is not exposed publicly
- **Telegram whitelist** — only your `TELEGRAM_USER_ID` can interact with the bot
- **Behavioral rules** — system prompt instructs Claude to never touch secrets (`age.key`, `*.sops.yaml`, `.env`) and to confirm before destructive operations
- **Session persistence** — conversation history saved to disk, survives restarts

---

## Disaster recovery

```bash
# New server: provision Ubuntu 22.04+, install Tailscale, then:
sudo git clone https://github.com/meroxdotdev/merox-agent /srv/merox-agent
cd /srv/merox-agent && cp .env.example .env && nano .env
sudo bash install.sh && claude login
```

| What | Where | Backed up? |
|------|-------|------------|
| Agent code | GitHub | ✅ |
| Server `.env` | Only on server | ⚠️ Save it |
| K8s secrets (SOPS) | Git-encrypted | ✅ (need AGE key) |
| AGE key | `/srv/kubernetes/infrastructure/age.key` | ⚠️ Back this up |

---

## License

MIT
