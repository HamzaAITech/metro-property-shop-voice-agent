import logging
import re
import shutil
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, Form
from fastapi.responses import Response
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse

from app.config import settings
from app.llm.conversation import Conversation
from app.pipeline import handle_turn
from app.tts.tts_engine import synthesize

logger = logging.getLogger("twilio_routes")

router = APIRouter(prefix="/twilio")

_twilio_client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)

AUDIO_DIR = Path(__file__).resolve().parent.parent.parent / "audio_cache"
AUDIO_DIR.mkdir(exist_ok=True)

# One Conversation per in-progress call, keyed by Twilio's CallSid.
# In-memory only - fine for a single-process demo; a real deployment would
# need this in Redis/a DB to survive restarts or multiple server workers.
call_sessions: dict[str, Conversation] = {}

# call_sid -> {"status": "processing"} | {"status": "done", ...} | {"status": "error", ...}
# Lets /handle-recording return to Twilio instantly while the slow STT->LLM->TTS
# pipeline runs in the background - see _process_turn_in_background.
call_results: dict[str, dict] = {}

GREETING_TEXT = "Namaste! Welcome to our property shop. How can I help you today?"

# Used when WE initiated the call (see scripts/make_outbound_calls.py) rather
# than the caller dialing in - proactively announces who's calling instead of
# reactively asking how to help, since the callee didn't ask us anything.
OUTBOUND_GREETING_TEXT = (
    "Namaste! This is Metro Property Shop calling from Delhi. We deal in all kinds of "
    "flats and shops across India, and this month we're offering zero brokerage fee on "
    "every rental booking. If you're looking to buy or rent, we have great options "
    "available right now. Would you like to hear more, or you're welcome to call us "
    "back anytime on this number."
)

# Played during the wait so silence doesn't read as a dead call. Bilingual
# and picked per-call based on Conversation.last_lang (set by
# pipeline.handle_turn after each turn's STT) - the filler used to be
# hardcoded to Hindi always, which sounded like a language mismatch to an
# English-speaking caller. Hindi text uses feminine verb conjugations
# ("karti hoon"/"rahi hoon") since both TTS voices (en-IN/hi-IN in
# tts_engine.VOICES) are female.
#
# A real person waiting on a call doesn't stay quiet for 8+ seconds then say
# one canned line - they murmur short "still thinking" sounds every couple of
# seconds. This is a short varied set of natural fillers (not one phrase
# repeated, which sounds robotic) played periodically through the wait
# instead of two fixed lines with long dead silence between. Generated once
# at startup and reused (not per-call) so none of this adds hot-path latency.
# Deliberately generic acknowledgments, NOT "let me check that for you" -
# that phrasing implies looking something up, which sounds wrong when the
# caller just said something like "I'm not interested" (nothing to check).
# These work regardless of what kind of turn it was.
FILLER_TEXT_INITIAL = {
    "hi": "Ek second...",
    "en": "Just a moment...",
}
FILLER_TEXTS_CYCLE = {
    "hi": ["Hmm...", "Bas ek pal...", "Ji, ek minute..."],
    "en": ["Hmm...", "Okay...", "Just a second..."],
}
# Poll attempt on which each cycled filler plays (every other attempt keeps
# it frequent without overlapping the previous line's own playback time).
FILLER_CYCLE_START_ATTEMPT = 2
FILLER_CYCLE_INTERVAL = 2

_filler_audio_urls: dict = {}


def _get_filler_audio_url(key: str, text: str, lang: str) -> str:
    if key not in _filler_audio_urls:
        _filler_audio_urls[key] = _publish_audio(synthesize(text, lang))
    return _filler_audio_urls[key]


def _initial_filler_for(lang: str) -> str:
    lang = lang if lang in FILLER_TEXT_INITIAL else "en"
    return _get_filler_audio_url(f"initial_{lang}", FILLER_TEXT_INITIAL[lang], lang)


def _cycled_filler_for(lang: str, attempt: int) -> str:
    lang = lang if lang in FILLER_TEXTS_CYCLE else "en"
    texts = FILLER_TEXTS_CYCLE[lang]
    index = (attempt - FILLER_CYCLE_START_ATTEMPT) // FILLER_CYCLE_INTERVAL
    text = texts[index % len(texts)]
    return _get_filler_audio_url(f"cycle_{lang}_{index % len(texts)}", text, lang)


def warm_up_fillers() -> None:
    for lang, text in FILLER_TEXT_INITIAL.items():
        _get_filler_audio_url(f"initial_{lang}", text, lang)
    for lang, texts in FILLER_TEXTS_CYCLE.items():
        for i, text in enumerate(texts):
            _get_filler_audio_url(f"cycle_{lang}_{i}", text, lang)


# A live call was measured at ~10-14s per turn (real phone audio + network
# overhead through a free tunnel), well past what a synchronous Twilio
# webhook can wait for (Twilio times out and announces "an application
# error has occurred"). So instead: respond to each webhook instantly, and
# hold the caller with short silent pauses while polling for the background
# result. 12 attempts * ~2.5s = ~30s of headroom before we give up.
POLL_PAUSE_SECONDS = 2
MAX_POLL_ATTEMPTS = 12


def _publish_audio(local_path: str) -> str:
    """Copy a generated audio file into the public static folder and return
    the public URL Twilio can fetch it from (Twilio needs a public URL, it
    can't reach a local file path)."""
    filename = f"{uuid.uuid4()}.mp3"
    shutil.copy(local_path, AUDIO_DIR / filename)
    return f"{settings.public_base_url}/audio/{filename}"


def _record_next_turn(vr: VoiceResponse) -> None:
    vr.record(
        action=f"{settings.public_base_url}/twilio/handle-recording",
        method="POST",
        max_length=8,
        # Silence-detection timeout: how long Twilio waits after you stop
        # talking before it's confident you're actually done (this, not our
        # server, is most of the "delay before the filler plays" you heard -
        # we don't even get the recording until this timeout fires). Was
        # trimmed to 2s for a snappier feel, but that caused a real call to
        # lose an entire turn (caller paused briefly mid-sentence, Twilio cut
        # the recording before they finished, STT got empty audio, call
        # ended with "I didn't catch that"). A dropped turn is far worse
        # than 1 extra second of latency - reverted to 3s.
        timeout=3,
        play_beep=False,
        trim="trim-silence",
    )


def _redirect_to_poll(vr: VoiceResponse, call_sid: str, attempt: int) -> None:
    vr.pause(length=POLL_PAUSE_SECONDS)
    vr.redirect(
        f"{settings.public_base_url}/twilio/poll?call_sid={call_sid}&attempt={attempt}",
        method="POST",
    )


def _download_recording_with_retries(recording_url: str, attempts: int = 3) -> bytes:
    """A real call disconnected because ONE transient DNS/network hiccup
    downloading the caller's recording killed the entire turn with no retry
    (httpx.ConnectError: getaddrinfo failed). A brief network blip shouldn't
    be able to end a live call - retry with short backoff before giving up."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return httpx.get(
                f"{recording_url}.mp3",
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                timeout=20,
            ).content
        except httpx.HTTPError as e:
            last_error = e
            logger.warning(
                "Recording download attempt %d/%d failed: %s", attempt, attempts, e
            )
            if attempt < attempts:
                time.sleep(1.5 * attempt)
    raise last_error


def _process_turn_in_background(call_sid: str, recording_url: str) -> None:
    """Runs the full STT -> LLM -> TTS pipeline outside the Twilio request/
    response cycle, since it's too slow to fit inside a single webhook call."""
    conversation = call_sessions.get(call_sid)
    try:
        audio_bytes = _download_recording_with_retries(recording_url)
        local_in_path = AUDIO_DIR / f"in_{uuid.uuid4()}.mp3"
        local_in_path.write_bytes(audio_bytes)

        caller_text, agent_text, agent_audio_path = handle_turn(conversation, str(local_in_path))
        call_results[call_sid] = {
            "status": "done",
            "audio_url": _publish_audio(agent_audio_path),
            "caller_text": caller_text,
            "end_call": conversation.should_end_call,
        }
    except Exception as e:
        # Without this, a background-task failure was silently swallowed into
        # call_results with no way to ever find out what actually went wrong.
        logger.exception("Turn processing failed for call_sid=%s", call_sid)
        call_results[call_sid] = {"status": "error", "error": str(e)}


def _start_call_recording_with_retries(call_sid: str, attempts: int = 3) -> None:
    """A call recording once failed to start with 'Requested resource is not
    eligible for recording' - likely a race where the call leg isn't fully
    'in-progress' yet the instant this fires. Retries with a short delay;
    best-effort overall, a recording failure should never break the call
    itself (that's why this runs as a background task, off voice_incoming's
    critical path, and every failure here is only ever logged, never raised)."""
    for attempt in range(1, attempts + 1):
        try:
            _twilio_client.calls(call_sid).recordings.create(recording_channels="dual")
            return
        except Exception as e:
            logger.warning(
                "Recording start attempt %d/%d failed for call_sid=%s: %s",
                attempt,
                attempts,
                call_sid,
                e,
            )
            if attempt < attempts:
                time.sleep(1.5 * attempt)
    logger.error("Giving up starting full-call recording for call_sid=%s", call_sid)


@router.post("/voice")
def voice_incoming(
    background_tasks: BackgroundTasks,
    CallSid: str = Form(...),
    Direction: str = Form(None),
    To: str = Form(None),
    From: str = Form(None),
):
    """Twilio hits this the moment a call connects - for both calls dialing
    in, and calls we placed via scripts/make_outbound_calls.py (Twilio still
    fetches this same URL for those; Direction tells them apart)."""
    is_outbound = Direction == "outbound-api"
    # Outbound: To is the number we dialed (the callee). Inbound: From is the
    # caller's own number (their caller ID). Either way, it's a number we
    # already have - see build_system_prompt's known_phone_number handling.
    raw_number = To if is_outbound else From
    known_phone_number = re.sub(r"\D", "", raw_number)[-10:] if raw_number else None

    call_sessions[CallSid] = Conversation(
        known_phone_number=known_phone_number, is_outbound=is_outbound
    )

    # Records the WHOLE call (both what's played to the caller and what they
    # say) as one continuous file - useful as a durable portfolio artifact
    # later. Backgrounded so a slow/retried Twilio API call never delays the
    # greeting the caller actually hears.
    background_tasks.add_task(_start_call_recording_with_retries, CallSid)

    text = OUTBOUND_GREETING_TEXT if is_outbound else GREETING_TEXT
    greeting_audio = synthesize(text, "en")
    public_url = _publish_audio(greeting_audio)

    vr = VoiceResponse()
    vr.play(public_url)
    _record_next_turn(vr)
    return Response(content=str(vr), media_type="application/xml")


@router.post("/handle-recording")
def handle_recording(
    background_tasks: BackgroundTasks,
    CallSid: str = Form(...),
    RecordingUrl: str = Form(None),
):
    """Twilio hits this after each recorded caller utterance. Responds
    instantly and kicks off processing in the background - see module
    docstring comment above call_results for why."""
    vr = VoiceResponse()

    if CallSid not in call_sessions or not RecordingUrl:
        logger.warning(
            "handle-recording rejected: call_sid=%s in_sessions=%s has_recording_url=%s",
            CallSid,
            CallSid in call_sessions,
            bool(RecordingUrl),
        )
        vr.say("Sorry, something went wrong. Please call again.")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    call_results[CallSid] = {"status": "processing"}
    background_tasks.add_task(_process_turn_in_background, CallSid, RecordingUrl)

    caller_lang = call_sessions[CallSid].last_lang
    vr.play(_initial_filler_for(caller_lang))
    _redirect_to_poll(vr, CallSid, attempt=1)
    return Response(content=str(vr), media_type="application/xml")


@router.post("/poll")
def poll(call_sid: str, attempt: int = 1):
    """Holds the caller with short silent pauses until the background turn
    (see _process_turn_in_background) finishes, errors, or we give up."""
    result = call_results.get(call_sid)
    vr = VoiceResponse()

    if result and result["status"] == "done":
        call_results.pop(call_sid, None)
        vr.play(result["audio_url"])
        if not result["caller_text"].strip() or result["end_call"]:
            vr.hangup()
            call_sessions.pop(call_sid, None)
        else:
            _record_next_turn(vr)
        return Response(content=str(vr), media_type="application/xml")

    if result and result["status"] == "error":
        call_results.pop(call_sid, None)
        call_sessions.pop(call_sid, None)
        vr.say("Sorry, something went wrong. Please call again.")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    if attempt >= MAX_POLL_ATTEMPTS:
        call_results.pop(call_sid, None)
        call_sessions.pop(call_sid, None)
        vr.say("Sorry, that's taking longer than expected. Please call again.")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    if attempt >= FILLER_CYCLE_START_ATTEMPT and (attempt - FILLER_CYCLE_START_ATTEMPT) % FILLER_CYCLE_INTERVAL == 0:
        conversation = call_sessions.get(call_sid)
        caller_lang = conversation.last_lang if conversation else "en"
        vr.play(_cycled_filler_for(caller_lang, attempt))

    _redirect_to_poll(vr, call_sid, attempt=attempt + 1)
    return Response(content=str(vr), media_type="application/xml")
