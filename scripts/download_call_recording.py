"""Downloads the full call recording for a given CallSid - use this after a
demo call ends to save a permanent, playable artifact for later (interviews,
portfolio, etc.), independent of whether this project/server/Twilio account
still exists by then.

Usage:
    venv/Scripts/python.exe scripts/download_call_recording.py CAxxxxxxxx... [output.mp3]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

import httpx  # noqa: E402
from twilio.rest import Client  # noqa: E402

from app.config import settings  # noqa: E402


def download_recording(call_sid: str, output_path: str) -> None:
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    recordings = client.calls(call_sid).recordings.list()

    if not recordings:
        print(f"No recording found for call {call_sid}. Has the call finished yet?")
        sys.exit(1)

    # A call also has short per-turn caller-only recordings (source
    # "RecordVerb", used internally for STT) alongside the ONE full dual-
    # channel call recording we actually want (source
    # "StartCallRecordingAPI" - see voice_incoming's recordings.create call).
    # Picking recordings[0] blindly can grab a 6-second snippet instead of
    # the real thing.
    full_call_recordings = [r for r in recordings if r.source == "StartCallRecordingAPI"]
    if not full_call_recordings:
        print("No full-call recording found (only per-turn snippets) - falling back to longest one.")
        recording = max(recordings, key=lambda r: int(r.duration or 0))
    else:
        recording = full_call_recordings[0]

    print(f"Using recording {recording.sid} ({recording.duration}s, source={recording.source})")
    url = f"https://api.twilio.com{recording.uri.replace('.json', '.mp3')}"
    audio = httpx.get(url, auth=(settings.twilio_account_sid, settings.twilio_auth_token)).content

    Path(output_path).write_bytes(audio)
    print(f"Saved {len(audio)} bytes -> {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: download_call_recording.py <call_sid> [output.mp3]")
        sys.exit(1)

    call_sid = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else f"{call_sid}.mp3"
    download_recording(call_sid, output_path)
