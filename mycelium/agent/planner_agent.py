"""
Planner agent - decides the corrective GitLab actions and graph updates to make.

Built with ADK on top of Vertex AI per the hackathon's mandatory stack.
"""
from __future__ import annotations

import asyncio
import json
import logging

import vertexai
from google.adk.agents import Agent
from vertexai.preview.reasoning_engines import AdkApp

from agent.activity_bus import bus as _activity_bus
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

GitLab action kinds available: create_issue, assign_issue, add_comment, edit_issue, close_issue, generate_onboarding_pack, generate_offboarding_artifact
Knowledge graph collections: developers, modules, tasks, contributions

Only plan actions where there is clear evidence from the data. Do not invent data.
Do not create more than 3-4 new issues per run to avoid noise.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDEMPOTENCY - read this before planning anything
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The pipeline runs on a loop. Prior runs already created issues. Your first job
is to compare the analyst's findings against `knowledge_graph.open_tasks` (the
list of issues already open in GitLab). Then:

CREATING ISSUES
  - Check `repository.open_issues` (the live GitLab list, includes iid + title
    + author + bot_authored flag) AND `knowledge_graph.open_tasks`. If any
    existing issue has a title that covers the same subject and concern type,
    do NOT create another. One issue per finding - ever, across all runs.
  - Only create a new issue when no existing issue addresses the finding.
  - Issues with `bot_authored: true` were created by the service account on a
    prior run. The bot owns those issues and may freely edit or supersede them.
  - Issues with `bot_authored: false` were created by a human. Be conservative:
    prefer add_comment or leave them alone rather than editing or closing them.

COMMENTING ON ISSUES
  - Do NOT plan add_comment to rephrase or restate what an issue's title already
    says. That is noise. Do not do it.
  - Only plan add_comment when ALL of the following are true:
      1. There is new, concrete, measurable data since the issue was created -
         e.g. drift count changed from 15 to 30 commits, a member's status
         changed, a new CVE was identified by the investigator.
      2. That new data materially changes what the reader needs to know.
      3. You can name the specific new fact in the comment body.
  - If you cannot point to a specific new fact, omit the add_comment action.

EMPTY PLANS ARE CORRECT
  - After the initial issues are filed, most runs should produce
    {"actions": [], "graph_updates": []}. That is the right and expected outcome.
  - Do not force actions to justify a pipeline run. Silence is correct when
    nothing has materially changed since the last run.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ISSUE CORRECTION DECISION TREE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When an existing issue has incorrect, outdated, or mis-scoped content, choose
from this ordered decision tree - earlier tiers are always preferred:

TIER 1 - PREFER: edit_issue (edit in place)
  When to use: the issue topic and title are correct but the description body
  needs updating - e.g., new file paths discovered, a CODEOWNERS snippet
  changed, or the action list needs expanding.
  Plan: one edit_issue action with iid and the corrected description.
  Do NOT use if the issue already has significant discussion comments - editing
  the body can confuse readers who have replied to specific passages.

TIER 2 - DEFAULT: keep and fix forward (add_comment)
  When to use: the issue history and discussion context must be preserved,
  and the new information is an update rather than a correction.
  Plan: one add_comment action carrying only the new concrete fact.
  This is the correct choice for most follow-up runs where data has changed.

TIER 3 - RESERVED: supersede (create new + link + close old)
  When to use: the original issue has FUNDAMENTALLY incorrect framing that
  cannot be repaired by editing - e.g., wrong module scope, wrong person
  named as the risk, or the entire premise has been invalidated.
  Plan these three actions in order:
    1. create_issue - new issue with correct scope and full description
    2. add_comment  - on the OLD issue: "Superseded by #NEW_IID - <one-sentence reason>"
    3. close_issue  - on the OLD issue (state: closed, superseded)
  TRACEABILITY RULE: never close an issue without first adding the linking
  comment. Fragmented trackers (new issue exists but old is still open) are
  worse than doing nothing.
  Creating a new issue WITHOUT closing the old one is NEVER acceptable.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ISSUE DESCRIPTION QUALITY RULES (apply to ALL create_issue and edit_issue actions):
- Be concrete and data-driven. Cite specific module names, file counts, commit
  counts, or contributor names from the evidence. Never be vague.
- State the risk plainly in one sentence. Do not repeat it.
- Recommended actions must name specific modules, files, or people - not just
  "identify a second engineer" or similar generic instructions.
- Do NOT include meta-commentary about the pipeline, the agent, or what the
  subject is already doing. Write as if a human engineer composed the issue.
- No sentences of the form "While X is doing Y, Z is also important." They are
  circular and add no information. State Z directly.
- End with a concrete, ordered action list (1, 2, 3…) referencing actual data.

PLANNING GUIDANCE BY CONCERN TYPE:

knowledge_concentration / multi_module_overload / sole_contributor / fading_contributor:
  Create an issue titled "Knowledge Transfer: [subject]". The description must:
  - Name the specific modules/files at risk and why (e.g., "owns 87% of commits
    to src/auth/ and src/pipeline/ with no other reviewer in the last 6 months").
  - Name 1-2 specific candidate engineers from the graph who could be cross-trained.
  - List concrete onboarding steps: which modules to shadow, which MRs to review,
    which documentation to write.
  Suggest candidate assignees from the graph where possible.

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
  Create an issue proposing CODEOWNERS edits. The description must:
  - Name every specific path that needs an owner (e.g. `internal/`, `scripts/`).
  - Name the specific person to assign as owner - use the top internal committer
    for each path from the knowledge graph. Do not say "starting with X" or
    "propose candidates" - commit to a specific owner per path.
  - Include a ready-to-copy CODEOWNERS snippet the team can apply directly.

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
(expertise_score: 0.6) - they are implicit knowledge holders. Set external=true
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
    },
    {
      "kind": "edit_issue",
      "params": {
        "iid": 12,
        "description": "...",
        "title": "optional - omit to leave unchanged"
      }
    },
    {
      "kind": "add_comment",
      "params": {
        "iid": 12,
        "body": "..."
      }
    },
    {
      "kind": "close_issue",
      "params": {
        "iid": 12
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


def _run_through_adk(prompt: str, stage_id: str = "plan") -> str:
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
            content = event.get("content") if isinstance(event, dict) else getattr(event, "content", None)
            parts = (content.get("parts") if isinstance(content, dict) else getattr(content, "parts", None)) or []
            for p in parts:
                text = p.get("text") if isinstance(p, dict) else getattr(p, "text", None)
                if text:
                    chunks.append(str(text))
                    stripped = str(text).strip()
                    # Skip pure JSON output - already surfaced as structured action_planned events.
                    if stripped and not stripped.startswith(("{", "[")):
                        _activity_bus.emit({"type": "agent_text", "stage_id": stage_id, "text": stripped})
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
    from config.settings import settings
    context = {
        "interpretation": interpretation,
        "repository": repo_snapshot,
        "knowledge_graph": graph_snapshot,
    }
    demo_note = (
        "\n\nNOTE - DEMO MODE: some entries in knowledge_graph carry demo: true. "
        "Treat them as real contributors and modules; plan actions for them as you "
        "would for any other team member."
        if settings.demo_mode and graph_snapshot.get("demo_data_present")
        else ""
    )
    prompt = (
        f"Context:\n{json.dumps(context, indent=2, default=str)}{demo_note}\n\n"
        "Return ONLY a JSON object matching the schema in your instructions."
    )

    try:
        text = _run_through_adk(prompt)
    except Exception as exc:
        logger.warning("[planner] AdkApp run failed (%s) - empty plan", exc)
        return {"actions": [], "graph_updates": []}

    if not text:
        logger.warning("[planner] empty output from ADK - empty plan")
        return {"actions": [], "graph_updates": []}

    parsed = _try_parse_json(text)
    if parsed is None:
        logger.warning("[planner] non-JSON output - empty plan. text[:200]=%r", text[:200])
        return {"actions": [], "graph_updates": []}
    return parsed


async def plan_async(interpretation: dict, repo_snapshot: dict, graph_snapshot: dict) -> dict:
    return await asyncio.to_thread(plan, interpretation, repo_snapshot, graph_snapshot)
