"""
Analyst agent - assesses continuity risk over the current GitLab + graph snapshot.

Built with ADK on top of Vertex AI per the hackathon's mandatory stack:
- google.adk.agents.Agent
- vertexai.preview.reasoning_engines.AdkApp (Agent Engine runtime)
- Gemini served by Vertex AI (not AI Studio)
"""
from __future__ import annotations

import asyncio
import json
import logging

import vertexai
from google.adk.agents import Agent
from vertexai.preview.reasoning_engines import AdkApp

from agent.activity_bus import bus as _activity_bus
from agent.json_utils import try_parse_json as _try_parse_json  # re-exported for tests
from config.settings import settings

logger = logging.getLogger(__name__)

vertexai.init(
    project=settings.google_cloud_project,
    location=settings.google_cloud_location,
)


_INSTRUCTION = """You are a continuity analyst for an engineering team.

Per the system design (PROJECT_IDEA.md), this system does NOT use scalar risk scores
or severity buckets. You produce structured FINDINGS - qualitative descriptions of
patterns in the knowledge graph, each with a concern type and a narrative.

You receive THREE bodies of evidence each run:

1. repository - observable facts from GitLab: members, commits, CODEOWNERS, pipelines,
   issues/MRs, fork divergence count, per-author commit counts.

2. knowledge_graph - current state from MongoDB: tracked developers, modules with
   prior risk scores, contribution edges.

3. investigations - output from investigator subagents that READ ACTUAL FILE CONTENT
   and produced their own structured judgments:
   - investigations.members[]   - per-member assessments (knowledge_at_risk,
     transferability_today, urgency_reasoning, recommended_actions).
   - investigations.modules[]   - per-module assessments (transferability_assessment,
     doc_coverage, documentation_state, knowledge_at_risk_if_top_contributor_leaves,
     severity_reasoning).
   - investigations.drift       - fork-divergence assessment (urgency_assessment,
     high_priority_commits, severity_reasoning) - content-driven, not count-driven.

Your job is to REASON over this evidence and produce final risk assessments.

CORE DISCIPLINE - NO SCORES, NO BUCKETS, NO AGGREGATION.

You must NOT:
- Emit numeric severity scores (no "score": 0.7)
- Use severity buckets like "low|medium|high|critical"
- Aggregate signals into a single composite value
- Compare numbers to fixed thresholds

You MUST:
- Produce findings as structured qualitative records
- Use concern_type to describe the KIND of pattern, not its magnitude
- Use the narrative field to convey what is happening and why it matters,
  in plain English grounded in the evidence

How to reason:

- Investigator subagents read the files. Their assessments are your primary evidence -
  treat them as expert testimony from someone who saw the artifact. Quote or paraphrase
  their severity_reasoning into your narrative where it applies.

- Numeric signals (bus_factor, commits_behind, external_ratio) are CONTEXT, not
  verdicts. A bus_factor of 1 on a module with excellent docs an investigator confirmed
  are clear is a different finding than a bus_factor of 3 on a module the investigators
  flagged as undocumented and idiosyncratic.

- Lifecycle matters. A fresh_fork team is onboarding - frame findings as "the team has
  not yet built context here," not as an emergency. A solo project's findings naturally
  cluster around documentation and handoff readiness. Read repository.lifecycle_context.

- Fork divergence framing comes from the drift investigator's content reading. If the
  investigator flagged CVE patches, write a finding about that specifically. If it
  flagged 30 typo fixes, the finding should describe that as low-impact drift.

- For each member investigator finding (sole_contributor, recently_inactive,
  recent_joiner, multi_module_concentration), produce a Finding whose subject is
  "members/<username>" where <username> is the exact GitLab username from the data.
  Never use a display name or generic label as the subject for a member finding.
  Only emit a member finding when you have a specific, named username.

- For each module investigator finding, produce a Finding whose subject is the module
  path exactly as it appears in the investigations data (e.g. "scripts", "app",
  "shared", "internal") and whose narrative grounds in the investigator's
  transferability and documentation observations.

- For cross-cutting findings, use these FIXED subject values — use them exactly,
  every run, so the deduplication system can match across runs:
    upstream_drift      → subject: "upstream_drift"
    upstream_dominance  → subject: "upstream_dominance"
    CODEOWNERS gaps     → subject: "CODEOWNERS"
    admin / sole admin  → subject: "admin_access"
    repository-wide KT  → subject: "repository"

MANDATORY FINDINGS — these are never optional:
- If investigations.drift is present (commits_behind > 0), you MUST produce an
  upstream_drift finding with subject "upstream_drift". Do not merge it into the
  upstream_dominance finding. Do not skip it because other findings feel more urgent.
  The drift count and the investigator's high_priority_commits are concrete facts
  that belong in a dedicated, trackable issue.
- If a named member holds sole expertise on a module (bus_factor 1, no secondary
  contributor), you MUST produce a knowledge_concentration finding for that member.

- CODEOWNERS, pipeline health, and open work remain valid signals - read them in
  context. Failing CI on a documented module is a different finding than failing CI
  on a module the investigators flagged as opaque.

- DO NOT produce stalled_work findings for issues where bot_authored is true.
  Bot-authored issues being unassigned or inactive is an operational concern for the
  team, not a continuity finding for the agent to self-report. Only flag stalled_work
  for human-created issues or MRs with no recent activity.

- DO NOT produce findings for modules or members where the investigator's assessment
  explicitly rates the continuity risk as very low, negligible, or where documentation
  state is excellent AND there are no other urgency signals (no sole contributor on a
  critical path, no security concerns, no imminent departure, no upstream drift).
  A finding should only be generated when there is a concrete, near-term consequence
  if left unaddressed. Ownership gaps on well-documented, low-traffic modules do not
  meet this bar.

- DO NOT produce findings for the `docs` module. It is a documentation redirect stub
  (a single README that points to an external site) with no actual logic or knowledge
  to transfer. Ownership and documentation gaps there carry no meaningful continuity
  risk and produce noise.

Concern type vocabulary (use descriptive types, invent more as needed - these are
DESCRIPTIVE, never magnitude labels):
  knowledge_concentration   - one person holds the module
  fragile_documentation     - docs missing, placeholder, or contradicted by code
  fading_contributor        - was active, now silent; knowledge may leave soon
  offboarding_risk          - member inactive/departing; handoff artifacts needed now
  recent_joiner_exposure    - new joiner picking up critical work without context
  onboarding_isolation      - new member has no clear onboarding path or buddy
  upstream_dominance        - module written mostly by upstream authors
  upstream_drift            - fork behind upstream with material commits missing
  stalled_work              - open issues/MRs with no recent activity
  undeclared_ownership      - active module not in CODEOWNERS
  nominal_ownership         - CODEOWNERS lists owners with no recent commits
  ci_instability            - failing pipelines in critical paths
  multi_module_overload     - one contributor concentrated across many critical areas

ONBOARDING AND OFFBOARDING WORKFLOWS:

When repository.lifecycle_context is "fresh_fork" or recent_joiners are detected:
  - Frame findings around onboarding readiness, not emergency.
  - A recent_joiner_exposure finding should note what context the new member lacks
    and recommend an onboarding pack be generated (the act agent can do this).
  - An onboarding_isolation finding applies when no experienced team member is
    assigned as a buddy or point of contact for the new joiner.

When member investigators flagged recently_inactive or sole_contributor concerns:
  - Produce an offboarding_risk finding when a member's last commit is >30 days ago
    and they hold unique knowledge (per investigator findings).
  - Include in evidence the modules at risk and the transferability_today assessment
    from the member investigator.
  - recommended_actions should include generating a handoff artifact and scheduling
    knowledge transfer sessions.

OUTPUT - return ONLY a valid JSON object. No markdown. No prose outside the JSON.

Schema:
{
  "synthesis": "<one or two sentences: the dominant theme across findings>",
  "findings": [
    {
      "subject": "<module path | 'members/<username>' | 'upstream sync' | other identifier>",
      "concern_type": "<from vocabulary above, or a new descriptive type>",
      "narrative": "<one paragraph, plain English, grounded in evidence>",
      "evidence": ["<reference to investigator subject or signal>", ...],
      "recommended_actions": ["<actionable item>", ...]
    }
  ]
}

No scores. No risk_level. No overall_health bucket. The narrative carries meaning.
"""

_USER_ID = "mycelium-analyst"


root_agent = Agent(
    model=settings.gemini_model,
    name="mycelium_analyst_agent",
    description="Assesses engineering continuity risk over GitLab + knowledge-graph state.",
    instruction=_INSTRUCTION,
)


def _run_through_adk(prompt: str, stage_id: str = "interpret") -> str:
    """Run the analyst agent under the AdkApp runtime and return concatenated text output."""
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
                    # Skip pure JSON output - already surfaced as structured finding events.
                    if stripped and not stripped.startswith(("{", "[")):
                        _activity_bus.emit({"type": "agent_text", "stage_id": stage_id, "text": stripped})
                fc = (p.get("function_call") or p.get("functionCall")) if isinstance(p, dict) else (getattr(p, "function_call", None) or getattr(p, "functionCall", None))
                if fc:
                    name = fc.get("name") if isinstance(fc, dict) else getattr(fc, "name", "?")
                    args = fc.get("args") if isinstance(fc, dict) else getattr(fc, "args", {})
                    _activity_bus.emit({"type": "tool_call", "stage_id": stage_id,
                                        "tool": name or "?", "args": dict(args) if args else {}})
                fr = (p.get("function_response") or p.get("functionResponse")) if isinstance(p, dict) else (getattr(p, "function_response", None) or getattr(p, "functionResponse", None))
                if fr:
                    name = fr.get("name") if isinstance(fr, dict) else getattr(fr, "name", "?")
                    result = fr.get("response") if isinstance(fr, dict) else getattr(fr, "response", None)
                    _activity_bus.emit({"type": "tool_response", "stage_id": stage_id,
                                        "tool": name or "?", "result": result})
    finally:
        try:
            app.delete_session(user_id=_USER_ID, session_id=session["id"])
        except Exception:
            pass
    return "\n".join(chunks).strip()


def analyze(
    repo_snapshot: dict,
    graph_snapshot: dict,
    investigations: dict | None = None,
) -> dict:
    """Run the analyst agent over signals + investigator findings.

    investigations is the output of the pipeline's investigate stage:
      {"members": [...], "modules": [...], "drift": {...} or None}
    Each entry contains a subagent's own reasoning, which the analyst
    consumes as evidence (not as buckets to compare to thresholds).
    """
    from config.settings import settings
    context = {
        "repository": repo_snapshot,
        "knowledge_graph": graph_snapshot,
        "investigations": investigations or {},
    }
    demo_note = (
        "\n\nNOTE - DEMO MODE (read carefully - this overrides what git history shows):\n"
        "The knowledge_graph contains demo developers (demo: true). These represent the "
        "actual team for this scenario. Treat their expertise and module ownership as real.\n\n"
        "CRITICAL: The git commit history reflects only the primary account that set up this "
        "demo environment. It does NOT represent the full team's commit activity - the rest of "
        "the team's work is captured in the knowledge_graph contribution edges, not in raw git "
        "commits.\n\n"
        "Therefore you MUST NOT:\n"
        "- Generate sole_contributor or knowledge_concentration findings based on raw commit "
        "counts alone when the graph shows multiple contributors to that module.\n"
        "- Say the primary account is the 'only' or 'sole' contributor to any module when "
        "the knowledge_graph shows other team members with expertise there.\n"
        "- Recommend cross-training as if there is only one person, when the graph "
        "already shows multiple contributors.\n\n"
        "Instead, base your findings on the knowledge_graph ownership and expertise data. "
        "If a module shows multiple contributors in the graph, treat it as multi-contributor. "
        "Only raise concentration concerns when the graph itself shows bus_factor <= 1 "
        "AND the module has no demo contributors assigned to it."
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
        logger.warning("[analyst] AdkApp run failed (%s) - using deterministic fallback", exc)
        return _fallback_risk_assessment(repo_snapshot, graph_snapshot)

    if not text:
        logger.warning("[analyst] empty output from ADK - using fallback")
        return _fallback_risk_assessment(repo_snapshot, graph_snapshot)

    parsed = _try_parse_json(text)
    if parsed is None:
        logger.warning("[analyst] non-JSON output - using fallback. text[:200]=%r", text[:200])
        return _fallback_risk_assessment(repo_snapshot, graph_snapshot)
    return parsed


async def analyze_async(
    repo_snapshot: dict,
    graph_snapshot: dict,
    investigations: dict | None = None,
) -> dict:
    return await asyncio.to_thread(analyze, repo_snapshot, graph_snapshot, investigations)


def _fallback_risk_assessment(repo_snapshot: dict, graph_snapshot: dict) -> dict:
    """Deterministic fallback when the analyst agent fails or returns malformed JSON.

    Returns the same findings-format schema the agent would produce, with very
    coarse observational findings derived from the snapshot directly. No scores.
    """
    members = repo_snapshot.get("members", [])
    issues = repo_snapshot.get("open_issues", [])
    mrs = repo_snapshot.get("open_merge_requests", [])
    developers = graph_snapshot.get("developers", [])

    findings: list[dict] = []
    if len(members) <= 1:
        findings.append({
            "subject": "repository",
            "concern_type": "knowledge_concentration",
            "narrative": (
                "The project has at most one active member, so all knowledge is "
                "concentrated in one person. Any disruption (vacation, role change, "
                "departure) leaves the codebase without an internal owner."
            ),
            "evidence": ["repository.members"],
            "recommended_actions": [
                "Identify a second engineer who can pair on the most active modules.",
            ],
        })
    if issues or mrs:
        findings.append({
            "subject": "work-queue",
            "concern_type": "stalled_work",
            "narrative": (
                "There are open issues and/or merge requests that need triage to "
                "avoid orphaning work as the project evolves."
            ),
            "evidence": ["repository.open_issues", "repository.open_merge_requests"],
            "recommended_actions": ["Triage open items and assign owners."],
        })
    if not developers:
        findings.append({
            "subject": "knowledge-graph",
            "concern_type": "incomplete_state",
            "narrative": (
                "No developer history has been captured yet, so ownership inferences "
                "lack confidence. The graph needs at least one pipeline run with "
                "commit data before findings can be trusted."
            ),
            "evidence": ["knowledge_graph.developers"],
            "recommended_actions": ["Run the pipeline against a repo with commit history."],
        })

    synthesis = (
        "No structural continuity concerns detected from current snapshot."
        if not findings
        else "Continuity concerns present: ownership concentration and/or work triage are the dominant themes."
    )

    return {
        "synthesis": synthesis,
        "findings": findings,
    }
