#!/bin/bash
# chiOS first-boot setup script
# Runs once as a systemd user service after first login.
# Self-disables after successful completion.

set -euo pipefail

DONE_FILE="/var/lib/chi-firstboot.done"
LOG_FILE="$HOME/.local/share/chi/firstboot.log"

mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "==> chiOS first-boot setup starting: $(date)"

# ---------------------------------------------------------------------------
# Guard: only run once
# ---------------------------------------------------------------------------
if [ -f "$DONE_FILE" ]; then
    echo "==> First-boot already completed. Exiting."
    exit 0
fi

# ---------------------------------------------------------------------------
# Helper: show desktop notification
# ---------------------------------------------------------------------------
notify() {
    notify-send -t 5000 "chiOS Setup" "$1" 2>/dev/null || echo "NOTIFY: $1"
}

# ---------------------------------------------------------------------------
# 1. Add Flathub remote
# ---------------------------------------------------------------------------
echo "==> Adding Flathub remote..."
flatpak remote-add --user --if-not-exists flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo
echo "    Flathub remote added"

# ---------------------------------------------------------------------------
# 2. Set up Podman Quadlet for Ollama
# ---------------------------------------------------------------------------
echo "==> Setting up Ollama Podman Quadlet..."

QUADLET_DIR="$HOME/.config/containers/systemd"
mkdir -p "$QUADLET_DIR"

# quadlet is already placed in skel, but ensure it's present
if [ ! -f "$QUADLET_DIR/ollama.container" ]; then
    cp /usr/share/chi-quadlets/ollama.container "$QUADLET_DIR/ollama.container"
fi

systemctl --user daemon-reload
systemctl --user enable --now ollama
echo "    Ollama Quadlet enabled"

# ---------------------------------------------------------------------------
# 3. Wait for Ollama to be ready
# ---------------------------------------------------------------------------
echo "==> Waiting for Ollama to start..."
notify "Setting up chiOS AI — pulling language model (this may take a few minutes)…"

RETRIES=30
for i in $(seq 1 $RETRIES); do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "    Ollama is ready"
        break
    fi
    if [ "$i" -eq "$RETRIES" ]; then
        echo "    WARNING: Ollama did not start within timeout. Will retry on next boot."
        exit 1
    fi
    sleep 5
done

# ---------------------------------------------------------------------------
# 4. Pull Ollama model (Qwen 3 8B Q4_K_M)
# ---------------------------------------------------------------------------
echo "==> Pulling Qwen 3 8B model (~5GB download)..."
notify "Downloading Qwen 3 8B model (~5GB). chi will be ready when complete."

ollama pull qwen3:8b

echo "    Model pulled successfully"

# ---------------------------------------------------------------------------
# 5. Create chi model alias from Modelfile
# ---------------------------------------------------------------------------
echo "==> Creating chi model from Modelfile..."
if [ -f /usr/lib/chi-agent/Modelfile ]; then
    ollama create chi -f /usr/lib/chi-agent/Modelfile
    echo "    chi model created"
else
    echo "    WARNING: Modelfile not found at /usr/lib/chi-agent/Modelfile"
fi

# ---------------------------------------------------------------------------
# 6. Pre-download Whisper medium model
# ---------------------------------------------------------------------------
echo "==> Pre-downloading Whisper medium model..."
notify "Downloading Whisper voice model…"
python3 /usr/lib/chi-voice/whisper_setup.py

echo "    Whisper model ready"

# ---------------------------------------------------------------------------
# 7. Set up containerd rootless for envclone
# ---------------------------------------------------------------------------
echo "==> Configuring containerd rootless..."
if command -v containerd > /dev/null; then
    # Enable rootless containerd for current user
    containerd-rootless-setuptool.sh install 2>/dev/null || \
    echo "    WARNING: containerd rootless setup failed (may require root)"

    systemctl --user enable --now containerd
    echo "    containerd rootless enabled"
else
    echo "    WARNING: containerd not found"
fi

# ---------------------------------------------------------------------------
# 8. Configure Claude Code MCP server for chi-agent
# ---------------------------------------------------------------------------
echo "==> Configuring Claude Code MCP integration..."

CLAUDE_CONFIG_DIR="$HOME/.config/claude"
mkdir -p "$CLAUDE_CONFIG_DIR"

MCP_CONFIG="$CLAUDE_CONFIG_DIR/mcp_servers.json"
if [ ! -f "$MCP_CONFIG" ]; then
    cat > "$MCP_CONFIG" << 'EOF'
{
  "mcpServers": {
    "chi": {
      "command": "python3",
      "args": ["/usr/lib/chi-agent/mcp_server.py", "--standalone"],
      "description": "chiOS AI agent — control the OS from Claude Code"
    }
  }
}
EOF
    echo "    Claude Code MCP config written"
fi

# ---------------------------------------------------------------------------
# 9. Start chi-agent user service
# ---------------------------------------------------------------------------
echo "==> Starting chi-agent..."
systemctl --user enable --now chi-firstboot 2>/dev/null || true
# The system chi-agent.service handles system-level, but we also want user
systemctl --user start chi-agent 2>/dev/null || echo "    (chi-agent runs as system service)"

# ---------------------------------------------------------------------------
# 10. Final
# ---------------------------------------------------------------------------
echo "==> chiOS first-boot complete!"
notify "chiOS setup complete! Press Super+Space to talk to chi."

# Mark complete so this doesn't run again
sudo touch "$DONE_FILE" 2>/dev/null || touch "$HOME/.chi-firstboot.done"

# Self-disable
systemctl --user disable chi-firstboot 2>/dev/null || true

echo "==> First-boot service disabled. Enjoy chiOS."
