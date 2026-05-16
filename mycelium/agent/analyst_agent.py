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
# Waits (seconds) before attempt 2, 3, 4 — backs off for rate limiting (429)
_RETRY_WAITS = [5, 15, 40]

_PROMPT = """You are a continuity risk analyst for an engineering team.

Given the repository state and current knowledge graph, identify continuity risks.

Focus on:
- Knowledge concentration (low bus factor, single owners)
- Orphaned or stalled work (unassigned issues/MRs)
- Modules with no active ownership
- Developer inactivity risks
- External contributor concentration (upstream/fork authors whose knowledge is not held by any current team member)
- CODEOWNERS drift (declared owners who are inactive, or active modules with no declared owner)
- Pipeline health (failing CI/CD pipelines compound risk in low-bus-factor modules)

INTERPRETING EXTERNAL CONTRIBUTORS:
If a significant portion of commits to a module were made by external/upstream contributors
(authors not in the current member list), that module carries "dark knowledge" risk — the code
exists but its context and intent lives outside the team. Score these modules higher than their
current-member bus factor alone would suggest.

INTERPRETING CODEOWNERS:
Declared ownership is ground truth. If codeowners data is present, cross-reference:
- Declared owner with zero recent commits → ownership is nominal, not real → elevated risk
- Active module with no CODEOWNERS entry → undeclared ownership → medium risk

INTERPRETING PIPELINES:
A module with failing pipelines and bus factor ≤ 1 should be scored as high or critical
regardless of other signals.

OUTPUT: Respond with ONLY a valid JSON object. No explanation, no reasoning, no markdown.
{
  "overall_health": "healthy|at_risk|critical",
  "summary": "<one concise sentence>",
  "risk_assessments": [
    {
      "module": "<path or area name>",
      "risk_level": "low|medium|high|critical",
      "score": <0.0 to 1.0>,
      "reason": "<concise reason>"
    }
  ]
}
"""


def analyze(repo_snapshot: dict, graph_snapshot: dict) -> dict:
    context = {"repository": repo_snapshot, "knowledge_graph": graph_snapshot}
    body = {
        "contents": [{"role": "user", "parts": [{"text": f"{_PROMPT}\n\n---\n\nContext:\n{json.dumps(context, indent=2, default=str)}"}]}],
        "generationConfig": {"temperature": 0.2},
    }

    data = _request_with_retry(body)
    if data is None:
        logger.warning("Analyst request failed after retries; using deterministic fallback")
        return _fallback_risk_assessment(repo_snapshot, graph_snapshot)

    candidate = (data.get("candidates") or [{}])[0]
    finish_reason = candidate.get("finishReason")
    if finish_reason not in ("STOP", "MAX_TOKENS", None):
        logger.warning("Analyst finishReason=%s; using fallback", finish_reason)
        return _fallback_risk_assessment(repo_snapshot, graph_snapshot)

    parts = candidate.get("content", {}).get("parts", [])
    text = "\n".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
    if not text:
        raise ValueError("Gemini returned empty text")
    logger.debug("Analyst output: %s", text[:300])

    parsed = _try_parse_json(text)
    if parsed is not None:
        return parsed

    logger.warning("Analyst returned non-JSON output, using deterministic fallback")
    return _fallback_risk_assessment(repo_snapshot, graph_snapshot)


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
                "Analyst request attempt %d/%d failed for model %s: %s",
                attempt, _MAX_ATTEMPTS, settings.gemini_model, exc,
            )
            if attempt < _MAX_ATTEMPTS:
                wait = _RETRY_WAITS[attempt - 1]
                # Only sleep for rate limiting / server errors; fail fast on client errors
                if status is None or status in (429, 500, 502, 503):
                    logger.info("Analyst: waiting %ds before retry (status=%s)…", wait, status)
                    time.sleep(wait)
                else:
                    break
        except ValueError as exc:
            last_error = exc
            logger.warning("Analyst: invalid JSON envelope on attempt %d/%d: %s", attempt, _MAX_ATTEMPTS, exc)
            break  # Malformed response won't improve with retries
    if last_error:
        logger.error("Analyst request failed permanently: %s", last_error)
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


def _fallback_risk_assessment(repo_snapshot: dict, graph_snapshot: dict) -> dict:
    members = repo_snapshot.get("members", [])
    issues = repo_snapshot.get("open_issues", [])
    mrs = repo_snapshot.get("open_merge_requests", [])
    developers = graph_snapshot.get("developers", [])

    risks = []
    if len(members) <= 1:
        risks.append(
            {
                "module": "repository",
                "risk_level": "high",
                "score": 0.88,
                "reason": "Single active member creates high continuity and handoff risk.",
            }
        )

    if issues or mrs:
        risks.append(
            {
                "module": "work-queue",
                "risk_level": "medium",
                "score": 0.56,
                "reason": "Open issues/MRs should be actively triaged to avoid orphaned work.",
            }
        )

    if not developers:
        risks.append(
            {
                "module": "knowledge-graph",
                "risk_level": "medium",
                "score": 0.5,
                "reason": "No developer history captured yet, reducing confidence in ownership signals.",
            }
        )

    overall = "healthy"
    if any(r["risk_level"] == "high" for r in risks):
        overall = "at_risk"
    if any(r["risk_level"] == "critical" for r in risks):
        overall = "critical"

    if not risks:
        summary = "No significant continuity risks detected from current repository and graph state."
    else:
        summary = "Continuity risks detected; prioritize ownership spread and active work triage."

    return {
        "overall_health": overall,
        "summary": summary,
        "risk_assessments": risks,
    }
