#!/bin/bash
# Merox Agent — server install script
# Run on the Oracle Cloud server after cloning.
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing Python dependencies..."
pip3 install -r "$AGENT_DIR/requirements.txt" --quiet

echo "==> Installing systemd service..."
cp "$AGENT_DIR/merox-agent.service" /etc/systemd/system/merox-agent.service
systemctl daemon-reload
systemctl enable merox-agent
systemctl restart merox-agent

echo "==> Creating client launcher /usr/local/bin/merox-agent..."
cat > /usr/local/bin/merox-agent << EOF
#!/bin/bash
exec python3 $AGENT_DIR/client.py "\$@"
EOF
chmod +x /usr/local/bin/merox-agent

echo ""
echo "✓ Done!"
echo ""
echo "Check service:  systemctl status merox-agent"
echo "Local client:   merox-agent"
echo ""
echo "─── On any other device (laptop etc.) ───────────────────────────────"
echo "  1. Connect Tailscale"
echo "  2. pip install httpx"
echo "  3. Copy client.py here"
echo "  4. echo 'AGENT_SERVER_URL=http://100.72.22.38:8765' > .env"
echo "  5. python3 client.py"
