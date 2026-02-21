#!/bin/bash
# chi-voice — push-to-talk transcription for chiOS
#
# Bound to Super+V (hold) in hyprland.conf.
# Flow: hold key → record → release → transcribe → send to chi-agent
#
# Dependencies: arecord (alsa-utils), faster-whisper (Python), pydbus

set -euo pipefail

WAV_FILE="/tmp/chi-voice-$(date +%s).wav"
TRANSCRIPT_FILE="${WAV_FILE%.wav}.txt"
MAX_SECONDS=30
SAMPLE_RATE=16000

# Signal file: Hyprland keybind script should touch this to stop recording
STOP_SIGNAL="/tmp/chi-voice-stop"

cleanup() {
    rm -f "$WAV_FILE" "$TRANSCRIPT_FILE" "$STOP_SIGNAL"
}
trap cleanup EXIT

# Notify user recording is starting
notify-send -t 2000 -i audio-input-microphone "chi" "Listening… (release Super+V to stop)" 2>/dev/null || true

# Remove stale stop signal
rm -f "$STOP_SIGNAL"

# Start recording in background, stop on signal file or max duration
arecord \
    --format=S16_LE \
    --rate="$SAMPLE_RATE" \
    --channels=1 \
    --file-type=wav \
    --duration="$MAX_SECONDS" \
    "$WAV_FILE" &

ARECORD_PID=$!

# Wait for stop signal (key release triggers voice-stop.sh which creates this file)
while [ ! -f "$STOP_SIGNAL" ] && kill -0 "$ARECORD_PID" 2>/dev/null; do
    sleep 0.1
done

# Stop recording
kill "$ARECORD_PID" 2>/dev/null || true
wait "$ARECORD_PID" 2>/dev/null || true

if [ ! -f "$WAV_FILE" ] || [ ! -s "$WAV_FILE" ]; then
    notify-send -t 2000 "chi" "No audio recorded" 2>/dev/null || true
    exit 1
fi

notify-send -t 1500 "chi" "Transcribing…" 2>/dev/null || true

# Transcribe with faster-whisper
python3 /usr/lib/chi-voice/transcribe.py "$WAV_FILE" "$TRANSCRIPT_FILE"

if [ ! -f "$TRANSCRIPT_FILE" ] || [ ! -s "$TRANSCRIPT_FILE" ]; then
    notify-send -t 2000 "chi" "Could not transcribe audio" 2>/dev/null || true
    exit 1
fi

TRANSCRIPT=$(cat "$TRANSCRIPT_FILE")

if [ -z "$TRANSCRIPT" ]; then
    notify-send -t 2000 "chi" "No speech detected" 2>/dev/null || true
    exit 0
fi

notify-send -t 2000 "chi" "\"$TRANSCRIPT\"" 2>/dev/null || true

# Send transcript to chi-agent via D-Bus
# Transcript is passed as argv[1] to avoid shell injection via heredoc interpolation
python3 - "$TRANSCRIPT" <<'EOF'
import sys
try:
    from pydbus import SessionBus
    bus = SessionBus()
    agent = bus.get("io.chios.Agent", "/io/chios/Agent")
    response = agent.Ask(sys.argv[1])
    print(response)
    import subprocess
    subprocess.run(["notify-send", "-t", "8000", "chi", response], check=False)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
EOF
