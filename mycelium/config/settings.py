# Copyright 2026 Javier Huang
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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

    # GitLab webhook signing token — must match the "Signing token" set in
    # GitLab → Settings → Webhooks. Stored with the whsec_ prefix exactly as
    # GitLab generates it. Leave empty to skip verification (local dev only).
    gitlab_webhook_signing_token: str = os.getenv("GITLAB_WEBHOOK_SIGNING_TOKEN", "")

    # CORS — comma-separated list of allowed origins.
    # Set to "*" in production (Cloud Run) to allow Vercel and other frontends.
    # Defaults to localhost for local dev.
    cors_origins: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if o.strip()
    ]


settings = Settings()

# Route all Gemini calls through Vertex AI (required per hackathon constraints).
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
os.environ["GOOGLE_CLOUD_LOCATION"] = settings.google_cloud_location
