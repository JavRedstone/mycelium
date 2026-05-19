"""
Act agent — the autonomous reasoning loop that takes corrective action.

Implements the hackathon's required stack:
    ADK (google.adk.agents.Agent)
        ↓
    Vertex AI Agent Engine runtime (vertexai.preview.reasoning_engines.AdkApp)
        ↓
    Gemini (via Vertex AI, NOT AI Studio)
        ↓
    Two MCP toolsets exposed to the agent simultaneously:
        - Official GitLab MCP server (HTTP / streamable-HTTP) — write tools
        - Official MongoDB MCP server (stdio via `npx`)        — graph queries

Gemini reasons across both tool surfaces in a single multi-turn loop and decides
which GitLab actions to perform based on what it finds in the knowledge graph.
MongoDB MCP is non-fatal: if `npx` or the MongoDB server is unavailable, the agent
falls back to GitLab-only operation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import vertexai
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
)
from mcp.client.stdio import StdioServerParameters
from vertexai.preview.reasoning_engines import AdkApp

from agent.activity_bus import bus as _activity_bus
from config.settings import settings
from connectors.gitlab_client import GitLabClient as _GitLabClient

logger = logging.getLogger(__name__)

# Vertex AI must be initialised before any ADK Agent is created or run.
vertexai.init(
    project=settings.google_cloud_project,
    location=settings.google_cloud_location,
)

_NPX = "npx.cmd" if sys.platform == "win32" else "npx"
_PYTHON = sys.executable
_SERVER_PY = Path(__file__).resolve().parent.parent / "connectors" / "mcp_server.py"
_USER_ID = "mycelium-pipeline"

_AGENT_INSTRUCTION = """\
You are Mycelium, an autonomous engineering continuity agent.

═══════════════════════════════════════════════════════════
AGENT AUTHORITY SCOPE — THIS IS A HARD SAFETY CONSTRAINT
═══════════════════════════════════════════════════════════

You are a CONTAINED ACTOR. You are authorized to act within EXACTLY ONE
GitLab project: the internal fork specified in each prompt's authority scope
block. Your authority is bounded by your organization's continuity domain.

YOU MUST NEVER:
  ✗ Create issues on any upstream or parent repository of your fork
  ✗ Post comments on any project other than your authorized project
  ✗ Take any write action on any GitLab project not matching your project ID/path
  ✗ Use GitLab MCP tools with a project_path or project_id that differs from
    the authorized values in the authority scope block

Upstream repositories:
  ✗ Are OUTSIDE your continuity domain
  ✗ Belong to their maintainers' workflow and decision process
  ✗ Must NEVER receive automated writes from this system
  ✗ Cross-project writes are ownership boundary violations

When using GitLab MCP tools that require a project argument:
  ALWAYS use the project_path from the authority scope block.
  NEVER pass any other project path or ID.

═══════════════════════════════════════════════════════════

Your primary job in each turn is to EXECUTE the planned actions you are given.
The plan has already been decided by the planner — you are the execution layer.

OPERATIONAL CONSTRAINTS:
- Do not mention tool errors to the user. If a tool fails, skip and move on.
- Do not ask for clarification — decide autonomously.
- Do not invent severity scores or buckets. Reason from finding narratives.
- Do NOT skip planned actions unless the exact same issue already exists.

You have three tool surfaces:

1. Mycelium MCP tools — primary surface for ALL reads AND writes.
   Pre-scoped to the authorized project — no project argument needed.
   READ:  get_concerns, get_module_experts, get_orphaned_modules,
          suggest_assignee, get_gitlab_project_state
   WRITE: create_issue, add_comment, assign_issue
   ARTIFACTS: generate_onboarding_pack(new_member_username),
              generate_offboarding_artifact(departing_member_username)

   Use generate_onboarding_pack when a finding's concern_type is
   recent_joiner_exposure or onboarding_isolation.
   Use generate_offboarding_artifact when a finding's concern_type is
   fading_contributor, offboarding_risk, or sole_contributor with low
   transferability reported by the investigator.

2. GitLab MCP tools — supplementary surface (may be unavailable).
   When using these tools, pass ONLY the authorized project_path from the
   authority scope block. Never pass any other project path.
   Prefer Mycelium MCP write tools when both surfaces are available.

3. MongoDB MCP tools — raw query fallback for custom aggregations only.

Execution loop — follow this EXACTLY:
1. For each action in the PLAN, call the corresponding Mycelium MCP tool IMMEDIATELY:
   - create_issue   → call create_issue with the title and description from the plan
   - add_comment    → call add_comment
   - assign_issue   → call assign_issue
   - generate_onboarding_pack / generate_offboarding_artifact → call Mycelium MCP
2. If a tool call fails, skip that action and proceed to the next.
3. Stop after processing every action in the plan.

CRITICAL — DO NOT:
  ✗ Call get_gitlab_project_state before executing (this causes premature termination)
  ✗ Skip a create_issue because you judge the situation as "already covered"
  ✗ Substitute your own assessment for the planner's decisions
  ✗ Confuse the TOPIC of an issue (which may reference an upstream repo) with
    the TARGET of the write — all issues are created IN your authorized project,
    even if their title or description discusses upstream changes
"""

_PROMPT_TEMPLATE = """\
╔══════════════════════════════════════════════════════════╗
║  AGENT AUTHORITY SCOPE — BINDING FOR THIS EXECUTION      ║
╠══════════════════════════════════════════════════════════╣
║  Authorized project ID:   {project_id:<32} ║
║  Authorized project path: {project_path:<32} ║
║                                                          ║
║  ALL GitLab write actions MUST target this project only. ║
║  Any other project_path or project_id = HARD VIOLATION.  ║
╚══════════════════════════════════════════════════════════╝

Continuity interpretation (qualitative findings, no scores):
{interpretation}

Planned actions — execute ALL of these using your MCP tools:
{plan}

Current repository snapshot:
{repo}

EXECUTION INSTRUCTIONS:
1. Call create_issue (Mycelium MCP) for EACH action in the plan above — right now.
2. Issue titles may reference upstream repos (e.g. "javredstone-mcp/gitlab-pages") as
   TOPICS. The write target is always your authorized project. This is NOT a boundary
   violation — you are tracking the topic in your own project's issue tracker.
3. If a tool call fails, skip it and continue to the next action.
4. Do NOT call get_gitlab_project_state first — execute immediately.
5. Do NOT substitute your own assessment for the planner's decisions.
6. When using GitLab MCP tools (if Mycelium MCP is unavailable), pass
   project_path="{project_path}" — never any other project path.
"""


# ---------------------------------------------------------------------------
# Agent construction
# ---------------------------------------------------------------------------

def _gitlab_toolset() -> MCPToolset:
    """Official GitLab MCP server proxied via mcp-remote (stdio transport).

    GitLab MCP uses OAuth 2.0 Dynamic Client Registration — not PAT bearer tokens.
    mcp-remote handles the OAuth handshake and caches the token in ~/.mcp-auth/.
    First run: opens a browser for OAuth authorization (one-time per machine).
    Subsequent runs: reuses the cached OAuth token automatically.

    Requires GitLab Duo (Premium/Ultimate) with beta features enabled.
    See: https://docs.gitlab.com/ee/user/gitlab_duo/mcp/
    """
    env = dict(os.environ)
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=_NPX,
                args=[
                    "-y", "mcp-remote@latest",
                    f"{settings.gitlab_url}/api/v4/mcp",
                ],
                env=env,
            ),
        ),
    )


def _mongodb_toolset() -> MCPToolset:
    """Official MongoDB MCP server via stdio (`npx @mongodb-js/mongodb-mcp-server`)."""
    env = dict(os.environ)
    env["MDB_MCP_CONNECTION_STRING"] = settings.mongodb_uri
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=_NPX,
                args=["-y", "@mongodb-js/mongodb-mcp-server"],
                env=env,
            ),
        ),
    )


def _mycelium_toolset() -> MCPToolset:
    """Custom Mycelium MCP server — typed tools over the knowledge graph + GitLab."""
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=_PYTHON,
                args=[str(_SERVER_PY)],
                env=dict(os.environ),
            ),
        ),
    )


def build_root_agent() -> Agent:
    """
    Build the Mycelium ADK agent with all three MCP toolsets.

    Toolset priority:
      1. Mycelium MCP  — typed knowledge graph + GitLab write tools, pre-scoped to the
                         configured project (settings.gitlab_project_id).
      2. GitLab MCP    — official GitLab MCP via mcp-remote (hackathon partner requirement).
                         Has broad project access; constrained to the authorized project
                         via instruction-level boundaries + post-hoc audit in act().
      3. MongoDB MCP   — raw query fallback for custom aggregations.

    SAFETY NOTE — GitLab MCP scope:
    The official GitLab MCP server (mcp-remote) uses OAuth and can operate on any
    project the token has access to, including upstream repositories. This is
    mitigated by:
      (a) Explicit project scope injected into every prompt (project_id + project_path)
      (b) Agent instruction hard-prohibiting cross-project writes
      (c) Post-hoc audit in act() that logs CRITICAL violations
    For all write operations, Mycelium MCP (pre-scoped) is preferred over GitLab MCP.

    This is the agent that gets wrapped in AdkApp for the Vertex AI Agent Engine
    runtime — both for local execution and for deployment to Agent Engine.
    """
    tools: list = []
    try:
        tools.append(_mycelium_toolset())
    except Exception as exc:
        logger.warning(
            "[act_agent] Mycelium MCP toolset construction failed (%s) — "
            "agent will run without Mycelium-specific tools", exc,
        )
    try:
        tools.append(_gitlab_toolset())
    except Exception as exc:
        logger.warning(
            "[act_agent] GitLab MCP toolset construction failed (%s) — "
            "check that GitLab Duo is enabled and GITLAB_TOKEN has the mcp scope", exc,
        )
    try:
        tools.append(_mongodb_toolset())
    except Exception as exc:
        logger.warning(
            "[act_agent] MongoDB MCP toolset construction failed (%s) — "
            "agent will run without raw MongoDB tools", exc,
        )

    return Agent(
        model=settings.gemini_model,
        name="mycelium_act_agent",
        description="Continuity agent that queries the knowledge graph and "
                    "takes corrective action in GitLab.",
        instruction=_AGENT_INSTRUCTION,
        tools=tools,
    )


# `root_agent` is the canonical name expected by ADK deployment tooling.
# Re-exported for ADK discovery; actual per-call execution uses a fresh agent.
root_agent = build_root_agent()


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Ownership boundary enforcement
# ---------------------------------------------------------------------------

# Argument keys that GitLab MCP tools use to identify a target project.
_PROJECT_ARG_KEYS = frozenset({
    "project_path", "project_id", "namespace", "project",
    "project_name", "repo_path", "repository",
})


def _audit_boundary(
    tool_calls: list[dict],
    authorized_id: int,
    authorized_path: str,
) -> list[str]:
    """Scan completed tool calls for ownership boundary violations.

    A violation is any write-capable GitLab tool call whose project argument
    does not match the authorized project.  Returns a list of violation
    descriptions; an empty list means the boundary was respected.
    """
    violations: list[str] = []
    authorized_path_lower = authorized_path.lower()

    for tc in tool_calls:
        tool_name = (tc.get("tool") or "").lower()
        args = tc.get("args") or {}

        for key, value in args.items():
            if key.lower() not in _PROJECT_ARG_KEYS:
                continue
            if isinstance(value, int):
                if value != authorized_id:
                    violations.append(
                        f"tool={tool_name!r} used project_id={value} "
                        f"(authorized: {authorized_id})"
                    )
            elif isinstance(value, str) and "/" in value:
                if value.lower() != authorized_path_lower:
                    violations.append(
                        f"tool={tool_name!r} used project_path={value!r} "
                        f"(authorized: {authorized_path!r})"
                    )

    return violations


def _field(obj, *keys):
    """Get the first matching field from a dict OR a Pydantic/proto object.

    ADK stream_query may yield plain dicts OR Pydantic model instances depending
    on the event type — MCP tool-call events often arrive as model objects.
    """
    for key in keys:
        val = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
        if val is not None:
            return val
    return None


def _parts(event) -> list:
    """Extract content.parts from a stream event (dict or object)."""
    content = _field(event, "content")
    if content is None:
        return []
    parts = _field(content, "parts")
    return list(parts) if parts else []


def _to_dict(obj) -> dict:
    """Best-effort conversion of a Pydantic/proto/mapping object to a plain dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return vars(obj)
    try:
        return dict(obj)
    except Exception:
        return {}


def _collect_tool_calls(event, sink: list[dict]) -> None:
    """Pull function_call / function_response pairs out of an AdkApp stream event.

    Handles both plain-dict events (analyst/planner) and Pydantic/proto-object
    events (act agent with MCP tools).
    """
    for part in _parts(event):
        fc = _field(part, "function_call", "functionCall")
        if fc:
            args = _field(fc, "args") or {}
            if not isinstance(args, dict):
                try:
                    args = dict(args)
                except Exception:
                    args = {}
            sink.append({
                "tool": _field(fc, "name"),
                "args": args,
                "result": None,
            })
        fr = _field(part, "function_response", "functionResponse")
        if fr:
            name = _field(fr, "name")
            response = _field(fr, "response") or {}
            for entry in reversed(sink):
                if entry["tool"] == name and entry["result"] is None:
                    entry["result"] = response
                    break


def _collect_trace(event, sink: list[dict]) -> None:
    """Build an ordered agent conversation trace from a stream event.

    Produces entries with a 'type' discriminant:
      {"type": "agent_text",     "text": str}
      {"type": "tool_call",      "tool": str, "args": dict}
      {"type": "tool_response",  "tool": str, "result": any}
    """
    for part in _parts(event):
        text = _field(part, "text")
        if text:
            text = str(text).strip()
            if text:
                if sink and sink[-1].get("type") == "agent_text":
                    sink[-1]["text"] = sink[-1]["text"] + "\n" + text
                else:
                    sink.append({"type": "agent_text", "text": text})

        fc = _field(part, "function_call", "functionCall")
        if fc:
            args = _field(fc, "args") or {}
            if not isinstance(args, dict):
                try:
                    args = dict(args)
                except Exception:
                    args = {}
            sink.append({
                "type": "tool_call",
                "tool": _field(fc, "name"),
                "args": args,
            })

        fr = _field(part, "function_response", "functionResponse")
        if fr:
            sink.append({
                "type": "tool_response",
                "tool": _field(fr, "name"),
                "result": _field(fr, "response"),
            })


async def _direct_execute_actions(
    actions: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Execute planned actions directly via Python — bypasses the ADK tool loop.

    Used as a reliable fallback when the ADK stream produces no tool calls.
    Emits the same tool_call / tool_response events to the activity bus so the
    UI sees them identically to agent-driven execution.
    """
    executed: list[dict] = []
    failed: list[dict] = []
    details: list[dict] = []

    async def _create_issue(params: dict) -> dict:
        def _run() -> dict:
            return _GitLabClient().create_issue(
                title=params.get("title", ""),
                description=params.get("description", ""),
                labels=params.get("labels") or None,
                assignee_username=params.get("assignee_username") or None,
            )
        return await asyncio.to_thread(_run)

    async def _add_comment(params: dict) -> dict:
        def _run() -> dict:
            client = _GitLabClient()
            kind = params.get("kind", "issue")
            iid = int(params.get("iid", 0))
            body = params.get("body", "")
            if kind == "mr":
                return client.comment_on_mr(mr_iid=iid, body=body)
            return client.comment_on_issue(issue_iid=iid, body=body)
        return await asyncio.to_thread(_run)

    async def _assign_issue(params: dict) -> dict:
        def _run() -> dict:
            return _GitLabClient().assign_issue(
                issue_iid=int(params.get("iid", 0)),
                assignee_username=params.get("assignee_username", ""),
            )
        return await asyncio.to_thread(_run)

    async def _onboarding_pack(params: dict) -> dict:
        from connectors.mcp_server import generate_onboarding_pack
        username = params.get("new_member_username") or params.get("username", "")
        return await generate_onboarding_pack(username)

    async def _offboarding_artifact(params: dict) -> dict:
        from connectors.mcp_server import generate_offboarding_artifact
        username = params.get("departing_member_username") or params.get("username", "")
        return await generate_offboarding_artifact(username)

    HANDLERS: dict = {
        "create_issue":               _create_issue,
        "add_comment":                _add_comment,
        "assign_issue":               _assign_issue,
        "generate_onboarding_pack":   _onboarding_pack,
        "generate_offboarding_artifact": _offboarding_artifact,
    }

    for action in actions:
        kind = action.get("kind", "")
        params = action.get("params", {})
        handler = HANDLERS.get(kind)
        if not handler:
            logger.warning("[act_agent] unknown action kind %r — skipping", kind)
            continue

        _activity_bus.emit({"type": "tool_call", "stage_id": "act", "tool": kind, "args": params})
        try:
            result = await handler(params)
            err = _extract_error(result)
            if err:
                failed.append({"tool": kind, "error": err})
                _activity_bus.emit({"type": "tool_response", "stage_id": "act", "tool": kind, "result": {"error": err}})
                logger.warning("[act_agent] direct %r failed: %s", kind, err)
            else:
                executed.append({"tool": kind, "args": params, "result": result})
                iid = _extract_iid(result)
                title = params.get("title", kind)
                label = (f"#{iid} " if iid else "") + title
                details.append({"kind": kind, "detail": label})
                _activity_bus.emit({"type": "tool_response", "stage_id": "act", "tool": kind, "result": result})
                logger.info("[act_agent] direct %r → %s", kind, label)
        except Exception as exc:
            logger.error("[act_agent] direct %r raised: %s", kind, exc)
            failed.append({"tool": kind, "error": str(exc)})
            _activity_bus.emit({"type": "tool_response", "stage_id": "act", "tool": kind,
                                "result": {"error": str(exc)}})

    return executed, failed, details


async def act(interpretation: dict, repo_snapshot: dict, plan: dict | None = None) -> dict:
    """
    Run one turn of the act agent under the Vertex AI Agent Engine runtime (AdkApp).

    `interpretation` is the analyst's findings output ({"synthesis", "findings"}).
    `plan` is the planner's output ({"actions": [...], "graph_updates": [...]}).

    The authorized project scope is derived from repo_snapshot so that the agent
    receives the exact project_id / project_path it is permitted to act on in
    every prompt turn — preventing drift toward upstream project writes.
    """
    authorized_id: int = int(repo_snapshot.get("project_id") or settings.gitlab_project_id)
    authorized_path: str = str(repo_snapshot.get("project_path") or authorized_id)

    actions = (plan or {}).get("actions", [])
    logger.info("[act_agent] starting — %d planned actions, project=%s", len(actions), authorized_path)

    prompt = _PROMPT_TEMPLATE.format(
        project_id=authorized_id,
        project_path=authorized_path,
        interpretation=json.dumps(interpretation, indent=2, default=str),
        plan=json.dumps(plan or {}, indent=2, default=str),
        repo=json.dumps(repo_snapshot, indent=2, default=str),
    )

    # Build a fresh agent per call so MCP stdio connections are never stale.
    agent = build_root_agent()
    app = AdkApp(agent=agent)

    tool_calls: list[dict] = []
    trace: list[dict] = []
    final_text_parts: list[str] = []

    def _drain_stream() -> None:
        session = app.create_session(user_id=_USER_ID)
        try:
            for event in app.stream_query(
                user_id=_USER_ID,
                session_id=session["id"],
                message=prompt,
            ):
                # ADK may yield plain dicts OR Pydantic model instances.
                # _collect_tool_calls/_collect_trace handle both via _field()/_parts().
                try:
                    _collect_tool_calls(event, tool_calls)
                    prev_len = len(trace)
                    _collect_trace(event, trace)
                    for entry in trace[prev_len:]:
                        _activity_bus.emit({**entry, "stage_id": "act"})
                    for p in _parts(event):
                        text = _field(p, "text")
                        if text:
                            final_text_parts.append(str(text))
                except Exception as parse_exc:
                    logger.debug("[act_agent] event parse error (type=%s): %s",
                                 type(event).__name__, parse_exc)
        finally:
            logger.info("[act_agent] stream done — %d tool_calls captured, %d trace entries",
                        len(tool_calls), len(trace))
            try:
                app.delete_session(user_id=_USER_ID, session_id=session["id"])
            except Exception:
                pass  # session cleanup is best-effort

    try:
        # stream_query is synchronous; run it off the event loop so SSE keeps flowing.
        await asyncio.to_thread(_drain_stream)
    except Exception as exc:
        logger.exception("[act_agent] AdkApp run failed: %s", exc)
        _activity_bus.emit({"type": "agent_text", "stage_id": "act",
                            "text": f"Act agent error — check server logs: {exc}"})

    # --- Ownership boundary audit -------------------------------------------
    violations = _audit_boundary(tool_calls, authorized_id, authorized_path)
    for v in violations:
        logger.critical("[act_agent] OWNERSHIP BOUNDARY VIOLATION: %s", v)
    # ------------------------------------------------------------------------

    # Process any tool calls the ADK stream captured.
    executed: list[dict] = []
    failed: list[dict] = []
    details: list[dict] = []
    for tc in tool_calls:
        name = tc.get("tool") or "?"
        args = tc.get("args") or {}
        result = tc.get("result") or {}
        err = _extract_error(result)
        if err:
            failed.append({"tool": name, "error": err})
        else:
            executed.append(tc)
            iid = _extract_iid(result)
            title = args.get("title") or (args.get("body") or "")[:60]
            label = f"#{iid} {title}".strip() if iid else title
            details.append({"kind": name, "detail": label})

    # If the ADK stream produced no tool calls, execute the plan directly.
    # This is the reliable fallback: Gemini reasons (text above) but we act
    # deterministically from the structured plan rather than waiting for the
    # agent to invoke tools through the MCP loop.
    if not tool_calls and actions:
        logger.info("[act_agent] ADK produced 0 tool calls — executing %d planned actions directly",
                    len(actions))
        _activity_bus.emit({
            "type": "agent_text", "stage_id": "act",
            "text": f"Executing {len(actions)} planned action(s) directly…",
        })
        direct_executed, direct_failed, direct_details = await _direct_execute_actions(actions)
        executed.extend(direct_executed)
        failed.extend(direct_failed)
        details.extend(direct_details)

    summary_text = "\n".join(final_text_parts).strip()
    return {
        "executed": len(executed),
        "failed": len(failed),
        "details": details,
        "mcp_calls": [{"tool": tc.get("tool"), "args": list((tc.get("args") or {}).keys())}
                      for tc in tool_calls],
        "summary": summary_text[:2000] if summary_text else None,
        "boundary_violations": violations,
        "trace": trace,
    }


def _extract_error(payload: dict | list | str | None) -> str | None:
    if not payload:
        return None
    if isinstance(payload, dict):
        if "error" in payload:
            return str(payload["error"])
        for v in payload.values():
            err = _extract_error(v)
            if err:
                return err
    elif isinstance(payload, list):
        for item in payload:
            err = _extract_error(item)
            if err:
                return err
    return None


def _extract_iid(payload: dict | list | str | None) -> str | int | None:
    if isinstance(payload, dict):
        for key in ("iid", "id"):
            if key in payload:
                return payload[key]
        for v in payload.values():
            iid = _extract_iid(v)
            if iid is not None:
                return iid
    elif isinstance(payload, list):
        for item in payload:
            iid = _extract_iid(item)
            if iid is not None:
                return iid
    return None
