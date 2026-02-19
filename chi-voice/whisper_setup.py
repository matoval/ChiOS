#!/usr/bin/env python3
"""
Pre-download the Whisper medium model during first-boot.
This avoids download latency on first voice command.
"""

import sys


def download_model() -> None:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("Installing faster-whisper...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "faster-whisper"], check=True)
        from faster_whisper import WhisperModel

    print("Downloading Whisper medium model (CPU int8)...")
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    print("Whisper medium model ready.")


if __name__ == "__main__":
    download_model()
