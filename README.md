# Metro Property Shop Voice Agent

A bilingual (Hindi + English) AI voice agent for a real estate business, built end-to-end on a
free/low-cost stack: it answers inbound calls, handles listing queries, schedules site visits,
captures leads, and can also place outbound advertisement calls — over a real phone number.

**Demo recordings:** [`demo_recordings/`](demo_recordings/) — real, unedited calls (dead-air
between the caller finishing and the agent replying has been trimmed for listenability; nothing
else was cut).

## What it does

1. Greets the caller and detects/continues in whichever language they speak (Hindi, English, or
   mixed Hinglish) — including handling casual small talk naturally before steering back to
   business.
2. Gathers requirements: buy vs. rent, property type, budget, locality.
3. Matches against a real listings dataset and describes relevant options — never invents a
   listing that isn't in the data.
4. Offers to schedule a site visit and captures name, phone number, and preferred time.
5. Answers common questions (office hours, documents needed, brokerage) from a small FAQ dataset.
6. Recognizes when a caller wants to end the call — including "I'm in a hurry" style cues, not
   just an explicit goodbye — and saves whatever lead info it has rather than losing it.
7. Can also place outbound calls (`scripts/make_outbound_calls.py`) using the same conversational
   agent, with a distinct proactive greeting for calls the business initiates.

## Architecture

```
Caller <--> Twilio (telephony) <--> FastAPI backend
                                       |
                                       +-- STT: faster-whisper (self-hosted, GPU-accelerated)
                                       +-- LLM: Claude Haiku 4.5 (conversation + tool use)
                                       +-- TTS: edge-tts (free, Indian-accented voices)
                                       +-- SQLite (leads)
```

**Why this stack:** built deliberately on free/low-cost components (self-hosted STT/TTS instead
of paid cloud APIs) to prove the same product can be built without committing to recurring costs
before it's validated. See [`docs/Demo_Call_Script.md`](docs/Demo_Call_Script.md) for a ready-to-use
script that exercises the full range of capabilities in one call.

### A real engineering constraint worth knowing about

Twilio's voice webhooks are synchronous — respond too slowly and Twilio gives up with a generic
error. This stack's full pipeline (speech-to-text → LLM → text-to-speech) takes several seconds,
which doesn't fit inside a single webhook response. The fix: `/twilio/handle-recording` responds
to Twilio *instantly* and processes the turn in a background task, while `/twilio/poll` holds the
caller with short, spoken "thinking" filler phrases (bilingual, varied, not a single repeated line)
until the result is ready. See [`app/telephony/twilio_routes.py`](app/telephony/twilio_routes.py).

## Project layout

```
app/
  main.py              FastAPI app, routes, startup model warmup
  config.py             Environment-based settings
  pipeline.py            Wires one turn together: STT -> LLM -> TTS
  stt/whisper_stt.py      Speech-to-text (faster-whisper, GPU-accelerated)
  tts/tts_engine.py       Text-to-speech (edge-tts, Hindi + English voices)
  llm/
    conversation.py       Multi-turn conversation state + tool-use loop
    prompts.py             System prompt, tool schemas, listings/FAQ loading
  telephony/twilio_routes.py   Twilio webhooks (voice, recording, poll, background recording)
  storage/leads.py         SQLite-backed lead storage
  data/                    Sample listings + FAQ (placeholder business data)
scripts/
  make_outbound_calls.py     Places outbound calls through the same agent
  download_call_recording.py  Downloads a finished call's full recording
docs/
  Demo_Call_Script.md         A script anyone can read to exercise the full system
demo_recordings/            Real recorded demo calls
```

## Running it locally

```bash
python -m venv venv
venv/Scripts/pip install -r requirements.txt
cp .env.example .env   # fill in your own API keys
venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Needs a public URL for Twilio to reach it (ngrok/Cloudflare Tunnel for local dev, or a real
deployment) — set `PUBLIC_BASE_URL` in `.env` accordingly and point your Twilio number's Voice
webhook at `{PUBLIC_BASE_URL}/twilio/voice`.

If you have an NVIDIA GPU and want faster speech-to-text, also install
`nvidia-cublas-cu12` and `nvidia-cudnn-cu12` — deliberately left out of `requirements.txt` since
they're several hundred MB and dead weight on any machine without a GPU (Railway included).

## Known limitations (honest, not hidden)

- **Latency**: end-to-end turn time is realistically 8–14 seconds on this free/local stack —
  Whisper's encoder processes a fixed-size window regardless of clip length, which is the
  dominant, largely untunable cost. A paid streaming STT/TTS stack would get this well under
  2 seconds; that's a real cost tradeoff, not an oversight.
- **Placeholder business data**: the listings/FAQ are illustrative, not a real property
  inventory — this was built speculatively, without an existing client relationship.
- **Outbound compliance**: outbound calling is built and works, but real cold-list marketing
  calls in India require TRAI telemarketer registration, which is out of scope for this project.
