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

Inputs you receive every turn:
- A continuity INTERPRETATION (qualitative findings with concern_type, narrative,
  evidence, recommended_actions) — there are no scalar risk scores in this system.
- A snapshot of the GitLab repository state.

IMPORTANT CONSTRAINTS:
- The GitLab project is already configured. NEVER ask the user for a project ID,
  URL, or any configuration — all tools have the project pre-wired.
- Do not mention tool errors to the user. If a tool fails, skip that action and
  move on. Do not ask for clarification — decide autonomously.
- Do not invent severity scores or buckets. Reason from the findings' narratives.

You have three tool surfaces:

1. Mycelium MCP tools — use these for ALL reads AND writes:
   READ:  get_concerns, get_module_experts, get_orphaned_modules,
          suggest_assignee, get_gitlab_project_state
   WRITE: create_issue, add_comment, assign_issue
   ARTIFACTS: generate_onboarding_pack(new_member_username),
              generate_offboarding_artifact(departing_member_username)
   These are the primary tools. Use them for all GitLab actions.

   Use generate_onboarding_pack when a finding's concern_type is
   recent_joiner_exposure or onboarding_isolation.
   Use generate_offboarding_artifact when a finding's concern_type is
   fading_contributor, offboarding_risk, or sole_contributor with low
   transferability reported by the investigator.

2. GitLab MCP tools — supplementary only (may be unavailable).
   If Mycelium MCP write tools are available, prefer them over GitLab MCP.

3. MongoDB MCP tools — raw query fallback for custom aggregations.

You receive a continuity INTERPRETATION (findings with concern_type, narrative,
evidence, recommended_actions) — NOT scalar risk scores. Reason about each
finding's narrative directly. The system does not use severity buckets.

Decision loop:
1. Call get_concerns and get_gitlab_project_state to understand the situation.
2. For each finding that warrants action (per its narrative + recommended_actions),
   call get_module_experts and suggest_assignee to identify the right people for
   knowledge transfer.
3. Take the minimum necessary corrective actions using create_issue / add_comment /
   assign_issue, guided by each finding's recommended_actions.
   - Do not duplicate existing issues — check the issues list from get_gitlab_project_state first.
   - Keep issue titles short and descriptions actionable (one paragraph + checklist).
   - At most 2-3 new issues per run to avoid noise.
4. Stop calling tools when the situation has been addressed.
"""

_PROMPT_TEMPLATE = """\
Continuity interpretation (qualitative findings, no scores):
{interpretation}

Current repository snapshot:
{repo}
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
    Build the Mycelium ADK agent with all three MCP toolsets attached.

    Toolset priority:
      1. Mycelium MCP  — typed knowledge graph + GitLab snapshot tools
      2. GitLab MCP    — write tools (create_issue, create_merge_request, …)
      3. MongoDB MCP   — raw query fallback

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


async def act(interpretation: dict, repo_snapshot: dict) -> dict:
    """
    Run one turn of the act agent under the Vertex AI Agent Engine runtime (AdkApp).

    `interpretation` is the analyst's findings output ({"synthesis", "findings"}).
    """
    prompt = _PROMPT_TEMPLATE.format(
        interpretation=json.dumps(interpretation, indent=2, default=str),
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
