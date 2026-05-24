"""
Mycelium configuration.

The runtime requires Vertex AI (not Google AI Studio) per hackathon requirements:
- Vertex AI SDK + Agent Engine
- ADK as agent construction framework
- Gemini accessed via Vertex AI

All Gemini calls happen through ADK + Vertex AI. AI Studio API keys are not used.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            f"Mycelium requires Vertex AI configuration — see README."
        )
    return value


class Settings:
    # --- Vertex AI / ADK ---
    google_cloud_project: str = _require("GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    # Staging bucket is only required when deploying to Agent Engine.
    google_cloud_storage_bucket: str = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "")

    # Default to a Vertex-AI-served Gemini model. Override via GEMINI_MODEL.
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # --- MongoDB ---
    mongodb_uri: str = _require("MONGODB_URI")
    mongodb_db: str = os.getenv("MONGODB_DB", "mycelium")

    # --- GitLab ---
    gitlab_url: str = os.getenv("GITLAB_URL", "https://gitlab.com")
    gitlab_token: str = _require("GITLAB_TOKEN")
    gitlab_project_id: int = int(_require("GITLAB_PROJECT_ID"))

    # --- Loop ---
    agent_loop_interval: int = int(os.getenv("AGENT_LOOP_INTERVAL_SECONDS", "300"))
    # Set PIPELINE_LOOP_ENABLED=false to disable auto-looping (saves AI costs during dev).
    # The manual POST /pipeline/run endpoint still works regardless.
    pipeline_loop_enabled: bool = os.getenv("PIPELINE_LOOP_ENABLED", "true").lower() in ("1", "true", "yes")

    # --- Demo mode ---
    # When true: demo-seeded data is visible to pipeline agents, agent prompts
    # receive a note about demo entries, and the /demo/seed endpoint is active.
    # Set false (the default) in production so agents only operate on real data.
    demo_mode: bool = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")

    # --- Service account ---
    # GitLab username of the project service account used for all automated
    # write actions (issue creation, comments, assignments, etc.).
    # Issues authored by this account are tagged bot_authored=True in the
    # repository snapshot so agents can distinguish automated from human issues,
    # and the account is excluded from team-member analysis.
    gitlab_bot_username: str = os.getenv("GITLAB_BOT_USERNAME", "mycelium-bot")


settings = Settings()

# Tell the google-genai SDK (used internally by ADK) to route through Vertex AI
# rather than the AI Studio public endpoint. Must be set BEFORE google-genai is imported.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
os.environ["GOOGLE_CLOUD_LOCATION"] = settings.google_cloud_location
