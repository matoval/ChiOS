#!/usr/bin/env python3
"""
Transcribe audio using faster-whisper.
Usage: python3 transcribe.py <input.wav> <output.txt>
"""

import sys
from pathlib import Path


def transcribe(wav_path: str, output_path: str) -> None:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper not installed. Run: pip install faster-whisper", file=sys.stderr)
        sys.exit(1)

    # medium model, CPU inference, int8 quantization for speed
    model = WhisperModel("medium", device="cpu", compute_type="int8")

    segments, info = model.transcribe(
        wav_path,
        language="en",
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    text_parts = [segment.text.strip() for segment in segments]
    transcript = " ".join(text_parts).strip()

    Path(output_path).write_text(transcript)
    print(f"Transcribed: {transcript}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.wav> <output.txt>", file=sys.stderr)
        sys.exit(1)
    transcribe(sys.argv[1], sys.argv[2])
