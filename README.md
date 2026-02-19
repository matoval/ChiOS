# chiOS

An AI-native OS for software engineers. Fedora Atomic base, Hyprland UI, local LLM as the primary interface — press `Super+Space` and tell it what to do.

```
Super+Space → "open firefox"           → Firefox launches
Super+Space → "install htop"           → flatpak installs htop
Super+Space → "new python project env" → envclone init python myproject
Super+V     → say "open the terminal"  → Kitty opens
```

---

## Architecture

```
Build:  Containerfile → OCI image (GHCR) → bootc-image-builder → chiOS.iso

Runtime:
  Base:  Fedora Atomic (ghcr.io/ublue-os/base-main) — immutable, rpm-ostree
  UI:    Hyprland + Waybar + Fuzzel + Kitty + SDDM
  AI:    Ollama (Podman Quadlet) + Qwen 3 8B Q4_K_M (CPU, ~5GB RAM)
         chi-agent: Python service, D-Bus + MCP
         chi-overlay: GTK4 popup (Super+Space)
         chi-voice: Whisper push-to-talk (Super+V)
```

**Why immutable?** The base OS is read-only. Rollback is one command. The AI can't accidentally brick the system. All dev work goes in containers via envclone.

**Package tiers:**
| Tier | Tool | Use for | Reboot? |
|------|------|---------|---------|
| 1 | flatpak | GUI desktop apps | No |
| 2 | rpm-ostree | System packages, drivers | Yes |
| 3 | envclone | Dev environments | No |

---

## Project Structure

```
chiOS/
├── Containerfile               # OS image definition
├── build.sh                    # Package installs + system config
├── iso.sh                      # Generate installable ISO
│
├── .github/workflows/
│   └── build.yml               # CI: build OCI image → GHCR; ISO on release
│
├── chi-agent/                  # AI orchestration service
│   ├── agent.py                # Ollama API loop + tool dispatch
│   ├── mcp_server.py           # MCP server (Claude Code integration)
│   ├── dbus_service.py         # io.chios.Agent session D-Bus service
│   ├── waybar_status.py        # Waybar AI status dot module
│   ├── tools/
│   │   ├── apps.py             # Launch apps via binary / hyprctl / gtk-launch
│   │   ├── packages.py         # flatpak (immediate) + rpm-ostree (staged)
│   │   ├── shell.py            # subprocess runner, deny-pattern safety
│   │   ├── system.py           # NetworkManager + systemd via D-Bus
│   │   └── envclone.py         # envclone CLI wrappers
│   ├── Modelfile               # Ollama system prompt (chi personality)
│   ├── chi-agent.service       # systemd unit
│   └── requirements.txt
│
├── chi-overlay/                # GTK4 AI prompt popup
│   ├── overlay.py              # Super+Space floating window
│   └── overlay.css
│
├── chi-voice/                  # Whisper push-to-talk
│   ├── voice.sh                # Super+V: arecord → whisper → chi-agent
│   ├── voice-stop.sh           # Key release handler
│   ├── transcribe.py           # faster-whisper medium, CPU int8
│   └── whisper_setup.py        # Pre-download model at first-boot
│
├── chi-shell/
│   ├── hyprland/hyprland.conf  # Keybindings, window rules, startup
│   ├── waybar/config.jsonc     # Workspaces, clock, AI status, net, audio
│   ├── waybar/style.css
│   ├── fuzzel/fuzzel.ini       # App launcher
│   └── kitty/kitty.conf        # Terminal
│
├── quadlets/
│   └── ollama.container        # Podman Quadlet: Ollama as rootless user service
│
├── configs/
│   ├── sddm/chios/             # Login screen
│   └── firefox/user.js         # Pre-configured bookmarks: Claude.ai, ChatGPT
│
└── post-install/
    └── firstboot.sh            # First-boot: pull model, set up containerd, configure MCP
```

---

## Build

### Prerequisites

- Podman or Docker
- `buildah` (for local OCI builds)

### 1. Build OCI image locally

```bash
podman build -t localhost/chios:dev -f Containerfile .
```

### 2. Generate ISO

```bash
./iso.sh                              # uses ghcr.io/matoval/chios:latest
./iso.sh localhost/chios:dev          # use local build
```

Output: `./output/bootiso/install.iso`

### 3. Test in QEMU

```bash
# Create a virtual disk
qemu-img create -f qcow2 test.qcow2 40G

# Boot from ISO
qemu-system-x86_64 -enable-kvm -m 8G \
  -cdrom output/bootiso/install.iso \
  -drive file=test.qcow2,if=virtio \
  -vga virtio \
  -cpu host
```

---

## CI/CD

GitHub Actions (`.github/workflows/build.yml`) runs on every push to `main`:

1. Builds OCI image with `buildah`
2. Tags with `latest` + git SHA
3. Pushes to `ghcr.io/matoval/chios`

On release tags (`v*`):
- Also runs `iso.sh`
- Attaches `install.iso` to the GitHub release

---

## Keybindings

| Key | Action |
|-----|--------|
| `Super+Space` | Open chi AI overlay |
| `Super+V` (hold) | Push-to-talk voice input |
| `Super+Enter` | Kitty terminal |
| `Super+D` | Fuzzel app launcher |
| `Super+Q` | Close window |
| `Super+F` | Fullscreen |
| `Super+T` | Toggle floating |
| `Super+1–9` | Switch workspace |
| `Super+Shift+1–9` | Move window to workspace |
| `Super+H/J/K/L` | Move focus |
| `Super+Shift+H/J/K/L` | Move window |

---

## AI Tools

chi-agent exposes these tools to the local LLM and to Claude Code via MCP:

| Tool | Description |
|------|-------------|
| `launch_app` | Launch any desktop app |
| `install_app` | Install via flatpak (immediate) or rpm-ostree (staged) |
| `install_system` | Install system package via rpm-ostree |
| `remove_app` | Remove flatpak or rpm-ostree package |
| `run_shell` | Run shell command (30s timeout, deny-pattern safety) |
| `get_network_status` | Current network connections |
| `set_network` | Enable/disable a connection |
| `manage_service` | Start/stop/restart/status systemd units |
| `envclone_init` | Init new dev environment |
| `envclone_up` | Start dev environment |
| `envclone_down` | Stop dev environment |
| `envclone_code` | Open VSCodium in dev environment |

### Claude Code MCP integration

After first-boot, Claude Code is pre-configured with the chi MCP server. You can use chi tools directly in Claude Code sessions — the same tools the overlay uses.

To add manually:
```json
// ~/.config/claude/mcp_servers.json
{
  "mcpServers": {
    "chi": {
      "command": "python3",
      "args": ["/usr/lib/chi-agent/mcp_server.py", "--standalone"]
    }
  }
}
```

---

## First Boot

On first login, `chi-firstboot.service` runs automatically and:

1. Adds Flathub remote
2. Enables Ollama Podman Quadlet (`~/.config/containers/systemd/ollama.container`)
3. Pulls `qwen3:8b` model (~5GB)
4. Creates `chi` Ollama model from Modelfile
5. Pre-downloads Whisper medium model
6. Sets up containerd rootless (required by envclone)
7. Writes Claude Code MCP config
8. Self-disables

Progress is shown via desktop notifications.

---

## Updates & Rollback

Updates are atomic and staged — the running system is never modified mid-update.

```bash
# Check for updates (runs weekly via bootc-update.timer)
bootc upgrade

# List deployments
rpm-ostree status

# Roll back to previous deployment
rpm-ostree rollback

# Reboot into rollback immediately
systemctl reboot
```

---

## Pre-installed Software

| App | Install method |
|-----|---------------|
| Claude Code | curl install in build.sh |
| VSCodium | rpm-ostree (vscodium RPM repo) |
| envclone | binary from GitHub releases |
| Firefox | rpm-ostree, pre-configured bookmarks |
| Kitty | rpm-ostree |
| containerd + nerdctl | rpm-ostree (required by envclone) |
| Ollama | Podman Quadlet (rootless) |

---

## Target Hardware

- RAM: 16GB (Qwen 3 8B uses ~5GB, leaving ~11GB for OS + apps)
- GPU: Integrated graphics (CPU inference only — no CUDA/ROCm required)
- Storage: 40GB+ recommended

---

## Model

Default: **Qwen 3 8B Q4_K_M**

Best-in-class tool calling for its size. Runs on CPU at reasonable speed (~10–20 tok/s on a modern CPU).

To switch models after install:
```bash
# Pull a different model
ollama pull llama3.2:3b

# Update the Modelfile to use it, then recreate
ollama create chi -f /usr/lib/chi-agent/Modelfile
```
