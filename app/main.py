import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.dashboard import render_dashboard
from app.stt.whisper_stt import get_model
from app.storage import leads
from app.telephony.twilio_routes import AUDIO_DIR
from app.telephony.twilio_routes import router as twilio_router
from app.telephony.twilio_routes import warm_up_fillers

app = FastAPI(title="Property Shop Voice Agent")
app.include_router(twilio_router)
app.mount("/audio", StaticFiles(directory=Path(AUDIO_DIR)), name="audio")


@app.on_event("startup")
async def warm_up_models():
    # Loads the Whisper model and generates the filler audio now instead of
    # on the first real call, so a live caller never pays those costs.
    # Run in a thread: both are blocking calls, and the TTS one internally
    # uses asyncio.run() which can't nest inside uvicorn's running loop.
    await asyncio.to_thread(get_model)
    await asyncio.to_thread(warm_up_fillers)


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return render_dashboard(leads.list_leads())


@app.get("/leads")
def get_leads():
    return leads.list_leads()


@app.delete("/leads/{call_id}")
def remove_lead(call_id: str, token: str = ""):
    if not settings.admin_token or token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Invalid or missing token")
    if not leads.delete_lead(call_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"status": "deleted", "call_id": call_id}
