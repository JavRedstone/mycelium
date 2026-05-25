"""
Deploy the Mycelium act agent to Vertex AI Agent Engine.

This implements the required hackathon pattern:

    from google.adk.agents import Agent
    from vertexai.preview.reasoning_engines import AdkApp
    from vertexai import agent_engines

    app = AdkApp(agent=root_agent)
    remote = agent_engines.create(app, requirements=[...], extra_packages=[...])

Usage:
    # Create / replace the deployment
    python deployment/deploy.py --create

    # List deployed agents
    python deployment/deploy.py --list

    # Delete a deployed agent by resource ID
    python deployment/deploy.py --delete --resource_id <id>

Required environment variables (read from .env):
    GOOGLE_CLOUD_PROJECT
    GOOGLE_CLOUD_LOCATION             (default: us-central1)
    GOOGLE_CLOUD_STORAGE_BUCKET       (staging bucket - without `gs://` prefix)
    GITLAB_TOKEN, GITLAB_PROJECT_ID, MONGODB_URI  (forwarded to the runtime)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import vertexai
from absl import app, flags
from dotenv import load_dotenv
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

# Make `agent`, `config`, etc. importable when invoked from anywhere.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.act_agent import root_agent  # noqa: E402

FLAGS = flags.FLAGS
flags.DEFINE_string("project_id", None, "GCP project ID (default: $GOOGLE_CLOUD_PROJECT).")
flags.DEFINE_string("location", None, "GCP location (default: $GOOGLE_CLOUD_LOCATION).")
flags.DEFINE_string("bucket", None, "GCS staging bucket (default: $GOOGLE_CLOUD_STORAGE_BUCKET).")
flags.DEFINE_string("resource_id", None, "ReasoningEngine resource ID (required for --delete).")
flags.DEFINE_bool("list", False, "List all deployed agents.")
flags.DEFINE_bool("create", False, "Create / replace the Mycelium agent deployment.")
flags.DEFINE_bool("delete", False, "Delete a deployed agent by --resource_id.")
flags.mark_bool_flags_as_mutual_exclusive(["create", "delete", "list"])


_REQUIREMENTS = [
    "google-adk>=1.31.0",
    "google-cloud-aiplatform[adk,agent_engines]>=1.93.0",
    "google-genai>=1.9.0",
    "pydantic>=2.10.6",
    "pydantic-settings>=2.7.1",
    "python-dotenv>=1.0.1",
    "mcp>=1.5.0",
    "python-gitlab>=4.5.0",
    "pymongo[srv]>=4.7.0",
    "motor>=3.4.0",
    "httpx>=0.27.0",
]

# Bundle the agent package + supporting modules so the runtime can import them.
_EXTRA_PACKAGES = [
    str(_PROJECT_ROOT / "agent"),
    str(_PROJECT_ROOT / "config"),
    str(_PROJECT_ROOT / "graph"),
    str(_PROJECT_ROOT / "connectors"),
    str(_PROJECT_ROOT / "risk"),
]


def _env_settings() -> dict[str, str]:
    """Environment variables to forward to the Agent Engine runtime."""
    forward = {
        "GOOGLE_GENAI_USE_VERTEXAI": "True",
    }
    for name in (
        "GITLAB_URL", "GITLAB_TOKEN", "GITLAB_PROJECT_ID",
        "MONGODB_URI", "MONGODB_DB",
        "GEMINI_MODEL",
    ):
        value = os.getenv(name)
        if value:
            forward[name] = value
    return forward


def create() -> None:
    adk_app = AdkApp(agent=root_agent)
    remote = agent_engines.create(
        adk_app,
        display_name="mycelium-continuity-agent",
        description="Mycelium - autonomous engineering continuity agent with "
                    "GitLab MCP + MongoDB MCP toolsets.",
        requirements=_REQUIREMENTS,
        extra_packages=_EXTRA_PACKAGES,
        env_vars=_env_settings(),
    )
    print(f"[OK] Created remote agent: {remote.resource_name}")


def delete(resource_id: str) -> None:
    remote = agent_engines.get(resource_id)
    remote.delete(force=True)
    print(f"[OK] Deleted remote agent: {resource_id}")


def list_agents() -> None:
    template = (
        "{agent.name} (\"{agent.display_name}\")\n"
        "  - Create time: {agent.create_time}\n"
        "  - Update time: {agent.update_time}\n"
    )
    output = "\n".join(template.format(agent=a) for a in agent_engines.list())
    print(f"All remote agents:\n{output}" if output else "No remote agents found.")


def main(argv: list[str]) -> None:
    del argv  # unused
    load_dotenv()

    project_id = FLAGS.project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = FLAGS.location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    bucket = FLAGS.bucket or os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET")

    missing = [
        name for name, value in [
            ("GOOGLE_CLOUD_PROJECT", project_id),
            ("GOOGLE_CLOUD_LOCATION", location),
            ("GOOGLE_CLOUD_STORAGE_BUCKET", bucket),
        ]
        if not value
    ]
    if missing:
        print(f"[FAIL] Missing required configuration: {', '.join(missing)}")
        return

    print(f"PROJECT:  {project_id}")
    print(f"LOCATION: {location}")
    print(f"BUCKET:   gs://{bucket}")

    vertexai.init(
        project=project_id,
        location=location,
        staging_bucket=f"gs://{bucket}",
    )

    if FLAGS.list:
        list_agents()
    elif FLAGS.create:
        create()
    elif FLAGS.delete:
        if not FLAGS.resource_id:
            print("[FAIL] --resource_id is required for --delete")
            return
        delete(FLAGS.resource_id)
    else:
        print("Pass one of --create, --list, --delete.")


if __name__ == "__main__":
    app.run(main)
