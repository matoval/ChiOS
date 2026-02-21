# chiOS v2 — Testing Checklist

Mark items as you verify them. Test on a fresh install from the Calamares ISO.

---

## Installation (Calamares)

- [ ] ISO boots to live environment on target hardware (UEFI + Legacy BIOS)
- [ ] Calamares launches automatically after X starts
- [ ] Calamares branding shows chiOS purple/dark theme
- [ ] **Welcome** page loads with correct product name "chiOS"
- [ ] **Locale** page sets language and timezone correctly
- [ ] **Keyboard** page applies selected layout
- [ ] **Partition** page shows available disks; "Erase disk" option works; target disk recorded
- [ ] **Users** page accepts username (≥6 char password enforced)
- [ ] **Summary** page shows correct disk, user, locale before confirming
- [ ] Installation slideshow shows chiOS branding while `chi-install` runs
- [ ] `bootc install to-disk` completes without error
- [ ] User account is created on the installed system
- [ ] Hostname is set correctly
- [ ] Installer offers reboot at the end
- [ ] Machine boots successfully from the installed disk (not the USB)

---

## Login Screen (chi-greeter)

- [ ] chi-greeter appears fullscreen with dark gradient background
- [ ] chiOS logo (✦), brand name, and tagline are visible
- [ ] Clock updates every second; date is correct
- [ ] Username and password fields accept input
- [ ] Tab key moves from username → password field
- [ ] Enter key in password field submits
- [ ] Incorrect password shows "Incorrect username or password." error, clears password field
- [ ] Correct credentials log in and start labwc
- [ ] **Shutdown** button powers off the machine
- [ ] **Restart** button reboots the machine

---

## Desktop Shell (labwc + chi-shell)

- [ ] labwc starts after login; no errors in journal (`journalctl --user -b`)
- [ ] chi-shell panel appears at the bottom of the screen (full width, ~56px)
- [ ] Panel is always on top; windows do not appear under it
- [ ] **Dock (left)**: Files (Nautilus), Browser (Firefox), Terminal (Kitty), Code (VSCodium) buttons visible
- [ ] Clicking a dock button launches the app
- [ ] **"✦ Ask chi…" button (center)**: click opens chi-overlay
- [ ] **Clock (right)**: shows current time, updates every second
- [ ] **Status dot (right)**: green when chi-agent is ready; yellow while processing; red if agent is down
- [ ] Right-clicking the desktop shows context menu (Ask chi / Terminal / Files / Browser / Log Out)
- [ ] **Super+Q** closes the focused window
- [ ] **Super+F** maximizes/restores a window
- [ ] **Super+Space** opens chi-overlay
- [ ] **Super+T** opens a terminal (Kitty)
- [ ] Dragging a window titlebar moves it; dragging a corner resizes it
- [ ] **Super+drag** moves any window (without grabbing titlebar)

---

## AI Overlay — chi-overlay v2

### Window behavior

- [ ] chi-overlay opens centered (~720×540px), floating on top
- [ ] Second `chi-overlay-show` invocation re-focuses the existing window (not a second instance)
- [ ] Escape key hides the window; window is not destroyed (process stays running)
- [ ] Closing the window (×) hides it; stays in background

### Chat tab

- [ ] Three tabs visible: Chat / History / Data
- [ ] Chat tab is active by default
- [ ] Previous messages load when window re-opens (within same session)
- [ ] "Thinking…" indicator appears while chi-agent is processing
- [ ] Ask a simple question (e.g., "What time is it?") → response appears
- [ ] Ask chi to launch an app (e.g., "open firefox") → Firefox launches
- [ ] Ask chi to run a shell command (e.g., "show disk usage") → result shown
- [ ] Voice button (🎤) triggers chi-voice recording; result populates the entry field
- [ ] Pressing Enter or clicking Send submits the message

### History tab

- [ ] Switching to History tab loads past conversations
- [ ] Each conversation shows date, message count, and a preview
- [ ] Clicking a conversation loads it into the Chat tab
- [ ] Per-row 🗑 button deletes that individual conversation (with confirmation label)
- [ ] "🗑 Clear all" toolbar button deletes all conversations
- [ ] After clearing, History tab shows placeholder text

### Data tab

- [ ] Data tab shows JSON output from chi-agent tool calls (e.g., network info, app lists)
- [ ] "Export JSON" button writes a file to ~/Downloads and opens it
- [ ] "🗑 Clear data" button clears the data store
- [ ] After clearing, Data tab shows empty/placeholder state

---

## AI Tools via chi-agent

- [ ] `launch_app`: "open the terminal" → Kitty opens
- [ ] `install_app` (flatpak): "install vlc" → VLC installed via Flatpak
- [ ] `remove_app`: "remove vlc" → VLC uninstalled
- [ ] `install_system` (rpm-ostree): "install htop system-wide" → staged, reboot prompt
- [ ] `run_shell`: "show disk usage" → `df -h` output returned
- [ ] `get_network_status`: "what's my network status?" → connection info shown
- [ ] `set_network`: "disconnect from wifi" → connection toggled
- [ ] `manage_service`: "is NetworkManager running?" → service status returned
- [ ] **Deny pattern**: "delete all my files" or `rm -rf /` → blocked, not executed

---

## Conversation History (SQLite)

- [ ] DB exists at `~/.local/share/chiOS/history.db` after first conversation
- [ ] Conversations persist across chi-overlay restarts (close + reopen)
- [ ] Conversations persist across reboots
- [ ] New conversation session starts after 2+ hours of inactivity
- [ ] Tool call data appears in the Data tab

---

## Voice Input (chi-voice)

- [ ] Hold Super+V, speak "open the terminal", release → Kitty opens
- [ ] Transcription appears in the chi-overlay chat entry before sending
- [ ] Whisper model loads on first use (may take a few seconds)
- [ ] `chi-voice` service is available (`which chi-voice`)

---

## First Boot Service

- [ ] `chi-firstboot.service` runs automatically after first login
- [ ] Flathub remote is added (`flatpak remotes` shows `flathub`)
- [ ] Ollama Quadlet container starts (`systemctl --user status ollama`)
- [ ] `qwen3:8b` model is pulled (`ollama list` shows the model)
- [ ] `chi` model is created from Modelfile (`ollama list` shows `chi`)
- [ ] Whisper medium model is downloaded
- [ ] Claude Code MCP config written (`~/.config/claude/mcp_servers.json`)
- [ ] Firstboot completion marker created (`/var/lib/chi-firstboot.done`)
- [ ] Firstboot service does NOT re-run on second login

---

## Pre-installed Apps

- [ ] Firefox launches; has Claude.ai and ChatGPT toolbar bookmarks
- [ ] VSCodium launches (`codium` or via dock)
- [ ] Kitty terminal opens and works
- [ ] Nautilus file manager opens
- [ ] Claude Code is available (`claude --version`)
- [ ] `nerdctl` is available (`nerdctl --version`)
- [ ] `envclone` is available (`envclone --help`)
- [ ] `bootc` is available (`bootc status`)

---

## Claude Code MCP Integration

- [ ] Open Kitty; run `claude`
- [ ] In Claude Code, run `/mcp` → `chi` server is listed as connected
- [ ] Use `launch_app` tool from Claude Code session → app launches
- [ ] Use `run_shell` tool from Claude Code session → command executes

---

## Package Management

- [ ] Install a Flatpak app via chi → takes effect immediately, no reboot
- [ ] Stage an rpm-ostree package via chi → confirms reboot required
- [ ] After reboot, the staged package is present (`rpm -q <package>`)
- [ ] `rpm-ostree status` shows current deployment info

---

## Automatic Updates

- [ ] `bootc-update.timer` is active (`systemctl status bootc-update.timer`)
- [ ] `bootc upgrade` runs manually without error
- [ ] `bootc status` shows image source as `ghcr.io/matoval/chios`

---

## envclone (Dev Environments)

- [ ] "new python project env" → chi creates a containerized dev environment
- [ ] "start the dev environment" → environment comes up
- [ ] "open VSCodium in the dev environment" → VSCodium opens inside container
- [ ] "stop the dev environment" → container stops

---

## Security

- [ ] chi-agent blocks dangerous shell commands (e.g., `rm -rf /`, `dd if=/dev/zero`)
- [ ] AI cannot write to `/etc` or `/usr` directly (immutable base)
- [ ] History deletion removes data from SQLite (no residual records)
- [ ] Password is never logged or stored in chi-agent history

---

## Known Issues / Notes

<!-- Add any observed issues during testing here -->
