from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"

    anthropic_api_key: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # The ngrok (or later, Railway) URL Twilio can reach this server at -
    # needed so we can hand Twilio a public URL for our generated TTS audio.
    public_base_url: str = ""

    tts_provider: str = "edge-tts"

    # Required to hit DELETE /leads/{id} - the dashboard is public, so
    # deleting leads shouldn't be wide open to anyone who finds the URL.
    admin_token: str = ""

    # A code redeploy on Railway gets a fresh container filesystem - without
    # this pointed at a mounted persistent volume, every deploy silently
    # wipes every captured lead. Defaults to a local relative path (fine for
    # local dev, where the process/filesystem persists across restarts).
    leads_db_path: str = "leads.db"


settings = Settings()
