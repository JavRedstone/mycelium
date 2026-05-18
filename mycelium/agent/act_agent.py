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

from config.settings import settings

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

Execution loop:
1. Call get_gitlab_project_state to get the current issues list (duplicate check).
2. For each action in the PLAN:
   - create_issue: call Mycelium MCP create_issue unless exact title exists.
   - add_comment / assign_issue: execute directly via Mycelium MCP.
   - generate_onboarding_pack / generate_offboarding_artifact: call Mycelium MCP.
3. Stop after executing all planned actions.
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
- Execute every planned action using Mycelium MCP tools (pre-scoped to the authorized project).
- When using GitLab MCP tools, ALWAYS pass project_path="{project_path}".
- Do NOT write to any other project — upstream/parent repos are outside your authority.
- Do NOT skip actions unless a tool call explicitly fails.
- Do NOT ask for confirmation — execute autonomously.
- Stop after executing all planned actions.
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


def _collect_tool_calls(event: dict, sink: list[dict]) -> None:
    """Pull function_call / function_response pairs out of an AdkApp stream event."""
    content = event.get("content") or {}
    parts = content.get("parts") or []
    for part in parts:
        fc = part.get("function_call") or part.get("functionCall")
        if fc:
            sink.append({
                "tool": fc.get("name"),
                "args": fc.get("args") or {},
                "result": None,
            })
        fr = part.get("function_response") or part.get("functionResponse")
        if fr:
            # Pair the response with the most recent unmatched call of the same name.
            name = fr.get("name")
            response = fr.get("response") or {}
            for entry in reversed(sink):
                if entry["tool"] == name and entry["result"] is None:
                    entry["result"] = response
                    break


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

    prompt = _PROMPT_TEMPLATE.format(
        project_id=authorized_id,
        project_path=authorized_path,
        interpretation=json.dumps(interpretation, indent=2, default=str),
        plan=json.dumps(plan or {}, indent=2, default=str),
        repo=json.dumps(repo_snapshot, indent=2, default=str),
    )

    app = AdkApp(agent=root_agent)

    tool_calls: list[dict] = []
    final_text_parts: list[str] = []

    def _drain_stream() -> None:
        session = app.create_session(user_id=_USER_ID)
        try:
            for event in app.stream_query(
                user_id=_USER_ID,
                session_id=session["id"],
                message=prompt,
            ):
                if isinstance(event, dict):
                    _collect_tool_calls(event, tool_calls)
                    parts = (event.get("content") or {}).get("parts") or []
                    for p in parts:
                        text = p.get("text")
                        if text:
                            final_text_parts.append(text)
        finally:
            try:
                app.delete_session(user_id=_USER_ID, session_id=session["id"])
            except Exception:
                pass  # session cleanup is best-effort

    try:
        # stream_query is synchronous; run it off the event loop so SSE keeps flowing.
        await asyncio.to_thread(_drain_stream)
    except Exception as exc:
        logger.exception("[act_agent] AdkApp run failed: %s", exc)

    # --- Ownership boundary audit -------------------------------------------
    # Check every tool call for cross-project writes before processing results.
    # This is a defence-in-depth layer: violations should already be prevented by
    # instruction-level constraints, but we log them critically if they slip through.
    violations = _audit_boundary(tool_calls, authorized_id, authorized_path)
    for v in violations:
        logger.critical("[act_agent] OWNERSHIP BOUNDARY VIOLATION: %s", v)
    # ------------------------------------------------------------------------

    executed: list[dict] = []
    failed: list[dict] = []
    details: list[dict] = []
    for tc in tool_calls:
        name = tc.get("tool") or "?"
        args = tc.get("args") or {}
        result = tc.get("result") or {}
        # MCP tool errors surface inside response payloads; treat any "error" key as failure.
        err = _extract_error(result)
        if err:
            failed.append({"tool": name, "error": err})
        else:
            executed.append(tc)
            iid = _extract_iid(result)
            title = args.get("title") or (args.get("body") or "")[:60]
            label = f"#{iid} {title}".strip() if iid else title
            details.append({"kind": name, "detail": label})

    summary_text = "\n".join(final_text_parts).strip()
    return {
        "executed": len(executed),
        "failed": len(failed),
        "details": details,
        "mcp_calls": [{"tool": tc.get("tool"), "args": list((tc.get("args") or {}).keys())}
                      for tc in tool_calls],
        "summary": summary_text[:2000] if summary_text else None,
        "boundary_violations": violations,
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
