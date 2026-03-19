# merox-agent

Intelligent CLI agent for managing the merox.dev homelab infrastructure:
- **Oracle Cloud server** — Docker services, system health
- **Kubernetes cluster** — Talos OS, FluxCD GitOps, Longhorn
- **Website** — merox.dev source at github.com/meroxdotdev/merox

Built with the [Anthropic Claude API](https://docs.anthropic.com).

## Requirements

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com)
- **Tailscale** — required to reach the Oracle server and K8s cluster remotely

## Setup

```bash
git clone https://github.com/meroxdotdev/merox-agent
cd merox-agent

# Install deps + create /usr/local/bin/merox-agent launcher
sudo bash install.sh

# Configure
cp .env.example .env
# edit .env — set ANTHROPIC_API_KEY

# Run
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
run task longhorn:status
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
├── agent.py          # main entry point + agentic loop
├── config.py         # all configuration (env var overrides)
├── prompt.py         # system prompt with infra context
├── tools/
│   ├── kubernetes.py # kubectl, flux, talosctl
│   ├── server.py     # docker, systemctl, read/write files, shell
│   └── git_tools.py  # git status, diff, commit, push
├── install.sh        # setup script
├── requirements.txt
├── .env.example
└── .gitignore
```

## Security

- Sensitive files are blocked: `*.sops.yaml`, `age.key`, `kubeconfig`, `talosconfig`, private keys
- Destructive operations require confirmation
- The agent never commits secrets or exposes credentials in responses

## Tailscale note

This agent runs on the Oracle Cloud server. To use it from another machine:
1. Connect your device to Tailscale
2. SSH to the server: `ssh user@100.72.22.38` (or use the hostname)
3. Run `merox-agent`

The cluster nodes are also on the Tailscale network, so all `kubectl`/`flux`/`talosctl`
commands work transparently once you're connected.
