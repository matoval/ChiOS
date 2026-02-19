#!/bin/bash
set -euo pipefail

# chiOS build script — runs inside OCI build context (rpm-ostree based)
# All changes here are baked into the immutable image layer.

echo "==> chiOS build.sh starting"

# ---------------------------------------------------------------------------
# 1. Add third-party RPM repos
# ---------------------------------------------------------------------------

# Hyprland COPR (not in standard Fedora repos)
FEDORA_VERSION=$(rpm -E %fedora)
curl -fsSL "https://copr.fedorainfracloud.org/coprs/solopasha/hyprland/repo/fedora-${FEDORA_VERSION}/solopasha-hyprland-fedora-${FEDORA_VERSION}.repo" \
    -o /etc/yum.repos.d/hyprland.repo

# VSCodium — install latest RPM directly from GitHub releases (no repo needed)
VSCODIUM_RPM_URL=$(curl -fsSL https://api.github.com/repos/VSCodium/vscodium/releases/latest \
  | python3 -c "import json,sys; assets=[a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if a['name'].endswith('el8.x86_64.rpm')]; print(assets[0])")
curl -fsSL "$VSCODIUM_RPM_URL" -o /tmp/codium.rpm

# ---------------------------------------------------------------------------
# 2. rpm-ostree package installs (baked into image)
# ---------------------------------------------------------------------------

rpm-ostree install \
  hyprland \
  waybar \
  fuzzel \
  kitty \
  sddm \
  pipewire \
  pipewire-alsa \
  pipewire-pulseaudio \
  wireplumber \
  xdg-utils \
  xorg-x11-server-Xwayland \
  xdg-desktop-portal-hyprland \
  polkit \
  lxqt-policykit \
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
  flatpak \
  \
  nodejs \
  npm \
  \
  grim \
  slurp \
  brightnessctl \
  \
  firefox

# Install VSCodium from downloaded RPM
rpm-ostree install /tmp/codium.rpm
rm /tmp/codium.rpm

echo "==> Core packages installed"

# ---------------------------------------------------------------------------
# 3. Install Python deps for chi-agent and chi-voice (into system Python)
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
# 5b. Install nerdctl binary (not in Fedora repos)
# ---------------------------------------------------------------------------

NERDCTL_URL="https://github.com/containerd/nerdctl/releases/download/v2.2.1/nerdctl-2.2.1-linux-amd64.tar.gz"
curl -fsSL "$NERDCTL_URL" -o /tmp/nerdctl.tar.gz
tar -C /usr/bin -xzf /tmp/nerdctl.tar.gz nerdctl
chmod +x /usr/bin/nerdctl
rm /tmp/nerdctl.tar.gz

echo "==> nerdctl installed"

# ---------------------------------------------------------------------------
# 6. Install chi-agent service
# ---------------------------------------------------------------------------

# Copy chi-agent to final location
mkdir -p /usr/lib/chi-agent
cp -r /usr/share/chi-agent/. /usr/lib/chi-agent/
pip3 install --no-cache-dir --prefix /usr -r /usr/lib/chi-agent/requirements.txt 2>/dev/null || true

# Install systemd unit (user service — needs D-Bus session bus)
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
# 9a. Set persistent kernel arguments
# ---------------------------------------------------------------------------

# console=ttyS0 ensures serial output (useful for debugging/headless)
# quiet removed so boot messages are visible
mkdir -p /usr/lib/bootc/kargs.d
cat > /usr/lib/bootc/kargs.d/console.toml << 'EOF'
kargs = ["console=ttyS0,115200", "console=tty0"]
EOF

echo "==> Kernel args configured"

# ---------------------------------------------------------------------------
# 9. Install chi-shell configs (skel → copied to new user homes)
# ---------------------------------------------------------------------------

mkdir -p /etc/skel/.config/hypr
mkdir -p /etc/skel/.config/waybar
mkdir -p /etc/skel/.config/fuzzel
mkdir -p /etc/skel/.config/kitty
mkdir -p /etc/skel/.config/containers/systemd

cp /usr/share/chi-shell/hyprland/hyprland.conf /etc/skel/.config/hypr/hyprland.conf
cp /usr/share/chi-shell/waybar/config.jsonc     /etc/skel/.config/waybar/config.jsonc
cp /usr/share/chi-shell/waybar/style.css        /etc/skel/.config/waybar/style.css
cp /usr/share/chi-shell/fuzzel/fuzzel.ini       /etc/skel/.config/fuzzel/fuzzel.ini
cp /usr/share/chi-shell/kitty/kitty.conf        /etc/skel/.config/kitty/kitty.conf

# Quadlets go to user systemd location via skel
cp /usr/share/chi-quadlets/ollama.container \
  /etc/skel/.config/containers/systemd/ollama.container

echo "==> chi-shell configs installed to /etc/skel"

# ---------------------------------------------------------------------------
# 10. SDDM config
# ---------------------------------------------------------------------------

mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/chios.conf << 'EOF'
[General]
DisplayServer=wayland
MinimumVT=1

[Wayland]
CompositorCommand=Hyprland
EOF

if [ -d /usr/share/chi-configs/sddm ]; then
  cp -r /usr/share/chi-configs/sddm/* /usr/share/sddm/themes/ 2>/dev/null || true
fi

echo "==> SDDM configured"

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
      {
        "Title": "Claude.ai",
        "URL": "https://claude.ai",
        "Placement": "toolbar"
      },
      {
        "Title": "ChatGPT",
        "URL": "https://chatgpt.com",
        "Placement": "toolbar"
      }
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
ConditionPathExists=!/var/lib/chi-firstboot.done
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

systemctl enable sddm

# Enable user services globally (applies to all users at login)
systemctl --global enable chi-agent
systemctl --global enable chi-firstboot

echo "==> System services enabled"

# ---------------------------------------------------------------------------
# 14. Flatpak remote (for post-install app installs)
# ---------------------------------------------------------------------------

# Note: flathub remote is added at first-boot (needs network), not here.
# We just ensure flatpak is configured to look for user remotes.

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
echo "==> chiOS build.sh complete"
