#!/bin/bash
# chiOS Installer ISO build script
#
# Runs inside a privileged Fedora 42 container (e.g. quay.io/fedora/fedora:42).
# Installs build tools, bakes the Calamares config into the live tree, and
# produces a bootable installer ISO using livemedia-creator (lorax).
#
# Environment variables:
#   CHIOS_IMAGE  — fully-qualified OCI image tag to embed in chi-install
#                  (default: ghcr.io/matoval/chios:latest)
#   ISO_NAME     — output filename (default: chiOS-installer.iso)
#   OUTPUT_DIR   — directory to write the ISO into (default: /output)

set -euxo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHIOS_IMAGE="${CHIOS_IMAGE:-ghcr.io/matoval/chios:latest}"
ISO_NAME="${ISO_NAME:-chiOS-installer.iso}"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"

echo "==> chiOS installer build starting"
echo "    Image:  ${CHIOS_IMAGE}"
echo "    ISO:    ${ISO_NAME}"
echo "    Output: ${OUTPUT_DIR}"

# ---------------------------------------------------------------------------
# 1. Install build dependencies
# ---------------------------------------------------------------------------

dnf install -y \
  lorax \
  anaconda \
  calamares \
  genisoimage \
  squashfs-tools \
  syslinux \
  grub2-efi-x64 \
  shim-x64
# Note: anaconda is required by livemedia-creator --no-virt to install packages
# into the live environment chroot. python3-calamares and calamares-libs do not
# exist as separate packages in Fedora 42; support is bundled inside calamares.

echo "==> Build tools installed"

# ---------------------------------------------------------------------------
# 2. Stage Calamares configuration into /etc/calamares
# ---------------------------------------------------------------------------

mkdir -p /etc/calamares/modules/chi-install
mkdir -p /etc/calamares/branding/chios

# Copy settings + branding
cp "${SCRIPT_DIR}/calamares/settings.conf" /etc/calamares/settings.conf
cp -r "${SCRIPT_DIR}/calamares/branding/chios/." /etc/calamares/branding/chios/

# Copy module configs (*.conf) for standard modules
cp "${SCRIPT_DIR}/calamares/modules/partition.conf" /etc/calamares/modules/partition.conf
cp "${SCRIPT_DIR}/calamares/modules/users.conf"     /etc/calamares/modules/users.conf
cp "${SCRIPT_DIR}/calamares/modules/finished.conf"  /etc/calamares/modules/finished.conf

# Copy chi-install custom module
cp "${SCRIPT_DIR}/calamares/modules/chi-install/module.desc" \
   /etc/calamares/modules/chi-install/module.desc
cp "${SCRIPT_DIR}/calamares/modules/chi-install/main.py" \
   /etc/calamares/modules/chi-install/main.py

# Inject the target OCI image URL
sed -i "s|CHIOS_IMAGE_PLACEHOLDER|${CHIOS_IMAGE}|g" \
  /etc/calamares/modules/chi-install/main.py

echo "==> Calamares config staged"

# ---------------------------------------------------------------------------
# 3. Build the live ISO with livemedia-creator
# ---------------------------------------------------------------------------

# Note: livemedia-creator requires --resultdir to NOT exist beforehand
# It creates the directory itself; pre-creating it causes an immediate error.
mkdir -p /tmp/livemedia-tmp

livemedia-creator \
  --ks "${SCRIPT_DIR}/chiOS-installer.ks" \
  --no-virt \
  --project "chiOS" \
  --make-iso \
  --iso-name "${ISO_NAME}" \
  --resultdir "${OUTPUT_DIR}" \
  --tmp /tmp/livemedia-tmp

echo "==> ISO built: ${OUTPUT_DIR}/${ISO_NAME}"

# ---------------------------------------------------------------------------
# 4. Verify and report
# ---------------------------------------------------------------------------

ISO_PATH="${OUTPUT_DIR}/${ISO_NAME}"
if [ -f "${ISO_PATH}" ]; then
  SIZE=$(du -sh "${ISO_PATH}" | cut -f1)
  echo "==> Success: ${ISO_NAME} (${SIZE})"
else
  echo "ERROR: Expected ISO not found at ${ISO_PATH}"
  ls -la "${OUTPUT_DIR}/" || true
  exit 1
fi
