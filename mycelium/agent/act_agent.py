"""
Act agent: Gemini + official GitLab MCP (HTTP) + official MongoDB MCP (stdio).

Connects to:
  - GitLab MCP at /api/v4/mcp via streamable-HTTP — write-capable tools only
  - MongoDB MCP via npx stdio subprocess — all tools (find, aggregate, etc.)

Gemini runs a multi-turn loop across both tool sets. MongoDB MCP is non-fatal:
if npx is unavailable, the agent falls back to GitLab MCP alone.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass

import httpx
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from config.settings import settings

logger = logging.getLogger(__name__)

_GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
)
_GEMINI_HEADERS = {"Content-Type": "application/json"}

_GITLAB_MCP_URL = f"{settings.gitlab_url}/api/v4/mcp"
_MCP_TIMEOUT = 60.0

# npx binary name differs on Windows
_NPX = "npx.cmd" if sys.platform == "win32" else "npx"

_PROMPT_TEMPLATE = """\
You are an engineering continuity agent with access to GitLab action tools and \
MongoDB knowledge graph query tools.

Steps:
1. Query the MongoDB knowledge graph (find, aggregate) for context on flagged modules
2. Take the minimum necessary corrective actions via GitLab tools (HIGH/CRITICAL risks only)
3. Do not create duplicate issues — check existing repo state first
4. Keep issue titles and descriptions concise and actionable
5. Stop calling tools when done

Risk Assessment:
{risks}

Current Repository State:
{repo}
"""

_READ_PREFIXES = ("list_", "get_", "search_", "show_", "describe_", "fetch_")


def _is_write_tool(tool_name: str) -> bool:
    return not any(tool_name.startswith(p) for p in _READ_PREFIXES)


# ---------------------------------------------------------------------------
# Tool registry — maps tool name to its MCP session
# ---------------------------------------------------------------------------

@dataclass
class _ToolEntry:
    declaration: dict
    session: ClientSession


def _mcp_tool_to_gemini(tool) -> dict:
    schema = tool.inputSchema or {}
    params: dict = {}
    if schema.get("properties"):
        params = {
            "type": "OBJECT",
            "properties": {k: _convert_schema_type(v) for k, v in schema["properties"].items()},
        }
        if schema.get("required"):
            params["required"] = schema["required"]
    return {
        "name": tool.name,
        "description": tool.description or "",
        "parameters": params,
    }


def _convert_schema_type(prop: dict) -> dict:
    type_map = {
        "string": "STRING", "integer": "INTEGER", "number": "NUMBER",
        "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT",
    }
    result = dict(prop)
    if "type" in result:
        result["type"] = type_map.get(result["type"], result["type"].upper())
    if "items" in result:
        result["items"] = _convert_schema_type(result["items"])
    return result


async def _build_registry(
    gl_session: ClientSession,
    mg_session: ClientSession | None,
) -> dict[str, _ToolEntry]:
    """Merge tools from GitLab MCP (write only) and MongoDB MCP (all)."""
    registry: dict[str, _ToolEntry] = {}

    try:
        gl_tools = await gl_session.list_tools()
        for t in gl_tools.tools:
            if _is_write_tool(t.name):
                registry[t.name] = _ToolEntry(_mcp_tool_to_gemini(t), gl_session)
        logger.info(
            "[act_agent] GitLab MCP: %d write tools: %s",
            len(registry), list(registry.keys()),
        )
    except Exception as exc:
        logger.warning("[act_agent] GitLab MCP list_tools failed: %s", exc)

    if mg_session is not None:
        try:
            mg_tools = await mg_session.list_tools()
            mg_count = 0
            for t in mg_tools.tools:
                registry[t.name] = _ToolEntry(_mcp_tool_to_gemini(t), mg_session)
                mg_count += 1
            logger.info("[act_agent] MongoDB MCP: %d tools added", mg_count)
        except Exception as exc:
            logger.warning("[act_agent] MongoDB MCP list_tools failed: %s", exc)

    return registry


# ---------------------------------------------------------------------------
# Gemini HTTP with exponential backoff
# ---------------------------------------------------------------------------

async def _post_gemini(http: httpx.AsyncClient, body: dict, max_retries: int = 3) -> dict:
    waits = [5, 15, 40]
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = await http.post(_GEMINI_URL, headers=_GEMINI_HEADERS, json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            status = exc.response.status_code
            logger.warning("[act_agent] Gemini %d on attempt %d/%d", status, attempt + 1, max_retries)
            if status not in (429, 500, 502, 503) or attempt == max_retries - 1:
                break
            wait = waits[min(attempt, len(waits) - 1)]
            logger.info("[act_agent] Waiting %ds before retry…", wait)
            await asyncio.sleep(wait)
        except httpx.RequestError as exc:
            last_exc = exc
            logger.warning("[act_agent] Connection error on attempt %d/%d: %s", attempt + 1, max_retries, exc)
            break
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Multi-turn Gemini + MCP loop
# ---------------------------------------------------------------------------

async def _run_mcp_loop(
    prompt: str,
    registry: dict[str, _ToolEntry],
    max_turns: int = 10,
) -> list[dict]:
    if not registry:
        logger.warning("[act_agent] No tools in registry — skipping execution")
        return []

    declarations = [entry.declaration for entry in registry.values()]
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    tool_calls: list[dict] = []

    async with httpx.AsyncClient(timeout=_MCP_TIMEOUT) as http:
        for turn in range(max_turns):
            body = {
                "contents": contents,
                "tools": [{"functionDeclarations": declarations}],
                "generationConfig": {"temperature": 0.2},
            }
            try:
                data = await _post_gemini(http, body)
            except Exception as exc:
                logger.warning("[act_agent] Gemini call failed on turn %d, stopping: %s", turn, exc)
                break

            candidate = data["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            contents.append({"role": "model", "parts": parts})

            fc_parts = [p for p in parts if "functionCall" in p]
            if not fc_parts:
                logger.debug("[act_agent] Model finished after %d turn(s)", turn + 1)
                break

            function_responses = []
            for fc_part in fc_parts:
                fc = fc_part["functionCall"]
                name = fc["name"]
                args = fc.get("args") or {}
                logger.info("[mcp_tool] %s(%s)", name, list(args.keys()))

                entry = registry.get(name)
                if entry is None:
                    logger.error("[act_agent] Unknown tool %s — skipping", name)
                    result_dict = {"error": f"Unknown tool: {name}"}
                else:
                    try:
                        mcp_result = await entry.session.call_tool(name, args)
                        raw = mcp_result.content[0].text if mcp_result.content else "{}"
                        try:
                            result_dict = json.loads(raw)
                        except json.JSONDecodeError:
                            result_dict = {"raw": raw}
                    except Exception as exc:
                        logger.error("[act_agent] MCP tool %s failed: %s", name, exc)
                        result_dict = {"error": str(exc)}

                tool_calls.append({"tool": name, "args": args, "result": result_dict})
                function_responses.append({
                    "functionResponse": {
                        "name": name,
                        "response": {"result": result_dict},
                    }
                })

            contents.append({"role": "user", "parts": function_responses})

    return tool_calls


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def act(risks: dict, repo_snapshot: dict) -> dict:
    """
    Run the act agent via official GitLab MCP (HTTP) + MongoDB MCP (stdio).
    MongoDB MCP is non-fatal: falls back to GitLab-only if npx is unavailable.
    """
    prompt = _PROMPT_TEMPLATE.format(
        risks=json.dumps(risks, indent=2, default=str),
        repo=json.dumps(repo_snapshot, indent=2, default=str),
    )

    gl_headers = {"Authorization": f"Bearer {settings.gitlab_token}"}
    mg_env = dict(os.environ)
    mg_env["MDB_MCP_CONNECTION_STRING"] = settings.mongodb_uri
    mg_params = StdioServerParameters(
        command=_NPX,
        args=["-y", "@mongodb-js/mongodb-mcp-server"],
        env=mg_env,
    )

    tool_calls: list[dict] = []
    try:
        async with streamablehttp_client(
            _GITLAB_MCP_URL,
            headers=gl_headers,
            timeout=_MCP_TIMEOUT,
        ) as (gl_r, gl_w, _):
            async with ClientSession(gl_r, gl_w) as gl_session:
                await gl_session.initialize()

                try:
                    async with stdio_client(mg_params) as (mg_r, mg_w):
                        async with ClientSession(mg_r, mg_w) as mg_session:
                            await mg_session.initialize()
                            registry = await _build_registry(gl_session, mg_session)
                            tool_calls = await _run_mcp_loop(prompt, registry)
                except Exception as exc:
                    logger.warning(
                        "[act_agent] MongoDB MCP unavailable (%s) — running GitLab MCP only", exc,
                    )
                    registry = await _build_registry(gl_session, None)
                    tool_calls = await _run_mcp_loop(prompt, registry)

    except Exception as exc:
        # Unwrap anyio / Python 3.11+ ExceptionGroup so the real cause is visible.
        inner = getattr(exc, "exceptions", None)
        if inner:
            for sub in inner:
                logger.error("[act_agent] GitLab MCP inner error: %s — %s", type(sub).__name__, sub)
        logger.error("[act_agent] GitLab MCP session failed (%s): %s", type(exc).__name__, exc)

    executed, failed, details = [], [], []
    for tc in tool_calls:
        name = tc["tool"]
        args = tc["args"]
        result = tc["result"]
        if "error" in result:
            failed.append({"tool": name, "error": result["error"]})
            logger.error("[act_agent] %s failed: %s", name, result["error"])
        else:
            executed.append(tc)
            iid = result.get("iid") or result.get("id")
            title = args.get("title") or args.get("body", "")[:60]
            details.append({"kind": name, "detail": f"#{iid} {title}".strip() if iid else title})

    return {
        "executed": len(executed),
        "failed": len(failed),
        "details": details,
        "mcp_calls": [{"tool": tc["tool"], "args": list(tc["args"].keys())} for tc in tool_calls],
    }
