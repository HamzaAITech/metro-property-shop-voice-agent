"""Places outbound calls that connect to the same voice agent used for
inbound calls (Twilio fetches TwiML from /twilio/voice once each call is
answered, exactly like an incoming call).

IMPORTANT: only use this on numbers that already have some relationship with
the shop (past inquirers, existing leads) unless you have separately handled
India's TRAI TCCCPR telemarketing compliance (telemarketer registration,
DND/NDNC scrubbing, sender ID registration) for a cold/marketing list. Twilio
also prohibits unsolicited robocalls under its Acceptable Use Policy and will
suspend accounts found violating it.

Usage:
    venv/Scripts/python.exe scripts/make_outbound_calls.py +919876543210 +919876543211
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from app.config import settings  # noqa: E402
from twilio.rest import Client  # noqa: E402

SECONDS_BETWEEN_CALLS = 3  # basic rate-limiting courtesy, not a compliance measure


def make_calls(phone_numbers: list[str]) -> None:
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    voice_url = f"{settings.public_base_url}/twilio/voice"

    for number in phone_numbers:
        call = client.calls.create(to=number, from_=settings.twilio_phone_number, url=voice_url)
        print(f"Calling {number} -> call sid {call.sid}")
        time.sleep(SECONDS_BETWEEN_CALLS)


if __name__ == "__main__":
    numbers = sys.argv[1:]
    if not numbers:
        print("Usage: make_outbound_calls.py <phone_number> [<phone_number> ...]")
        sys.exit(1)
    make_calls(numbers)
