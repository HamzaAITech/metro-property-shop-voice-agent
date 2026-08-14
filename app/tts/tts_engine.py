import asyncio
import tempfile

import edge_tts

# Indian-accented voices, not US/UK — matches who's actually calling this shop.
# "Expressive" Neerja variant + a faster rate aim for a brisker, more modern
# delivery than the flat default. edge-tts's free tier only has ONE Hindi
# female voice (Swara) - there's no alternative to swap to for Hindi; a
# noticeably better Hindi voice would mean a paid provider (Google/Azure/
# ElevenLabs), a real cost tradeoff to weigh separately.
VOICES = {
    "en": "en-IN-NeerjaExpressiveNeural",
    "hi": "hi-IN-SwaraNeural",
}
SPEECH_RATE = "+8%"


async def _synthesize_async(text: str, language: str, output_path: str) -> None:
    voice = VOICES.get(language, VOICES["en"])
    communicate = edge_tts.Communicate(text, voice, rate=SPEECH_RATE)
    await communicate.save(output_path)


def synthesize(text: str, language: str = "en") -> str:
    """Synthesizes speech and returns the path to a temp mp3 file."""
    output_path = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    asyncio.run(_synthesize_async(text, language, output_path))
    return output_path
