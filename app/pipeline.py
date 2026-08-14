import re

from app.llm.conversation import Conversation
from app.stt.whisper_stt import transcribe
from app.tts.tts_engine import VOICES, synthesize


def _strip_markdown(text: str) -> str:
    """The LLM sometimes uses markdown (e.g. **bold**) despite being told not
    to in the system prompt. TTS engines read those symbols aloud literally
    (e.g. repeated '**' comes out as a garbled repeating noise), so this is
    a hard guarantee, not just a prompt instruction the model might skip."""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"[*_`#]", "", text)
    return text


NO_SPEECH_FALLBACK_TEXT = "Sorry, I didn't catch that. Goodbye for now."


def handle_turn(conversation: Conversation, audio_in_path: str) -> tuple[str, str, str]:
    """One turn of the call: audio in -> STT -> LLM -> TTS -> audio out.

    Returns (caller_text, agent_text, audio_out_path).
    """
    caller_text, detected_lang = transcribe(audio_in_path)
    reply_lang = detected_lang if detected_lang in VOICES else "en"
    # Remembered so the NEXT turn's filler phrase (played before we've
    # transcribed anything, in twilio_routes.handle_recording) can match the
    # caller's language too, instead of always defaulting to Hindi.
    conversation.last_lang = reply_lang

    if not caller_text.strip():
        # Whisper can return an empty transcript for silence/background
        # noise/an unparseable sound. Sending that to the LLM as a "user"
        # message crashes the API call outright (it rejects empty content),
        # so skip the LLM entirely - there's nothing to respond to anyway.
        # The caller (twilio_routes.poll) already treats empty caller_text
        # as "end the call gracefully", this just gives it something to play.
        audio_out_path = synthesize(NO_SPEECH_FALLBACK_TEXT, "en")
        return caller_text, NO_SPEECH_FALLBACK_TEXT, audio_out_path

    agent_text = conversation.respond(caller_text)
    audio_out_path = synthesize(_strip_markdown(agent_text), reply_lang)

    return caller_text, agent_text, audio_out_path
