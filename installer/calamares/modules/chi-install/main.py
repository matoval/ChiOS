#!/usr/bin/env python3
"""
chi-install — Calamares Python job module for chiOS.

Install flow:
  1. Pull chiOS OCI image (if not already cached)
  2. Run `bootc install to-disk <disk>` — handles partitioning + bootloader
  3. Mount the installed root partition
  4. Create the user account (useradd + chpasswd)
  5. Set the hostname
  6. Unmount

bootc install to-disk requires that the live environment has already
pulled the OCI image (done in the kickstart %post via `podman pull`).
"""

import json
import os
import subprocess
import tempfile
import time

import libcalamares

# Injected by build-installer.sh
CHIOS_IMAGE = "CHIOS_IMAGE_PLACEHOLDER"

# ─── helpers ────────────────────────────────────────────────────────────────

def run(cmd, **kwargs):
    """Run a command, return CompletedProcess. Raises on non-zero exit."""
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def find_root_partition(disk: str) -> str | None:
    """
    After bootc install, find the root partition on *disk*.

    bootc creates:
      p1 = EFI System Partition  (vfat, ~300 MB)
      p2 = /boot                 (ext4/xfs, ~1 GB)   [sometimes]
      pN = root                  (xfs, rest of disk)

    We pick the largest non-EFI partition.
    """
    result = run(["lsblk", "-J", "-b", "-o", "NAME,TYPE,FSTYPE,SIZE", disk])
    if result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    partitions = []
    for dev in data.get("blockdevices", []):
        for child in dev.get("children", []):
            if child.get("type") != "part":
                continue
            fstype = child.get("fstype", "")
            if fstype in ("xfs", "ext4", "btrfs"):
                try:
                    size = int(child.get("size", 0))
                except (TypeError, ValueError):
                    size = 0
                partitions.append((size, f"/dev/{child['name']}"))

    if not partitions:
        return None

    partitions.sort(reverse=True)
    return partitions[0][1]


# ─── Calamares interface ─────────────────────────────────────────────────────

def pretty_name() -> str:
    return "Installing chiOS"


def run() -> None | tuple[str, str]:
    """
    Returns None on success, or (title, detail) on failure.
    """
    gs = libcalamares.globalstorage

    # --- Collect install parameters from globalStorage ---
    disk = gs.value("bootDevice")       # set by the partition module
    username = (gs.value("username") or "").strip()
    password = gs.value("password") or ""
    hostname = (gs.value("hostname") or "chios").strip()

    if not disk:
        return (
            "No target disk selected",
            "The partition module did not record a target disk. "
            "Please go back and select a disk.",
        )

    if not username:
        username = "user"

    libcalamares.utils.debug(f"chi-install: disk={disk} user={username} host={hostname}")

    # ── Step 1: Pull OCI image if not cached ────────────────────────────────
    libcalamares.job.setprogress(0.02)
    libcalamares.utils.debug(f"chi-install: checking image {CHIOS_IMAGE}")

    pull = subprocess.run(
        ["podman", "pull", CHIOS_IMAGE],
        capture_output=True, text=True
    )
    if pull.returncode != 0:
        # Image might already be loaded from the live ISO bundle — continue
        libcalamares.utils.warning(f"podman pull warning: {pull.stderr[:500]}")

    # ── Step 2: bootc install to-disk ────────────────────────────────────────
    libcalamares.job.setprogress(0.05)
    libcalamares.utils.debug(f"chi-install: running bootc install to-disk {disk}")

    bootc = subprocess.run(
        [
            "bootc", "install", "to-disk",
            "--target-no-signature-check",
            "--skip-fetch-check",
            disk,
        ],
        capture_output=True, text=True
    )
    if bootc.returncode != 0:
        return (
            "Installation failed",
            f"bootc install to-disk returned exit code {bootc.returncode}:\n"
            + bootc.stderr[-2000:],
        )

    libcalamares.job.setprogress(0.82)
    libcalamares.utils.debug("chi-install: bootc install complete")

    # ── Step 3: Find and mount the installed root partition ──────────────────
    # Give the kernel a moment to re-read the partition table
    time.sleep(2)
    subprocess.run(["udevadm", "settle"], capture_output=True)

    root_part = find_root_partition(disk)
    if not root_part:
        return (
            "Could not find root partition",
            f"Unable to locate the root partition on {disk} after installation.",
        )

    libcalamares.utils.debug(f"chi-install: root partition = {root_part}")

    mount_point = tempfile.mkdtemp(prefix="chios-root-")
    try:
        # Mount root
        mnt = subprocess.run(
            ["mount", root_part, mount_point],
            capture_output=True, text=True
        )
        if mnt.returncode != 0:
            return (
                "Mount failed",
                f"Could not mount {root_part} at {mount_point}:\n{mnt.stderr}",
            )

        # Mount /proc, /sys, /dev so chroot works
        for bind in ("/proc", "/sys", "/dev"):
            subprocess.run(
                ["mount", "--bind", bind, mount_point + bind],
                capture_output=True
            )

        libcalamares.job.setprogress(0.88)

        # ── Step 4: Create user ───────────────────────────────────────────────
        libcalamares.utils.debug(f"chi-install: creating user {username}")

        useradd = subprocess.run(
            [
                "chroot", mount_point,
                "useradd", "-m", "-G", "wheel,users,video,audio",
                "-s", "/bin/bash", username,
            ],
            capture_output=True, text=True
        )
        if useradd.returncode not in (0, 9):  # 9 = user already exists
            libcalamares.utils.warning(f"useradd: {useradd.stderr}")

        # Set password via chpasswd
        chpasswd = subprocess.run(
            ["chroot", mount_point, "chpasswd"],
            input=f"{username}:{password}\n",
            capture_output=True, text=True
        )
        if chpasswd.returncode != 0:
            libcalamares.utils.warning(f"chpasswd: {chpasswd.stderr}")

        libcalamares.job.setprogress(0.92)

        # ── Step 5: Set hostname ──────────────────────────────────────────────
        hostname_file = os.path.join(mount_point, "etc", "hostname")
        try:
            os.makedirs(os.path.dirname(hostname_file), exist_ok=True)
            with open(hostname_file, "w") as f:
                f.write(hostname + "\n")
        except OSError as e:
            libcalamares.utils.warning(f"hostname write: {e}")

        libcalamares.job.setprogress(0.95)

    finally:
        # ── Step 6: Unmount ───────────────────────────────────────────────────
        for bind in ("/dev", "/sys", "/proc"):
            subprocess.run(
                ["umount", "-l", mount_point + bind],
                capture_output=True
            )
        subprocess.run(["umount", "-l", mount_point], capture_output=True)
        try:
            os.rmdir(mount_point)
        except OSError:
            pass

    libcalamares.job.setprogress(1.0)
    libcalamares.utils.debug("chi-install: complete")
    return None
