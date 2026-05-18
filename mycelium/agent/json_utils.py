"""Robust JSON extraction from LLM text output.

Kept in its own module (no Vertex AI / ADK imports) so it can be unit-tested
without triggering Vertex AI initialisation.
"""
from __future__ import annotations

import json


def try_parse_json(text: str) -> dict | None:
    """Best-effort extraction of a JSON object from possibly-noisy LLM text.

    Handles markdown code fences and prose-wrapped JSON. Returns None if no
    valid JSON object can be recovered.
    """
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None
