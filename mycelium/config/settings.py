"""Mycelium settings - read from environment variables at startup.

Operational settings (loop enabled/interval, max investigators) are stored in
MongoDB and editable via PATCH /config without restarting the server.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name!r} is not set.")
    return value


class Settings:
    google_cloud_project: str = _require("GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    google_cloud_storage_bucket: str = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "")

    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    mongodb_uri: str = _require("MONGODB_URI")
    mongodb_db: str = os.getenv("MONGODB_DB", "mycelium")

    gitlab_url: str = os.getenv("GITLAB_URL", "https://gitlab.com")
    gitlab_token: str = _require("GITLAB_TOKEN")
    gitlab_project_id: int = int(_require("GITLAB_PROJECT_ID"))

    # Deployment-level flags - require a server restart to change.
    demo_mode: bool = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")
    gitlab_bot_username: str = os.getenv("GITLAB_BOT_USERNAME", "mycelium-bot")


settings = Settings()

# Route all Gemini calls through Vertex AI (required per hackathon constraints).
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
os.environ["GOOGLE_CLOUD_LOCATION"] = settings.google_cloud_location
