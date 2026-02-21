#!/bin/bash
set -euo pipefail

# chiOS build script — runs inside OCI build context
# All changes here are baked into the immutable image layer.

echo "==> chiOS build.sh starting"

# ---------------------------------------------------------------------------
# 1. Add third-party RPM repos
# ---------------------------------------------------------------------------

# VSCodium — install latest RPM directly from GitHub releases
VSCODIUM_RPM_URL=$(curl -fsSL https://api.github.com/repos/VSCodium/vscodium/releases/latest \
  | python3 -c "import json,sys; assets=[a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if a['name'].endswith('el8.x86_64.rpm')]; print(assets[0])")
curl -fsSL "$VSCODIUM_RPM_URL" -o /tmp/codium.rpm

# ---------------------------------------------------------------------------
# 2. rpm-ostree package installs (baked into image)
# ---------------------------------------------------------------------------

rpm-ostree install \
  \
  labwc \
  gtk4-layer-shell \
  xdg-desktop-portal-wlr \
  \
  greetd \
  cage \
  \
  kitty \
  nautilus \
  \
  pipewire \
  pipewire-alsa \
  pipewire-pulseaudio \
  wireplumber \
  \
  xdg-utils \
  xdg-user-dirs \
  xorg-x11-server-Xwayland \
  polkit \
  lxqt-policykit \
  \
  adwaita-icon-theme \
  wl-clipboard \
  \
  containerd \
  \
  python3 \
  python3-pip \
  python3-gobject \
  python3-dbus \
  python3-pydantic \
  \
  ffmpeg \
  alsa-utils \
  \
  git \
  curl \
  wget \
  jq \
  zstd \
  flatpak \
  \
  nodejs \
  npm \
  \
  grim \
  slurp \
  brightnessctl \
  \
  NetworkManager-tui \
  network-manager-applet \
  \
  firefox

# Install VSCodium from downloaded RPM
rpm-ostree install /tmp/codium.rpm
rm /tmp/codium.rpm

echo "==> Core packages installed"

# ---------------------------------------------------------------------------
# 3. Install Python deps (system-wide)
# ---------------------------------------------------------------------------

pip3 install --no-cache-dir --prefix /usr \
  requests \
  pydbus \
  pyaudio \
  faster-whisper \
  mcp

echo "==> Python packages installed"

# ---------------------------------------------------------------------------
# 4. Install Claude Code CLI
# ---------------------------------------------------------------------------

HOME=/tmp npm install -g --prefix /usr --cache /tmp/npm-cache @anthropic-ai/claude-code
rm -rf /tmp/npm-cache

echo "==> Claude Code installed"

# ---------------------------------------------------------------------------
# 5. Install envclone binary
# ---------------------------------------------------------------------------

ENVCLONE_URL="https://github.com/matoval/envclone/releases/download/v0.1.0/envclone"
curl -fsSL "$ENVCLONE_URL" -o /usr/bin/envclone
chmod +x /usr/bin/envclone

echo "==> envclone installed"

# ---------------------------------------------------------------------------
# 5b. Install nerdctl binary
# ---------------------------------------------------------------------------

NERDCTL_URL="https://github.com/containerd/nerdctl/releases/download/v2.2.1/nerdctl-2.2.1-linux-amd64.tar.gz"
curl -fsSL "$NERDCTL_URL" -o /tmp/nerdctl.tar.gz
tar -C /usr/bin -xzf /tmp/nerdctl.tar.gz nerdctl
chmod +x /usr/bin/nerdctl
rm /tmp/nerdctl.tar.gz

echo "==> nerdctl installed"

# ---------------------------------------------------------------------------
# 5c. Install Ollama CLI binary
# ---------------------------------------------------------------------------

OLLAMA_VERSION=$(curl -fsSL https://api.github.com/repos/ollama/ollama/releases/latest \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])")
curl -fsSL "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-amd64.tar.zst" \
  -o /tmp/ollama.tar.zst
tar -C /usr -xf /tmp/ollama.tar.zst
rm /tmp/ollama.tar.zst

echo "==> Ollama CLI installed"

# ---------------------------------------------------------------------------
# 6. Install chi-agent
# ---------------------------------------------------------------------------

mkdir -p /usr/lib/chi-agent
cp -r /usr/share/chi-agent/. /usr/lib/chi-agent/
pip3 install --no-cache-dir --prefix /usr -r /usr/lib/chi-agent/requirements.txt 2>/dev/null || true

cp /usr/lib/chi-agent/chi-agent.service /usr/lib/systemd/user/chi-agent.service

echo "==> chi-agent installed"

# ---------------------------------------------------------------------------
# 7. Install chi-overlay
# ---------------------------------------------------------------------------

mkdir -p /usr/lib/chi-overlay
cp -r /usr/share/chi-overlay/. /usr/lib/chi-overlay/

echo "==> chi-overlay installed"

# ---------------------------------------------------------------------------
# 8. Install chi-voice
# ---------------------------------------------------------------------------

mkdir -p /usr/lib/chi-voice
cp -r /usr/share/chi-voice/. /usr/lib/chi-voice/
chmod +x /usr/lib/chi-voice/voice.sh

echo "==> chi-voice installed"

# ---------------------------------------------------------------------------
# 8b. Install chi-shell
# ---------------------------------------------------------------------------

mkdir -p /usr/lib/chi-shell /usr/share/chi-shell
cp -r /usr/share/chi-shell-src/. /usr/lib/chi-shell/
# CSS goes in /usr/share for chi-shell to load
cp /usr/lib/chi-shell/chi-shell.css /usr/share/chi-shell/chi-shell.css
chmod +x /usr/lib/chi-shell/chi-shell.py
ln -sf /usr/lib/chi-shell/chi-shell.py /usr/bin/chi-shell

echo "==> chi-shell installed"

# ---------------------------------------------------------------------------
# 8c. Install chi-greeter
# ---------------------------------------------------------------------------

mkdir -p /usr/lib/chi-greeter /usr/share/chi-greeter
cp -r /usr/share/chi-greeter-src/. /usr/lib/chi-greeter/
cp /usr/lib/chi-greeter/chi-greeter.css /usr/share/chi-greeter/chi-greeter.css
chmod +x /usr/lib/chi-greeter/chi-greeter.py
ln -sf /usr/lib/chi-greeter/chi-greeter.py /usr/bin/chi-greeter

echo "==> chi-greeter installed"

# ---------------------------------------------------------------------------
# 8d. Install chi-overlay-show helper
# ---------------------------------------------------------------------------

cat > /usr/bin/chi-overlay-show << 'EOF'
#!/bin/bash
# Show chi-overlay — launches or re-activates the running instance
exec python3 /usr/lib/chi-overlay/overlay.py
EOF
chmod +x /usr/bin/chi-overlay-show

echo "==> chi-overlay-show installed"

# ---------------------------------------------------------------------------
# 9. Kernel arguments
# ---------------------------------------------------------------------------

mkdir -p /usr/lib/bootc/kargs.d
cat > /usr/lib/bootc/kargs.d/console.toml << 'EOF'
kargs = ["console=ttyS0,115200", "console=tty0"]
EOF

echo "==> Kernel args configured"

# ---------------------------------------------------------------------------
# 9b. chi-shell skel configs (labwc + apps.json)
# ---------------------------------------------------------------------------

mkdir -p /etc/skel/.config/labwc
mkdir -p /etc/skel/.config/chi-shell
mkdir -p /etc/skel/.config/containers/systemd

cp /usr/lib/chi-shell/labwc/rc.xml      /etc/skel/.config/labwc/rc.xml
cp /usr/lib/chi-shell/labwc/autostart   /etc/skel/.config/labwc/autostart
cp /usr/lib/chi-shell/labwc/menu.xml    /etc/skel/.config/labwc/menu.xml
chmod +x /etc/skel/.config/labwc/autostart

cp /usr/lib/chi-shell/apps.json /etc/skel/.config/chi-shell/apps.json

# Quadlet for Ollama container
cp /usr/share/chi-quadlets/ollama.container \
  /etc/skel/.config/containers/systemd/ollama.container

echo "==> chi-shell skel configs installed"

# ---------------------------------------------------------------------------
# 10. greetd config (replaces SDDM)
# ---------------------------------------------------------------------------

mkdir -p /etc/greetd

cat > /etc/greetd/config.toml << 'EOF'
[terminal]
vt = 1

[default_session]
# cage provides a minimal Wayland compositor for chi-greeter
command = "cage -s -- chi-greeter"
user = "_greeter"
EOF

# Create dedicated greeter system user
useradd -r -M -s /sbin/nologin -c "greetd greeter" _greeter 2>/dev/null || true

systemctl enable greetd

echo "==> greetd configured"

# ---------------------------------------------------------------------------
# 11. Firefox pre-configuration
# ---------------------------------------------------------------------------

FIREFOX_POLICIES_DIR="/usr/lib64/firefox/distribution"
mkdir -p "$FIREFOX_POLICIES_DIR"

if [ -f /usr/share/chi-configs/firefox/user.js ]; then
  mkdir -p /etc/skel/.mozilla/firefox/default
  cp /usr/share/chi-configs/firefox/user.js \
    /etc/skel/.mozilla/firefox/default/user.js
fi

cat > "$FIREFOX_POLICIES_DIR/policies.json" << 'EOF'
{
  "policies": {
    "DisableTelemetry": true,
    "DisableFirefoxStudies": true,
    "Bookmarks": [
      {"Title": "Claude.ai",  "URL": "https://claude.ai",      "Placement": "toolbar"},
      {"Title": "ChatGPT",    "URL": "https://chatgpt.com",    "Placement": "toolbar"}
    ]
  }
}
EOF

echo "==> Firefox pre-configured"

# ---------------------------------------------------------------------------
# 12. Install firstboot service
# ---------------------------------------------------------------------------

cp /usr/share/chi-post-install/firstboot.sh /usr/bin/chi-firstboot.sh
chmod +x /usr/bin/chi-firstboot.sh

cat > /usr/lib/systemd/user/chi-firstboot.service << 'EOF'
[Unit]
Description=chiOS First Boot Setup
ConditionPathExists=!%h/.local/share/chi/firstboot.done
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/chi-firstboot.sh
RemainAfterExit=yes

[Install]
WantedBy=default.target
EOF

# ---------------------------------------------------------------------------
# 13. Enable system-level services
# ---------------------------------------------------------------------------

# User services (enabled for all users at login)
systemctl --global enable chi-agent
systemctl --global enable chi-firstboot

echo "==> System services enabled"

# ---------------------------------------------------------------------------
# 15. bootc auto-update timer
# ---------------------------------------------------------------------------

cat > /usr/lib/systemd/system/bootc-update.service << 'EOF'
[Unit]
Description=bootc Automatic Update
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/bootc upgrade
EOF

cat > /usr/lib/systemd/system/bootc-update.timer << 'EOF'
[Unit]
Description=Weekly bootc Automatic Update

[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl enable bootc-update.timer

echo "==> bootc auto-update timer enabled"

# ---------------------------------------------------------------------------
# 16. Pre-bundle Ollama container image (~2GB, avoids first-boot pull)
# ---------------------------------------------------------------------------

mkdir -p /usr/share/chi-ollama
echo "==> Pre-pulling Ollama container image (~2GB)..."
skopeo copy docker://docker.io/ollama/ollama:latest \
    docker-archive:/usr/share/chi-ollama/ollama.tar:docker.io/ollama/ollama:latest
echo "==> Ollama image bundled"

echo "==> chiOS build.sh complete"
