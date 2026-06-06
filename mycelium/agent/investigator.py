# Copyright 2026 Javier Huang
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Investigator subagents - content-aware judgment.

Spawned concurrently by the pipeline's investigate stage. Each subagent focuses
on one entity (member, module, or drift) and reads actual file content via the
GitLabClient, then asks Gemini to produce a structured assessment that numeric
signals can't.

Design principle: no thresholds. Severity comes from reading content, not from
comparing counts to constants. Each subagent returns its own reasoning so the
downstream analyst sees evidence, not buckets.

These are lightweight Gemini calls (not full AdkApp runtime) so we can spawn
many of them concurrently per pipeline run.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import vertexai
from google import genai

from agent.activity_bus import bus as _activity_bus
from agent.json_utils import try_parse_json
from config.settings import settings

if TYPE_CHECKING:
    from connectors.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)

vertexai.init(project=settings.google_cloud_project, location=settings.google_cloud_location)

_GENAI = genai.Client(
    vertexai=True,
    project=settings.google_cloud_project,
    location=settings.google_cloud_location,
)

# Budget caps - adaptive within these limits, the subagent decides when to stop.
_MAX_FILES_PER_MODULE_INVESTIGATION = 30
_MAX_FILES_PER_MEMBER_INVESTIGATION = 10
_MAX_DEPTH = 3
_MAX_SUBDIRS_PER_LEVEL = 2
_MAX_CODE_SAMPLES_PER_DIR = 3
_MAX_UPSTREAM_COMMITS_TO_READ = 25

# Always-read filenames (case-insensitive) - these are the highest-value reads.
_KEY_DOC_FILES = {
    "readme.md", "readme.rst", "readme.txt", "readme",
    "contributing.md", "contributing.rst",
    "architecture.md", "design.md", "docs.md",
    "package.json", "pyproject.toml", "setup.py", "setup.cfg",
    "go.mod", "cargo.toml", "build.gradle", "pom.xml",
    "makefile", "dockerfile", ".gitlab-ci.yml", ".github/workflows",
    "codeowners",
}


def _gemini_call(prompt: str, model: str | None = None) -> str:
    """Synchronous Gemini call. Wrap in asyncio.to_thread for concurrency."""
    model_name = model or settings.gemini_model
    try:
        response = _GENAI.models.generate_content(model=model_name, contents=prompt)
        return (response.text or "").strip()
    except Exception as exc:
        logger.warning("[investigator] Gemini call failed: %s", exc)
        return ""


def _count_files(tree: dict) -> int:
    count = len(tree.get("files_read", []))
    for sub in tree.get("subdirs_investigated", []):
        count += _count_files(sub)
    return count


def _format_files_for_prompt(file_tree: dict, indent: int = 0) -> str:
    """Flatten a recursive file tree into a prompt-friendly text block."""
    lines = []
    prefix = "  " * indent
    lines.append(f"{prefix}[dir] {file_tree.get('path', '?')}/")
    for f in file_tree.get("files_read", []):
        lines.append(f"{prefix}  ===== {f['path']} =====")
        lines.append(f.get("content", ""))
        lines.append("")
    for sub in file_tree.get("subdirs_investigated", []):
        lines.append(_format_files_for_prompt(sub, indent + 1))
    return "\n".join(lines)


async def _read_directory_files(
    gitlab_client: "GitLabClient",
    dir_path: str,
    depth: int,
    budget: list[int],
) -> dict:
    """Adaptive-depth recursive reader. The shared budget list lets callers
    stop the whole recursion once enough has been read."""
    result = {"path": dir_path, "files_read": [], "subdirs_investigated": []}
    if budget[0] <= 0:
        return result

    tree = await asyncio.to_thread(gitlab_client.get_directory_tree, dir_path, False)

    key_files = [
        item for item in tree
        if item["type"] == "blob" and item["name"].lower() in _KEY_DOC_FILES
    ]
    # Sample a few code/source files for naming + comment signal
    other_files = [
        item for item in tree
        if item["type"] == "blob" and item["name"].lower() not in _KEY_DOC_FILES
    ][:_MAX_CODE_SAMPLES_PER_DIR]

    for item in key_files + other_files:
        if budget[0] <= 0:
            break
        content = await asyncio.to_thread(gitlab_client.get_file_content, item["path"])
        if content:
            result["files_read"].append({"path": item["path"], "content": content})
            budget[0] -= 1

    # Adaptive recursion. Subagent decides whether to drill based on
    # remaining budget and what's left to investigate.
    if depth < _MAX_DEPTH and budget[0] > 5:
        subdirs = [item for item in tree if item["type"] == "tree"]
        for subdir in subdirs[:_MAX_SUBDIRS_PER_LEVEL]:
            if budget[0] <= 5:
                break
            sub = await _read_directory_files(gitlab_client, subdir["path"], depth + 1, budget)
            if sub["files_read"] or sub["subdirs_investigated"]:
                result["subdirs_investigated"].append(sub)

    return result


# ---------------------------------------------------------------------------
# Module investigator
# ---------------------------------------------------------------------------

async def investigate_module(
    module_path: str,
    contributors: list[dict],
    gitlab_client: "GitLabClient",
) -> dict:
    """Recursively read a module's content; judge knowledge transferability."""
    budget = [_MAX_FILES_PER_MODULE_INVESTIGATION]
    file_tree = await _read_directory_files(gitlab_client, module_path, depth=0, budget=budget)

    file_count = _count_files(file_tree)
    if file_count == 0:
        return {
            "module": module_path,
            "investigated": False,
            "reason": "No readable files found in this module",
            "files_read_count": 0,
        }

    contributors_summary = [
        f"- {c.get('developer_username', '?')}: {c.get('commit_count', 0)} commits, "
        f"expertise={c.get('expertise_score', 0):.2f}, external={c.get('external', False)}"
        for c in contributors[:10]
    ]

    prompt = f"""You are a module investigator subagent for an engineering continuity system.

You receive: a module path, the files in it (recursively read), and its contributor list.
You output: a structured assessment of how transferable the knowledge in this module is.

Module: {module_path}
Files read ({file_count}):
{_format_files_for_prompt(file_tree)}

Top contributors:
{chr(10).join(contributors_summary) if contributors_summary else "(no contributor data)"}

How to judge transferability - read the actual content, do not count files:
- A module is TRANSFERABLE when a new engineer can read these files and understand what
  the module does, how to change it, what conventions apply, and who to ask. README explains
  intent. Code has meaningful naming and comments at decision points. Setup is documented.
- A module is NOT TRANSFERABLE when the README is empty, a placeholder, or just "TODO";
  source files lack comments at non-obvious decisions; setup steps live only in one person's
  head; design decisions are nowhere recorded.
- Placeholder docs ("TODO: add docs", "Coming soon") are WORSE than no docs - they signal
  abandoned intent.

Return ONLY valid JSON, no markdown. Schema:
{{
  "module": "{module_path}",
  "transferability_assessment": "<one paragraph: can a new engineer pick this up>",
  "doc_coverage": <float 0.0-1.0 - your own judgment from reading the content>,
  "documentation_state": "<excellent|adequate|sparse|placeholder|missing>",
  "key_concerns": ["<specific concern 1>", "<specific concern 2>"],
  "knowledge_at_risk_if_top_contributor_leaves": "<one paragraph: what would be lost>",
  "recommended_documentation_actions": ["<actionable item 1>", "<actionable item 2>"],
  "severity_reasoning": "<one paragraph: how severe is the continuity risk and why>"
}}
"""

    text = await asyncio.to_thread(_gemini_call, prompt)
    parsed = try_parse_json(text) or {}
    parsed.setdefault("module", module_path)
    parsed["files_read_count"] = file_count
    parsed["investigated"] = True

    lines = [f"**Module: {module_path}**  ({file_count} files read)"]
    if parsed.get("documentation_state"):
        lines.append(f"Documentation: {parsed['documentation_state']}")
    if parsed.get("transferability_assessment"):
        lines.append(f"\n{parsed['transferability_assessment']}")
    if parsed.get("severity_reasoning"):
        lines.append(f"\n{parsed['severity_reasoning']}")
    _activity_bus.emit({"type": "agent_text", "stage_id": "investigate", "text": "\n".join(lines)})

    return parsed


# ---------------------------------------------------------------------------
# Member investigator
# ---------------------------------------------------------------------------

async def investigate_member(
    member: dict,
    attention_reason: str,
    uniquely_owned_modules: list[str],
    gitlab_client: "GitLabClient",
) -> dict:
    """Investigate what knowledge walks out the door if this member leaves."""
    file_samples = []
    budget = [_MAX_FILES_PER_MEMBER_INVESTIGATION]
    for module_path in uniquely_owned_modules[:3]:
        if budget[0] <= 0:
            break
        sub = await _read_directory_files(gitlab_client, module_path, depth=0, budget=budget)
        if sub["files_read"] or sub["subdirs_investigated"]:
            file_samples.append(sub)

    files_text = (
        "\n\n".join(_format_files_for_prompt(s) for s in file_samples)
        if file_samples
        else "(no readable files in this member's modules)"
    )

    member_name = member.get("name") or member.get("username") or "unknown"

    prompt = f"""You are a member investigator subagent for an engineering continuity system.

You receive: a high-attention team member, why they need attention, the modules they
uniquely contribute to, and sample file content from those modules.
You output: a structured assessment of what knowledge walks out the door if this person
leaves or becomes inactive.

Member: {member_name}
Attention reason: {attention_reason}
Modules they uniquely contribute to or solely own: {uniquely_owned_modules}

Sample file content from their modules:
{files_text}

Member metadata: {json.dumps(member, default=str, indent=2)}

How to judge:
- "sole_contributor" - they are the only meaningful committer in one or more modules.
  Their leaving means no internal knowledge of those modules.
- "recently_inactive" - they were contributing, now silent. Could be vacation, role change,
  or actual departure. Assess what is at risk if they don't return.
- "recent_joiner" - they recently started contributing. Risk is different: they may not
  yet have deep context, and assigning critical work to them prematurely is itself risky.
- "multi_module_concentration" - they own multiple critical modules. Concentration risk.

Do not threshold. Read the modules' actual content (above) to judge how documented their
work is and whether someone else could pick it up from the code alone.

Return ONLY valid JSON, no markdown. Schema:
{{
  "member": "{member_name}",
  "attention_reason": "{attention_reason}",
  "uniquely_owned_modules": {json.dumps(uniquely_owned_modules)},
  "knowledge_at_risk": "<one paragraph: what specifically would be lost>",
  "transferability_today": "<one paragraph: could someone pick this up from the code now>",
  "urgency_reasoning": "<one paragraph: how urgent is action, and why>",
  "recommended_actions": ["<actionable item 1>", "<actionable item 2>"],
  "documentation_gaps": ["<specific gap 1>", "<specific gap 2>"]
}}
"""

    text = await asyncio.to_thread(_gemini_call, prompt)
    parsed = try_parse_json(text) or {}
    parsed.setdefault("member", member_name)
    parsed.setdefault("attention_reason", attention_reason)
    parsed.setdefault("uniquely_owned_modules", uniquely_owned_modules)

    lines = [f"**Member: {member_name}**  (reason: {attention_reason})"]
    if parsed.get("knowledge_at_risk"):
        lines.append(f"\n{parsed['knowledge_at_risk']}")
    if parsed.get("urgency_reasoning"):
        lines.append(f"\n{parsed['urgency_reasoning']}")
    _activity_bus.emit({"type": "agent_text", "stage_id": "investigate", "text": "\n".join(lines)})

    return parsed


# ---------------------------------------------------------------------------
# Drift investigator
# ---------------------------------------------------------------------------

async def investigate_drift(
    fork_divergence: dict,
    gitlab_client: "GitLabClient",
) -> dict:
    """Read upstream commits the fork hasn't merged; judge urgency from content."""
    commits = await asyncio.to_thread(
        gitlab_client.get_upstream_commits_since_fork, _MAX_UPSTREAM_COMMITS_TO_READ
    )

    if not commits:
        return {
            "investigated": False,
            "reason": "No upstream commits readable (not a fork, no divergence, or upstream inaccessible)",
            **fork_divergence,
        }

    commits_text = "\n\n".join(
        f"[{c['id']}] {c['author_name']} ({c['created_at'][:10]})\n"
        f"  Title:  {c['title']}\n"
        f"  Body:   {c['message'][:300]}"
        for c in commits
    )

    prompt = f"""You are a drift investigator subagent for an engineering continuity system.

The fork is behind upstream. Upstream commits the fork hasn't merged (most recent first):

{commits_text}

Total commits behind: {fork_divergence.get('commits_behind', 'unknown')}
Upstream project: {fork_divergence.get('upstream_project', 'unknown')}

Your job: judge how urgent it is to sync upstream BASED ON THE CONTENT of these commits.
Do NOT use the count as severity. 3 CVE patches >>> 30 README typo fixes.

Read each commit title/message and weigh:
- Security signals: "CVE", "vulnerability", "security", "patch", "exploit", "sanitiz"
- Breaking changes: "breaking", "BREAKING CHANGE", "major", "deprecat"
- Critical-path edits: auth, payment, data integrity, encryption
- Low-impact: typo, formatting, comment, README, changelog, version bump, deps

Return ONLY valid JSON, no markdown. Schema:
{{
  "commits_behind": {fork_divergence.get('commits_behind', 0)},
  "upstream_project": "{fork_divergence.get('upstream_project', '')}",
  "urgency_assessment": "<one paragraph reasoning, content-driven not count-driven>",
  "high_priority_commits": [
    {{"id": "<short sha>", "title": "<title>", "why": "<why this one matters>"}}
  ],
  "low_priority_dominance": <true if most commits are cosmetic/docs/version bumps>,
  "recommended_action": "<one sentence>",
  "severity_reasoning": "<one paragraph: how severe and why, in plain English>"
}}
"""

    text = await asyncio.to_thread(_gemini_call, prompt)
    parsed = try_parse_json(text) or {}
    parsed["investigated"] = True
    parsed.setdefault("commits_behind", fork_divergence.get("commits_behind", 0))
    parsed.setdefault("upstream_project", fork_divergence.get("upstream_project", ""))

    lines = [f"**Upstream drift**: {parsed['commits_behind']} commits behind `{parsed['upstream_project']}`"]
    if parsed.get("urgency_assessment"):
        lines.append(f"\n{parsed['urgency_assessment']}")
    if parsed.get("severity_reasoning"):
        lines.append(f"\n{parsed['severity_reasoning']}")
    _activity_bus.emit({"type": "agent_text", "stage_id": "investigate", "text": "\n".join(lines)})

    return parsed
