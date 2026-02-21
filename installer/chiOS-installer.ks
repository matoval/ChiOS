# chiOS Live Installer Kickstart
# Builds a bootable live ISO containing Calamares + bootc client.
# The live environment boots, auto-logs in, and auto-starts the chiOS installer.

lang en_US.UTF-8
keyboard us
timezone UTC
selinux --disabled
firewall --disabled
rootpw --lock

# Packages for the live environment
%packages
# Core system
@core
@hardware-support
@fonts

# Networking
NetworkManager
NetworkManager-wifi
NetworkManager-wwan
nm-connection-editor

# Display / Xorg
xorg-x11-server-Xorg
xorg-x11-drv-libinput
xorg-x11-drv-fbdev
mesa-dri-drivers
mesa-vulkan-drivers

# Minimal window manager for installer (Openbox + Xterm for fallback)
openbox
xterm
xdg-utils

# Calamares installer
calamares
calamares-libs

# bootc (pulls the chiOS image during install)
bootc
podman
skopeo

# Fonts for chiOS UI feel
google-noto-sans-fonts
google-noto-emoji-fonts

# Utilities
gparted
parted
util-linux
wget
curl

# Live ISO tooling
dracut-live
%end

%post --nochroot
# Set up auto-login as root in the live environment via .bash_profile
# (livemedia-creator creates a liveuser; we use root for simplicity)
cat > /mnt/sysimage/root/.xinitrc << 'XINITRC'
#!/bin/bash
# Start openbox and launch Calamares in full-screen
openbox &
sleep 1

# Set background to chiOS dark color
xsetroot -solid "#0c0b14"

# Launch Calamares (Qt5/Qt6 installer)
exec calamares -D 6
XINITRC
chmod +x /mnt/sysimage/root/.xinitrc

# Auto-start X on tty1 login
cat > /mnt/sysimage/root/.bash_profile << 'PROFILE'
# Auto-start X on tty1
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec startx
fi
PROFILE
%end

%post
# Install Calamares configuration
mkdir -p /etc/calamares/modules/chi-install
mkdir -p /etc/calamares/branding/chios

# (Calamares config files are copied in by build-installer.sh before livemedia-creator runs)

# Enable getty auto-login on tty1 so installer starts without password
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << 'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I $TERM
EOF

# Set graphical target
systemctl set-default graphical.target

# Enable NetworkManager
systemctl enable NetworkManager
%end
