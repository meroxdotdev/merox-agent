# merox-agent

Intelligent CLI agent for managing the merox.dev homelab infrastructure:
- **Oracle Cloud server** — Docker services, system health
- **Kubernetes cluster** — Talos OS, FluxCD GitOps, Longhorn
- **Website** — merox.dev source at github.com/meroxdotdev/merox

Built with the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) — uses your **Claude Code account**, no separate API key needed.

## Requirements

- Python 3.11+
- Node.js 18+ (for Claude Code CLI)
- **Claude Code CLI** — authenticated with your account
- **Tailscale** — required to reach the Oracle server and K8s cluster remotely

## Setup

```bash
git clone https://github.com/meroxdotdev/merox-agent
cd merox-agent

# 1. Install Claude Code CLI (if not already installed)
npm install -g @anthropic-ai/claude-code

# 2. Authenticate once (follow the login prompts)
claude

# 3. Install deps + create /usr/local/bin/merox-agent launcher
sudo bash install.sh

# 4. Configure
cp .env.example .env
# edit .env — set SERVER_TS_IP, SERVER_NAME, etc. (no API key needed)

# 5. Run
merox-agent
```

## Usage

```bash
merox-agent                              # interactive chat (remembers context)
merox-agent "what pods are failing?"     # one-shot question

# In interactive mode:
clear   # reset conversation history
exit    # quit
```

## Example questions

```
# Cluster
what is the status of the cluster?
show me all pods that are not running
what does the longhorn helmrelease look like?
reconcile flux-system

# Server
what docker containers are running?
show me the last 50 lines of traefik logs
how much disk is left on the server?
restart the netdata container

# GitOps
what changed in the infra repo recently?
add a new app called 'myapp' to the default namespace
commit and push the changes

# Website
what's the last commit on the website repo?
```

## Project structure

```
merox-agent/
├── agent.py          # standalone local agent (uses Anthropic API directly)
├── service.py        # HTTP server (uses Claude Agent SDK — no API key)
├── client.py         # thin remote client (connects to service.py over Tailscale)
├── config.py         # all configuration (env var overrides)
├── prompt.py         # system prompt with infra context
├── tools/
│   ├── kubernetes.py # kubectl, flux, talosctl (used by agent.py)
│   ├── server.py     # docker, systemctl, shell (used by agent.py)
│   └── git_tools.py  # git status, diff, commit, push (used by agent.py)
├── install.sh        # setup script
├── requirements.txt
├── .env.example
└── .gitignore
```

## Two modes

| Mode | File | Auth | Use case |
|------|------|------|----------|
| Local agent | `agent.py` | `ANTHROPIC_API_KEY` | Direct SSH access to server |
| HTTP service | `service.py` | Claude Code CLI login | Remote via Tailscale from any device |

The **HTTP service** (`service.py`) is the recommended mode — run it once on the Oracle server and connect from any device via `client.py`.

## Security

- Sensitive files are blocked: `*.sops.yaml`, `age.key`, `kubeconfig`, `talosconfig`, private keys
- Destructive operations require confirmation
- The agent never commits secrets or exposes credentials in responses

## Tailscale note

The service runs on the Oracle Cloud server. To connect from another device:
1. Connect your device to Tailscale
2. `pip install httpx && python3 client.py`

The cluster nodes are also on the Tailscale network, so all `kubectl`/`flux`/`talosctl`
commands work transparently once connected.
