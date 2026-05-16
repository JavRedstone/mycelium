import json
import logging
import requests
from config.settings import settings
from agent.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
)
_HEADERS = {"Content-Type": "application/json"}


def _call_gemini(system_prompt: str, user_content: str) -> str:
    body = {
        "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n---\n\n{user_content}"}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    response = requests.post(_API_URL, headers=_HEADERS, json=body)
    response.raise_for_status()
    data = response.json()
    candidate = data["candidates"][0]
    finish_reason = candidate.get("finishReason")
    if finish_reason not in ("STOP", "MAX_TOKENS", None):
        logger.error("Gemini unexpected finishReason=%s | full response: %s", finish_reason, data)
        raise ValueError(f"Gemini returned finishReason={finish_reason}")
    parts = candidate.get("content", {}).get("parts", [])
    text = parts[0].get("text", "") if parts else ""
    if not text:
        logger.error("Gemini returned empty text | full response: %s", data)
        raise ValueError("Gemini returned empty text")
    return text


def _extract_json(text: str) -> dict:
    logger.debug("Raw Gemini text: %r", text)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    logger.debug("Extracted text for JSON parse: %r", text)
    return json.loads(text)


class ContinuityAgent:
    def reason(self, context: dict, task_prompt: str) -> dict:
        user_content = (
            f"{task_prompt}\n\n"
            "Respond with ONLY a raw JSON object. No explanation, no markdown, no code fences.\n\n"
            f"Context:\n{json.dumps(context, indent=2, default=str)}"
        )
        text = _call_gemini(SYSTEM_PROMPT, user_content)
        return _extract_json(text)

    def observe_and_decide(self, repo_snapshot: dict, knowledge_graph_state: dict) -> dict:
        context = {
            "repository": repo_snapshot,
            "knowledge_graph": knowledge_graph_state,
        }
        prompt = (
            "Analyze the repository and knowledge graph state. "
            "Return a JSON object with keys: "
            "'risk_assessments' (list of module risks), "
            "'actions' (list of GitLab actions to execute), "
            "'graph_updates' (list of knowledge graph writes)."
        )
        return self.reason(context, prompt)
