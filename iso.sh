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
# Write bootc-image-builder config TOML
# ---------------------------------------------------------------------------

cat > "${CONFIG_FILE}" << EOF
[[customizations.user]]
name = "${CHI_USER}"
password = "${CHI_PASS}"
groups = ["wheel"]
EOF

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
