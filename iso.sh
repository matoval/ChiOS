#!/bin/bash
set -euo pipefail

# iso.sh — Generate installable chiOS ISO via bootc-image-builder
# Usage: ./iso.sh [IMAGE]
# Default image: ghcr.io/matoval/chios:latest

IMAGE="${1:-ghcr.io/matoval/chios:latest}"
OUTPUT_DIR="$(pwd)/output"
CONFIG_FILE="$(mktemp /tmp/chios-config-XXXXXX.toml)"

echo "==> Building chiOS ISO from image: ${IMAGE}"
echo "==> Output directory: ${OUTPUT_DIR}"
echo ""

# ---------------------------------------------------------------------------
# Target disk selection (required — installer is fully automatic)
# ---------------------------------------------------------------------------

echo "WARNING: The chiOS installer is fully automatic and will ERASE the target"
echo "         disk without any confirmation. ALL DATA will be permanently lost."
echo ""
echo "Run 'lsblk' on the target machine to identify the correct disk first."
echo ""

CHI_DISK=""
while [[ -z "${CHI_DISK}" ]]; do
  read -rp "Target install disk (e.g. /dev/sda, /dev/nvme0n1): " CHI_DISK
  if [[ -z "${CHI_DISK}" ]]; then
    echo "A target disk is required."
  fi
done
echo ""

# ---------------------------------------------------------------------------
# Prompt for user credentials
# ---------------------------------------------------------------------------

read -rp "Username: " CHI_USER
while [[ -z "${CHI_USER}" ]]; do
  echo "Username cannot be empty."
  read -rp "Username: " CHI_USER
done

while true; do
  read -rsp "Password: " CHI_PASS
  echo ""
  read -rsp "Confirm password: " CHI_PASS2
  echo ""
  if [[ "${CHI_PASS}" == "${CHI_PASS2}" ]]; then
    break
  fi
  echo "Passwords do not match, try again."
done

while [[ -z "${CHI_PASS}" ]]; do
  echo "Password cannot be empty."
  read -rsp "Password: " CHI_PASS
  echo ""
done

# ---------------------------------------------------------------------------
# WiFi configuration (optional)
# ---------------------------------------------------------------------------

echo "WiFi setup (optional — skip if using ethernet or configuring later):"
read -rp "WiFi SSID [leave blank to skip]: " CHI_WIFI_SSID
CHI_WIFI_PASS=""
if [[ -n "${CHI_WIFI_SSID}" ]]; then
  read -rsp "WiFi password: " CHI_WIFI_PASS
  echo ""
fi
echo ""

# ---------------------------------------------------------------------------
# Write bootc-image-builder config TOML
# ---------------------------------------------------------------------------

# Hash password for kickstart (SHA-512, accepted by Anaconda)
CHI_PASS_HASH=$(openssl passwd -6 "${CHI_PASS}")
DISK_BASENAME=$(basename "${CHI_DISK}")

# Build kickstart header (all variables expanded now)
KICKSTART_HEADER="text --non-interactive
zerombr
clearpart --all --initlabel --drives=${DISK_BASENAME}
ignoredisk --only-use=${DISK_BASENAME}
autopart --noswap --type=lvm
user --name=${CHI_USER} --password=${CHI_PASS_HASH} --iscrypted --groups=wheel
reboot"

# Optionally append WiFi %post section
KICKSTART_POST=""
if [[ -n "${CHI_WIFI_SSID}" ]]; then
  KICKSTART_POST="%post
mkdir -p /etc/NetworkManager/system-connections
cat > /etc/NetworkManager/system-connections/chiOS-wifi.nmconnection << 'NMEOF'
[connection]
id=chiOS-wifi
type=wifi
autoconnect=true

[wifi]
mode=infrastructure
ssid=${CHI_WIFI_SSID}

[wifi-security]
auth-alg=open
key-mgmt=wpa-psk
psk=${CHI_WIFI_PASS}

[ipv4]
method=auto

[ipv6]
method=auto
NMEOF
chmod 600 /etc/NetworkManager/system-connections/chiOS-wifi.nmconnection
%end"
fi

# Write TOML — [[customizations.user]] cannot be combined with kickstart block;
# user creation is handled inside the kickstart contents instead.
cat > "${CONFIG_FILE}" << EOF
[customizations.installer.kickstart]
contents = """
${KICKSTART_HEADER}
${KICKSTART_POST}
"""
EOF
echo "==> Target disk: ${CHI_DISK}"
[[ -n "${CHI_WIFI_SSID}" ]] && echo "==> WiFi: ${CHI_WIFI_SSID} (pre-configured)"

echo "==> User '${CHI_USER}' will be created in the ISO installer"
echo ""

# ---------------------------------------------------------------------------
# Transfer local image to root storage if needed
# ---------------------------------------------------------------------------

mkdir -p "${OUTPUT_DIR}"

if [[ "${IMAGE}" == localhost/* ]]; then
  echo "==> Transferring local image to root's container storage..."
  podman save "${IMAGE}" | sudo podman load
fi

# ---------------------------------------------------------------------------
# Run bootc-image-builder
# ---------------------------------------------------------------------------

sudo podman run --rm --privileged \
  --pull=newer \
  -v /var/lib/containers/storage:/var/lib/containers/storage \
  -v "${OUTPUT_DIR}:/output" \
  -v "${CONFIG_FILE}:/config.toml:ro" \
  quay.io/centos-bootc/bootc-image-builder:latest \
  --type iso \
  --rootfs xfs \
  --config /config.toml \
  --output /output \
  "${IMAGE}"

rm -f "${CONFIG_FILE}"

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

ISO_PATH="${OUTPUT_DIR}/bootiso/install.iso"

if [ -f "${ISO_PATH}" ]; then
  echo ""
  echo "==> ISO built successfully!"
  echo "    Path: ${ISO_PATH}"
  echo "    Size: $(du -sh "${ISO_PATH}" | cut -f1)"
  echo "    User: ${CHI_USER}"
  echo ""
  echo "==> Test with QEMU:"
  echo "    qemu-img create -f qcow2 test.qcow2 40G"
  echo "    qemu-system-x86_64 -enable-kvm -m 8G -cdrom ${ISO_PATH} -drive file=test.qcow2,if=virtio -cpu host -nographic"
else
  echo "==> ERROR: ISO not found at expected path: ${ISO_PATH}"
  find "${OUTPUT_DIR}" -type f 2>/dev/null || echo "    (empty)"
  rm -f "${CONFIG_FILE}"
  exit 1
fi
