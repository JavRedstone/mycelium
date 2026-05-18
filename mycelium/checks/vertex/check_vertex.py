"""
Sanity check: Vertex AI is reachable, ADC works, and the configured Gemini model
can be invoked through the Vertex AI Gemini endpoint.

This validates the hackathon-required path: Vertex AI (not Google AI Studio).
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
        print("[FAIL] Vertex AI — GOOGLE_CLOUD_PROJECT is not set")
        return 1

    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Route google-genai through Vertex AI rather than AI Studio.
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    os.environ["GOOGLE_CLOUD_LOCATION"] = location

    try:
        import vertexai
        from google import genai

        vertexai.init(project=project, location=location)

        client = genai.Client(vertexai=True, project=project, location=location)
        response = client.models.generate_content(
            model=model,
            contents="This is an API test call. Please respond with only the word: ok",
        )
        text = (response.text or "").strip()
        print(f"[OK] Vertex AI — project={project} location={location} model={model}")
        print(f"     response: {text}")
        return 0
    except Exception as exc:
        print(f"[FAIL] Vertex AI — {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
