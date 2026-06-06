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

"""
Sanity check: ADK (google.adk) is installed and Vertex AI Agent Engine's
AdkApp runtime can execute a no-tools agent end-to-end against Vertex AI Gemini.

Validates the full stack:
    google.adk.agents.Agent
        ↓
    vertexai.preview.reasoning_engines.AdkApp     (Agent Engine runtime)
        ↓
    Gemini via Vertex AI
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def main() -> int:
    try:
        project = os.environ["GOOGLE_CLOUD_PROJECT"]
    except KeyError:
        print("[FAIL] ADK - GOOGLE_CLOUD_PROJECT is not set")
        return 1

    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    os.environ["GOOGLE_CLOUD_LOCATION"] = location

    try:
        import vertexai
        from google.adk.agents import Agent
        from vertexai.preview.reasoning_engines import AdkApp

        vertexai.init(project=project, location=location)

        agent = Agent(
            model=model,
            name="adk_smoketest_agent",
            description="ADK smoke-test agent - no tools.",
            instruction="You are a smoke-test agent. Reply with one word only: ok",
        )
        app = AdkApp(agent=agent)

        user_id = "adk-smoketest"
        session = app.create_session(user_id=user_id)
        try:
            chunks: list[str] = []
            for event in app.stream_query(
                user_id=user_id,
                session_id=session["id"],
                message="ping",
            ):
                if not isinstance(event, dict):
                    continue
                for part in (event.get("content") or {}).get("parts") or []:
                    if "text" in part:
                        chunks.append(part["text"])
            text = "".join(chunks).strip()
        finally:
            try:
                app.delete_session(user_id=user_id, session_id=session["id"])
            except Exception:
                pass

        print(f"[OK] ADK + AdkApp - model={model}")
        print(f"     response: {text[:120]}")
        return 0
    except Exception as exc:
        print(f"[FAIL] ADK - {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
