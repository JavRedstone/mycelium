"""
Planner agent — decides the corrective GitLab actions and graph updates to make.

Built with ADK on top of Vertex AI per the hackathon's mandatory stack.
"""
from __future__ import annotations

import asyncio
import json
import logging

import vertexai
from google.adk.agents import Agent
from vertexai.preview.reasoning_engines import AdkApp

from agent.json_utils import try_parse_json as _try_parse_json
from config.settings import settings

logger = logging.getLogger(__name__)

vertexai.init(
    project=settings.google_cloud_project,
    location=settings.google_cloud_location,
)


_INSTRUCTION = """You are an engineering continuity planner.

You receive a continuity INTERPRETATION (findings with concern_type, narrative,
evidence, recommended_actions) plus repository and knowledge-graph state.

Per PROJECT_IDEA: there is no scalar risk model. Do NOT reason about scores or
severity buckets. Reason about whether each finding warrants a concrete GitLab
action right now, given its narrative and recommended_actions.

GitLab action kinds available: create_issue, assign_issue, add_comment, generate_onboarding_pack, generate_offboarding_artifact
Knowledge graph collections: developers, modules, tasks, contributions

Only plan actions where there is clear evidence from the data. Do not invent data.
Do not create more than 3-4 new issues per run to avoid noise.

PLANNING GUIDANCE BY CONCERN TYPE:

knowledge_concentration / multi_module_overload / fading_contributor:
  Consider creating an issue titled "Knowledge Transfer: [subject]" describing
  what would be lost and recommending a pairing or handoff action. Suggest
  candidate assignees from the graph where possible.

fragile_documentation:
  Consider creating an issue to write or update the README/architecture doc
  for the affected module. Reference the investigator's documentation_gaps if
  present in the evidence.

upstream_dominance / upstream_drift:
  Consider an issue describing the dark-knowledge area or the missing upstream
  context. For drift, mention the high_priority_commits the drift investigator
  flagged if any.

stalled_work:
  Consider commenting on the issue/MR to nudge triage, or reassigning to an
  active member.

undeclared_ownership / nominal_ownership:
  Consider an issue proposing CODEOWNERS edits.

ci_instability:
  Consider an issue tagging the most active contributor for the affected area.

recent_joiner_exposure / onboarding_isolation:
  Call generate_onboarding_pack with the new member's username. This creates a
  structured onboarding guide as a GitLab issue: team roster, module expert map,
  and a starter checklist. Do this once per new joiner detected in the findings.

fading_contributor / offboarding_risk:
  Call generate_offboarding_artifact with the member's username. This creates a
  handoff issue documenting their at-risk modules, knowledge gaps, and transfer
  candidates. Do this when a member investigator flagged recently_inactive or
  sole_contributor with low transferability.

For graph_updates, include contributors whose only signal is MR approvals
(expertise_score: 0.6) — they are implicit knowledge holders. Set external=true
for developer entries that match upstream authors in the investigations.

OUTPUT: Respond with ONLY a valid JSON object. No explanation, no markdown.
Schema:
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

_USER_ID = "mycelium-planner"

root_agent = Agent(
    model=settings.gemini_model,
    name="mycelium_planner_agent",
    description="Plans GitLab corrective actions and graph updates from risk assessments.",
    instruction=_INSTRUCTION,
)


def _run_through_adk(prompt: str) -> str:
    app = AdkApp(agent=root_agent)
    session = app.create_session(user_id=_USER_ID)
    chunks: list[str] = []
    try:
        for event in app.stream_query(
            user_id=_USER_ID,
            session_id=session["id"],
            message=prompt,
        ):
            if not isinstance(event, dict):
                continue
            parts = (event.get("content") or {}).get("parts") or []
            for p in parts:
                text = p.get("text")
                if text:
                    chunks.append(text)
    finally:
        try:
            app.delete_session(user_id=_USER_ID, session_id=session["id"])
        except Exception:
            pass
    return "\n".join(chunks).strip()


def plan(interpretation: dict, repo_snapshot: dict, graph_snapshot: dict) -> dict:
    """Build a remediation plan from the analyst's findings.

    interpretation is the analyst output: {"synthesis": "...", "findings": [...]}.
    """
    context = {
        "interpretation": interpretation,
        "repository": repo_snapshot,
        "knowledge_graph": graph_snapshot,
    }
    prompt = (
        f"Context:\n{json.dumps(context, indent=2, default=str)}\n\n"
        "Return ONLY a JSON object matching the schema in your instructions."
    )

    try:
        text = _run_through_adk(prompt)
    except Exception as exc:
        logger.warning("[planner] AdkApp run failed (%s) — empty plan", exc)
        return {"actions": [], "graph_updates": []}

    if not text:
        logger.warning("[planner] empty output from ADK — empty plan")
        return {"actions": [], "graph_updates": []}

    parsed = _try_parse_json(text)
    if parsed is None:
        logger.warning("[planner] non-JSON output — empty plan. text[:200]=%r", text[:200])
        return {"actions": [], "graph_updates": []}
    return parsed


async def plan_async(interpretation: dict, repo_snapshot: dict, graph_snapshot: dict) -> dict:
    return await asyncio.to_thread(plan, interpretation, repo_snapshot, graph_snapshot)
