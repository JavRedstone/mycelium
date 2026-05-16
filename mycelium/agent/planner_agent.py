import json
import logging
import time
import requests
from config.settings import settings

logger = logging.getLogger(__name__)

_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
)
_HEADERS = {"Content-Type": "application/json"}
_REQUEST_TIMEOUT_SECONDS = 60
_MAX_ATTEMPTS = 4
_RETRY_WAITS = [5, 15, 40]

_PROMPT = """You are an engineering continuity planner.

Given risk assessments and repository/graph state, decide the corrective actions to execute
in GitLab and the updates to write to the knowledge graph.

GitLab action kinds available: create_issue, assign_issue, comment_issue, comment_mr
Knowledge graph collections: developers, modules, tasks, contributions

Only plan actions where there is clear evidence from the data. Do not invent data.

PLANNING RULES FOR SPECIAL SIGNALS:

external_contributors: If modules have high external/upstream authorship, create a GitLab issue
  titled "Knowledge Transfer: [module] — upstream author context missing" describing which modules
  carry dark knowledge risk. Label these issues ["continuity", "upstream-knowledge", "risk"].
  Update the graph: set external=true for those developer entries.

codeowners: If codeowners data shows declared owners with no recent activity, create an issue to
  reassign or validate ownership. Update the modules collection with the declared owners list.
  If a high-risk module has no CODEOWNERS entry, create an issue to add one.

pipeline failures: If pipelines are failing in modules with high risk scores, create an issue
  prioritizing stabilization and assign to the module's most active current contributor.

mr_approvers: When planning graph_updates, include contributors whose only signal is MR approvals
  (expertise_score: 0.6) — they are implicit knowledge holders for those code areas.

OUTPUT: Respond with ONLY a valid JSON object. No explanation, no reasoning, no markdown.
{
  "actions": [
    {
      "kind": "create_issue",
      "params": {
        "title": "...",
        "description": "...",
        "labels": []
      }
    }
  ],
  "graph_updates": [
    {
      "collection": "developers",
      "data": {
        "gitlab_id": 123,
        "username": "...",
        "name": "...",
        "active": true,
        "external": false,
        "expertise": {}
      }
    }
  ]
}
"""


def plan(risk_assessments: dict, repo_snapshot: dict, graph_snapshot: dict) -> dict:
    context = {
        "risk_assessments": risk_assessments,
        "repository": repo_snapshot,
        "knowledge_graph": graph_snapshot,
    }
    body = {
        "contents": [{"role": "user", "parts": [{"text": f"{_PROMPT}\n\n---\n\nContext:\n{json.dumps(context, indent=2, default=str)}"}]}],
        "generationConfig": {"temperature": 0.2},
    }

    data = _request_with_retry(body)
    if data is None:
        logger.warning("Planner request failed after retries; using safe fallback")
        return {"actions": [], "graph_updates": []}

    candidate = (data.get("candidates") or [{}])[0]
    finish_reason = candidate.get("finishReason")
    if finish_reason not in ("STOP", "MAX_TOKENS", None):
        logger.warning("Planner finishReason=%s; using safe fallback", finish_reason)
        return {"actions": [], "graph_updates": []}

    parts = candidate.get("content", {}).get("parts", [])
    text = "\n".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
    if not text:
        raise ValueError("Gemini returned empty text")
    logger.debug("Planner output: %s", text[:300])

    parsed = _try_parse_json(text)
    if parsed is not None:
        return parsed

    logger.warning("Planner returned non-JSON output, using safe fallback")
    return {"actions": [], "graph_updates": []}


def _request_with_retry(body: dict) -> dict | None:
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = requests.post(
                _API_URL,
                headers=_HEADERS,
                json=body,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            logger.warning(
                "Planner request attempt %d/%d failed for model %s: %s",
                attempt, _MAX_ATTEMPTS, settings.gemini_model, exc,
            )
            if attempt < _MAX_ATTEMPTS:
                wait = _RETRY_WAITS[attempt - 1]
                if status is None or status in (429, 500, 502, 503):
                    logger.info("Planner: waiting %ds before retry (status=%s)…", wait, status)
                    time.sleep(wait)
                else:
                    break
        except ValueError as exc:
            last_error = exc
            logger.warning("Planner: invalid JSON envelope on attempt %d/%d: %s", attempt, _MAX_ATTEMPTS, exc)
            break
    if last_error:
        logger.error("Planner request failed permanently: %s", last_error)
    return None


def _try_parse_json(text: str) -> dict | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = cleaned[start:end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return None
    return None
