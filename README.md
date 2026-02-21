# chiOS

An AI-native OS for any knowledge level. Fedora Atomic base, custom desktop shell, local LLM as the primary interface — click "✦ Ask chi…" and tell it what to do.

```text
Click "✦ Ask chi…"  → "open firefox"           → Firefox launches
Click "✦ Ask chi…"  → "install htop"           → flatpak installs htop
Click "✦ Ask chi…"  → "new python project env" → envclone init python myproject
Hold Super+V        → say "open the terminal"  → Kitty opens
```

---

## Architecture

```text
Build:   Containerfile → OCI image (GHCR) → Calamares live ISO (GitHub Releases)

Runtime:
  Base:     Fedora Atomic (ghcr.io/ublue-os/base-main) — immutable, bootc/rpm-ostree
  Login:    chi-greeter (GTK4) via greetd
  Desktop:  labwc (Wayland compositor) + chi-shell (GTK4 panel)
  AI:       Ollama (Podman Quadlet) + Qwen 3 8B Q4_K_M (CPU, ~5GB RAM)
            chi-agent: Python service, D-Bus + MCP
            chi-overlay: GTK4 tabbed window (Chat / History / Data)
            chi-voice: Whisper push-to-talk (Super+V)
```

**Why immutable?** The base OS is read-only. Rollback is one command. The AI can't accidentally brick the system. All dev work goes in containers via envclone.

**Package tiers:**

| Tier | Tool | Use for | Reboot? |
| --- | --- | --- | --- |
| 1 | flatpak | GUI desktop apps | No |
| 2 | rpm-ostree | System packages, drivers | Yes |
| 3 | envclone | Dev environments | No |

---

## Project Structure

```text
chiOS/
├── Containerfile               # OS image definition
├── build.sh                    # Package installs + system config (runs inside OCI build)
│
├── .github/workflows/
│   └── build.yml               # CI: OCI image → GHCR; Calamares ISO on release tags
│
├── installer/                  # Calamares live installer ISO
│   ├── build-installer.sh      # Build script (runs in Fedora container)
│   ├── chiOS-installer.ks      # Kickstart for the live environment
│   └── calamares/
│       ├── settings.conf       # Wizard module sequence
│       ├── branding/chios/     # chiOS dark theme for Calamares
│       └── modules/
│           ├── partition.conf  # Disk selection (erase mode)
│           ├── users.conf      # User account creation
│           └── chi-install/    # Custom Python module: bootc install + user setup
│
├── chi-agent/                  # AI orchestration service
│   ├── agent.py                # Ollama API loop + tool dispatch
│   ├── mcp_server.py           # MCP server (Claude Code integration)
│   ├── dbus_service.py         # io.chios.Agent D-Bus service
│   ├── history.py              # SQLite conversation + data storage
│   ├── tools/
│   │   ├── apps.py             # Launch apps
│   │   ├── packages.py         # flatpak (immediate) + rpm-ostree (staged)
│   │   ├── shell.py            # subprocess runner with deny-pattern safety
│   │   ├── system.py           # NetworkManager + systemd via D-Bus
│   │   └── envclone.py         # envclone CLI wrappers
│   ├── Modelfile               # Ollama system prompt (chi personality)
│   ├── chi-agent.service       # systemd user unit
│   └── requirements.txt
│
├── chi-overlay/                # GTK4 AI companion window
│   ├── overlay.py              # Tabbed window: Chat / History / Data
│   └── overlay.css
│
├── chi-shell/                  # Custom desktop panel
│   ├── chi-shell.py            # GTK4 layer-shell panel (dock + chi button + clock)
│   ├── chi-shell.css
│   ├── apps.json               # Default pinned dock apps
│   ├── kitty/kitty.conf        # Terminal config
│   └── labwc/                  # Wayland compositor config
│       ├── rc.xml              # Window management + keybindings
│       ├── autostart           # Session startup
│       └── menu.xml            # Right-click desktop menu
│
├── chi-greeter/                # Custom GTK4 login screen
│   ├── chi-greeter.py          # greetd IPC client + fullscreen login UI
│   └── chi-greeter.css
│
├── chi-voice/                  # Whisper push-to-talk
│   ├── voice.sh                # Super+V: arecord → whisper → chi-agent
│   ├── voice-stop.sh           # Key release handler
│   ├── transcribe.py           # faster-whisper medium, CPU int8
│   └── whisper_setup.py        # Pre-download model at first-boot
│
├── quadlets/
│   └── ollama.container        # Podman Quadlet: Ollama as rootless user service
│
├── configs/
│   └── firefox/user.js         # Pre-configured bookmarks: Claude.ai, ChatGPT
│
└── post-install/
    └── firstboot.sh            # First-boot: pull model, set up containerd, configure MCP
```

---

## Install

### Download ISO

Download the latest `chiOS-vX.Y.Z-installer.iso` from [GitHub Releases](https://github.com/matoval/chios/releases).

Verify the checksum:

```bash
sha256sum -c SHA256SUMS
```

### Flash to USB

```bash
sudo dd if=chiOS-vX.Y.Z-installer.iso of=/dev/sdX bs=4M status=progress
```

Or use [Balena Etcher](https://etcher.balena.io/).

### Run the installer

1. Boot from the USB drive
2. Follow the Calamares graphical installer: welcome → locale → keyboard → disk → user → install
3. Reboot into chiOS

---

## Build Locally

### Build requirements

- Podman or Docker
- `buildah`

### Build OCI image

```bash
buildah build -t localhost/chios:dev -f Containerfile .
```

### Build installer ISO

```bash
mkdir -p output
sudo podman run --rm --privileged \
  -v "$(pwd)/installer:/installer:ro" \
  -v "$(pwd)/output:/output" \
  -e CHIOS_IMAGE="localhost/chios:dev" \
  -e ISO_NAME="chiOS-dev-installer.iso" \
  quay.io/fedora/fedora:42 \
  bash /installer/build-installer.sh
```

Output: `./output/chiOS-dev-installer.iso`

### Test in QEMU

```bash
# Create virtual disk
qemu-img create -f qcow2 test.qcow2 40G

# Boot from installer ISO
qemu-system-x86_64 -enable-kvm -m 8G \
  -cdrom output/chiOS-dev-installer.iso \
  -drive file=test.qcow2,if=virtio \
  -vga virtio -cpu host

# After install, boot installed OS
qemu-system-x86_64 -enable-kvm -m 8G \
  -drive file=test.qcow2,if=virtio \
  -vga virtio -cpu host
```

---

## CI/CD

GitHub Actions (`.github/workflows/build.yml`):

**On every push to `main`:**

1. Builds OCI image with `buildah`
2. Tags with `latest` + git SHA
3. Pushes to `ghcr.io/matoval/chios`

**On release tags (`v*`):**

1. Builds the versioned OCI image
2. Builds the Calamares live installer ISO (inside a Fedora container)
3. Generates `SHA256SUMS`
4. Creates a GitHub Release with ISO + checksum attached

To ship a release:

```bash
git tag v1.0.0 && git push --tags
```

---

## Desktop

### Keybindings (labwc)

| Key | Action |
| --- | --- |
| `Super+Space` | Open/focus chi-overlay |
| `Super+V` (hold) | Push-to-talk voice input |
| `Super+T` | Kitty terminal |
| `Super+Q` | Close window |
| `Super+F` | Maximize/restore |
| `Super+drag` | Move any window |

### chi-shell panel (bottom of screen)

| Area | Contents |
| --- | --- |
| Left | Pinned app dock (Files, Browser, Terminal, Code) |
| Center | ✦ Ask chi… button |
| Right | Clock + chi-agent status dot |

Right-click the desktop for a quick-launch menu.

---

## chi-overlay (AI window)

Three tabs:

- **Chat** — Conversation with chi. Persistent history (SQLite). Voice button for push-to-talk.
- **History** — Past conversations by date. Click to reload. Per-row delete or clear all.
- **Data** — JSON output from chi-agent tool calls (network info, app installs, etc.). Export or clear.

---

## AI Tools

chi-agent exposes these tools to the local LLM and to Claude Code via MCP:

| Tool | Description |
| --- | --- |
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

After first-boot, Claude Code is pre-configured with the chi MCP server. Use chi tools directly in Claude Code sessions — same tools the overlay uses.

To add manually:

```json
{
  "mcpServers": {
    "chi": {
      "command": "python3",
      "args": ["/usr/lib/chi-agent/mcp_server.py", "--standalone"]
    }
  }
}
```

Save to `~/.config/claude/mcp_servers.json`.

---

## First Boot

On first login, `chi-firstboot.service` runs automatically and:

1. Adds Flathub remote
2. Enables Ollama Podman Quadlet
3. Pulls `qwen3:8b` model (~5GB)
4. Creates `chi` Ollama model from Modelfile
5. Pre-downloads Whisper medium model
6. Sets up containerd rootless (required by envclone)
7. Writes Claude Code MCP config
8. Self-disables (marks `~/.local/share/chi/firstboot.done`)

Progress is shown via desktop notifications.

---

## Updates and Rollback

Updates are atomic and staged — the running system is never modified mid-update.

```bash
# Check for updates (runs weekly via bootc-update.timer)
bootc upgrade

# List deployments
rpm-ostree status

# Roll back to previous deployment
rpm-ostree rollback
```

---

## Pre-installed Software

| App | Method |
| --- | --- |
| Claude Code | npm install (build.sh) |
| VSCodium | RPM from GitHub releases |
| envclone | Binary from GitHub releases |
| Firefox | rpm-ostree, pre-configured bookmarks |
| Kitty | rpm-ostree |
| Nautilus | rpm-ostree |
| containerd + nerdctl | rpm-ostree |
| Ollama | Podman Quadlet (rootless) |

---

## Target Hardware

- RAM: 16GB+ (Qwen 3 8B uses ~5GB; OS + apps need the rest)
- GPU: Integrated graphics (CPU inference — no CUDA/ROCm required)
- Storage: 40GB+ recommended

---

## Model

Default: **Qwen 3 8B Q4_K_M**

Best-in-class tool calling for its size. Runs on CPU at ~10–20 tok/s on a modern CPU.

To switch models after install:

```bash
ollama pull llama3.2:3b
# Edit /usr/lib/chi-agent/Modelfile, then:
ollama create chi -f /usr/lib/chi-agent/Modelfile
```
