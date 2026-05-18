"""
Interactive ADK agent runner — ask Mycelium's act agent a question.

Spins up the same ADK Agent that the pipeline uses (GitLab MCP + MongoDB MCP),
wraps it in `AdkApp`, and streams events for one prompt. The agent runs on
Vertex AI Gemini through the Agent Engine runtime.

Usage:
    python checks/check_ask.py
    python checks/check_ask.py "What are the riskiest modules?"
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.act_agent import root_agent  # noqa: E402  (loads vertexai.init via settings)
from vertexai.preview.reasoning_engines import AdkApp  # noqa: E402


_USER_ID = "mycelium-check-ask"


def ask(question: str) -> None:
    app = AdkApp(agent=root_agent)
    session = app.create_session(user_id=_USER_ID)
    print(f"Asking: {question}\n")

    try:
        for event in app.stream_query(
            user_id=_USER_ID,
            session_id=session["id"],
            message=question,
        ):
            if not isinstance(event, dict):
                continue
            for part in (event.get("content") or {}).get("parts") or []:
                fc = part.get("function_call") or part.get("functionCall")
                if fc:
                    name = fc.get("name")
                    args = fc.get("args") or {}
                    short = ", ".join(f"{k}={repr(v)[:40]}" for k, v in args.items())
                    print(f"  -> {name}({short})")
                text = part.get("text")
                if text:
                    print(text)
    finally:
        try:
            app.delete_session(user_id=_USER_ID, session_id=session["id"])
        except Exception:
            pass


def main() -> None:
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        print(f"Mycelium — interactive ADK agent  (Vertex AI, model: {model})")
        print("Tools: GitLab MCP + MongoDB MCP. Ctrl+C to quit.\n")
        try:
            question = input("Question: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            return
        if not question:
            print("No question entered.")
            return

    ask(question)


if __name__ == "__main__":
    main()
