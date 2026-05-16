"""
Multi-turn Gemini function-calling loop.

This implements the MCP agentic pattern: Gemini decides which tools to call,
we execute them, feed results back, and repeat until the model stops calling tools.
"""
from __future__ import annotations

import logging
import requests
from config.settings import settings

logger = logging.getLogger(__name__)

_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
)
_HEADERS = {"Content-Type": "application/json"}


def run_with_tools(
    prompt: str,
    tool_declarations: list[dict],
    tool_executor,
    max_turns: int = 8,
) -> tuple[str, list[dict]]:
    """
    Run a multi-turn Gemini function-calling loop.

    Returns (final_text_output, list_of_tool_calls_made).
    Each tool call entry: {"name": str, "args": dict, "result": dict}.
    """
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    tools_called: list[dict] = []

    for turn in range(max_turns):
        body = {
            "contents": contents,
            "tools": [{"functionDeclarations": tool_declarations}],
            "generationConfig": {"temperature": 0.2},
        }
        response = requests.post(_API_URL, headers=_HEADERS, json=body, timeout=60)
        response.raise_for_status()

        data = response.json()
        candidate = data["candidates"][0]
        finish_reason = candidate.get("finishReason")
        if finish_reason not in ("STOP", "MAX_TOKENS", None):
            raise ValueError(f"Gemini finishReason={finish_reason}")

        parts = candidate.get("content", {}).get("parts", [])
        contents.append({"role": "model", "parts": parts})

        fc_parts = [p for p in parts if "functionCall" in p]
        text_parts = [p["text"] for p in parts if "text" in p]

        if not fc_parts:
            # No more tool calls — model is done
            return "\n".join(text_parts), tools_called

        # Execute every function call the model requested
        function_responses = []
        for fc_part in fc_parts:
            fc = fc_part["functionCall"]
            name = fc["name"]
            args = fc.get("args") or {}
            logger.debug("[mcp_tool] turn=%d %s(%s)", turn + 1, name, list(args.keys()))
            result = tool_executor(name, args)
            tools_called.append({"name": name, "args": args, "result": result})
            function_responses.append({
                "functionResponse": {
                    "name": name,
                    "response": {"result": result},
                }
            })

        contents.append({"role": "user", "parts": function_responses})

    # Max turns hit — return whatever text was last output
    last_text = next((p["text"] for p in reversed(parts) if "text" in p), "")
    logger.warning("[mcp_tool] Max turns (%d) reached", max_turns)
    return last_text, tools_called
