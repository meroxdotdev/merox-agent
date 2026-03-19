#!/bin/bash
# Merox Agent — server install script
# Run on the Oracle Cloud server after cloning the repo.
#
# Usage:
#   git clone https://github.com/meroxdotdev/merox-agent /srv/merox-agent
#   cd /srv/merox-agent
#   cp .env.example .env && nano .env   # fill in your values
#   sudo bash install.sh
#
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$AGENT_DIR/.venv"
PYTHON="$VENV/bin/python3"

# ── Checks ────────────────────────────────────────────────────────────────────

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run as root: sudo bash install.sh"
    exit 1
fi

if [[ ! -f "$AGENT_DIR/.env" ]]; then
    echo "ERROR: .env not found. Copy and edit it first:"
    echo "  cp $AGENT_DIR/.env.example $AGENT_DIR/.env"
    exit 1
fi

# ── Python virtualenv ─────────────────────────────────────────────────────────

echo "==> Creating Python virtualenv at $VENV ..."
python3 -m venv "$VENV"
"$PYTHON" -m pip install --upgrade pip --quiet
"$PYTHON" -m pip install -r "$AGENT_DIR/requirements.txt"
"$PYTHON" -c "import claude_agent_sdk, fastapi, uvicorn, telegram; print('All packages OK')"

# ── Claude Code permissions ───────────────────────────────────────────────────

echo "==> Configuring Claude Code tool permissions ..."
mkdir -p "$AGENT_DIR/.claude"
cat > "$AGENT_DIR/.claude/settings.json" << 'EOF'
{
  "permissions": {
    "allow": [
      "Bash(*)",
      "Read(*)",
      "Write(*)",
      "Edit(*)"
    ],
    "deny": []
  }
}
EOF

# ── systemd service ───────────────────────────────────────────────────────────

echo "==> Installing systemd service ..."

# Write the service file with the correct venv python path
cat > /etc/systemd/system/merox-agent.service << EOF
[Unit]
Description=Merox Infrastructure Agent
After=network.target tailscaled.service
Wants=tailscaled.service

[Service]
Type=simple
WorkingDirectory=$AGENT_DIR
ExecStart=$PYTHON $AGENT_DIR/service.py
EnvironmentFile=$AGENT_DIR/.env
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable merox-agent
systemctl restart merox-agent

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "Done! Service is running."
echo ""
echo "Check logs:     journalctl -u merox-agent -f"
echo "Check status:   systemctl status merox-agent"
echo ""
echo "─── On your laptop / phone ──────────────────────────────────────────────"
echo "  1. Connect Tailscale"
echo "  2. pip install httpx"
echo "  3. python3 client.py  (set AGENT_SERVER_URL in .env first)"
echo "  Or just message @meroxagentbot on Telegram."
