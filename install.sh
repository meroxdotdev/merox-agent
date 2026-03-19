#!/bin/bash
# Merox Agent — install script
# Run once after cloning the repo on a new machine.
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="/usr/local/bin/merox-agent"

echo "==> Installing Python dependencies..."
pip3 install -r "$AGENT_DIR/requirements.txt" --quiet

echo "==> Creating launcher at $LAUNCHER..."
cat > "$LAUNCHER" << EOF
#!/bin/bash
# Auto-load .env if present next to agent.py
if [ -f "$AGENT_DIR/.env" ]; then
    set -o allexport
    source "$AGENT_DIR/.env"
    set +o allexport
fi
exec python3 "$AGENT_DIR/agent.py" "\$@"
EOF
chmod +x "$LAUNCHER"

echo ""
echo "✓ Done. Setup:"
echo "  1. cp $AGENT_DIR/.env.example $AGENT_DIR/.env"
echo "  2. Edit .env — add your ANTHROPIC_API_KEY"
echo "  3. Run: merox-agent"
echo ""
echo "  NOTE: Tailscale must be connected to reach the cluster remotely."
