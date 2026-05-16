import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    gemini_api_key: str = os.environ["GEMINI_API_KEY"]
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    google_cloud_project: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    google_cloud_region: str = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")

    mongodb_uri: str = os.environ["MONGODB_URI"]
    mongodb_db: str = os.getenv("MONGODB_DB", "mycelium")

    gitlab_url: str = os.getenv("GITLAB_URL", "https://gitlab.com")
    gitlab_token: str = os.environ["GITLAB_TOKEN"]
    gitlab_project_id: int = int(os.environ["GITLAB_PROJECT_ID"])

    agent_loop_interval: int = int(os.getenv("AGENT_LOOP_INTERVAL_SECONDS", "300"))


settings = Settings()
