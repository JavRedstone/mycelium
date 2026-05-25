"""
Mycelium custom MCP server.

Exposes all tools the act agent needs: knowledge graph reads AND GitLab write
actions.  The official GitLab MCP (mcp-remote) requires OAuth/Duo and is
unreliable - all write operations go through this server via the configured
GITLAB_TOKEN instead.

Entry point (stdio):
    python connectors/mcp_server.py

Read tools:
    get_concerns            - Recent analyst findings (qualitative, no scores)
    get_module_experts      - Top contributors for a specific module
    get_orphaned_modules    - Modules with bus_factor <= 1 or no declared owner
    suggest_assignee        - Best person to receive a knowledge transfer
    get_gitlab_project_state - Compact GitLab snapshot (issues + MRs)

Write tools (GitLab - project is pre-configured, no project_id needed):
    create_issue            - Open a new GitLab issue
    add_comment             - Comment on an issue or MR
    assign_issue            - Assign an issue to a team member
    edit_issue              - Edit an existing issue's description (and optionally title)
    close_issue             - Close an existing issue (e.g. superseded)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make the project root importable when run as __main__.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP
from motor.motor_asyncio import AsyncIOMotorClient

from config.settings import settings
from connectors.gitlab_client import GitLabClient

mcp = FastMCP("mycelium")

# ---------------------------------------------------------------------------
# Shared DB client (created lazily per-call; Motor is async-safe to share)
# ---------------------------------------------------------------------------

def _db():
    client = AsyncIOMotorClient(settings.mongodb_uri)
    return client[settings.mongodb_db]


# ---------------------------------------------------------------------------
# Tool: get_concerns  (replaces get_risk_summary - no scores, qualitative)
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_concerns(limit: int = 50) -> dict:
    """
    Return recent continuity findings from the knowledge graph.

    Findings are qualitative analyst output (concern_type + narrative + evidence
    + recommended_actions). The system does NOT compute scalar risk scores -
    you reason over the narratives directly.

    Args:
        limit: Maximum number of findings to return (default 50).
    """
    db = _db()
    findings = await db["findings"].find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    modules = await db["modules"].find({}, {"_id": 0, "path": 1, "bus_factor": 1, "owners": 1}).to_list(None)
    single_committer = [m for m in modules if m.get("bus_factor", 0) <= 1]

    # Group findings by concern_type for quick scanning
    by_type: dict[str, int] = {}
    for f in findings:
        ct = f.get("concern_type", "unspecified")
        by_type[ct] = by_type.get(ct, 0) + 1

    return {
        "total_modules": len(modules),
        "modules_with_single_committer": len(single_committer),
        "single_committer_paths": [m["path"] for m in single_committer[:10]],
        "finding_count": len(findings),
        "findings_by_concern_type": by_type,
        "recent_findings": findings,
    }


# ---------------------------------------------------------------------------
# Tool: get_module_experts
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_module_experts(module_path: str) -> dict:
    """
    Return the top contributors for a given module path.

    Args:
        module_path: The module path as stored in the knowledge graph
                     (e.g. "src/auth/login.py").

    Returns a dict with the module's risk score, bus_factor, owners, and a
    ranked list of contributors with their expertise scores.
    """
    db = _db()
    module = await db["modules"].find_one({"path": module_path}, {"_id": 0})
    if not module:
        return {"error": f"Module not found: {module_path}"}

    contributions = await db["contributions"].find(
        {"module_path": module_path}, {"_id": 0}
    ).sort("expertise_score", -1).to_list(10)

    experts = []
    for c in contributions:
        dev = await db["developers"].find_one(
            {"username": c["developer_username"]}, {"_id": 0, "name": 1, "active": 1, "external": 1}
        )
        experts.append({
            "username": c["developer_username"],
            "name": (dev or {}).get("name", c["developer_username"]),
            "expertise_score": c.get("expertise_score", 0),
            "commit_count": c.get("commit_count", 0),
            "active": (dev or {}).get("active", True),
            "external": (dev or {}).get("external", False),
        })

    return {
        "path": module_path,
        "bus_factor": module.get("bus_factor", 0),
        "owners": module.get("owners", []),
        "experts": experts,
    }


# ---------------------------------------------------------------------------
# Tool: get_orphaned_modules
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_orphaned_modules(max_results: int = 20) -> list[dict]:
    """
    Return modules with low contributor concentration or no declared owner.

    A module is structurally orphaned when:
    - bus_factor <= 1 (one or fewer contributors hold 80%+ of the commits), OR
    - owners list is empty (no CODEOWNERS entry).

    This is a structural observation, not a severity judgment - the caller
    should reason about whether each entry actually warrants action.

    Args:
        max_results: Maximum number of results to return (default 20).
    """
    db = _db()
    cursor = db["modules"].find(
        {"$or": [{"bus_factor": {"$lte": 1}}, {"owners": {"$size": 0}}, {"owners": {"$exists": False}}]},
        {"_id": 0, "path": 1, "bus_factor": 1, "owners": 1},
    ).sort("bus_factor", 1).limit(max_results)

    return await cursor.to_list(max_results)


# ---------------------------------------------------------------------------
# Tool: suggest_assignee
# ---------------------------------------------------------------------------

@mcp.tool()
async def suggest_assignee(module_path: str) -> dict:
    """
    Suggest the best active internal team member to receive a knowledge
    transfer for the given module.

    Ranks candidates by expertise_score, preferring active internal members.
    Falls back to external contributors if no internal candidates exist.

    Args:
        module_path: The module path to find a knowledge transfer recipient for.
    """
    db = _db()
    contributions = await db["contributions"].find(
        {"module_path": module_path}, {"_id": 0}
    ).sort("expertise_score", -1).to_list(None)

    if not contributions:
        return {"error": f"No contribution data for module: {module_path}"}

    ranked = []
    for c in contributions:
        dev = await db["developers"].find_one(
            {"username": c["developer_username"]}, {"_id": 0}
        )
        if dev:
            ranked.append({
                "username": c["developer_username"],
                "name": dev.get("name", c["developer_username"]),
                "expertise_score": c.get("expertise_score", 0),
                "commit_count": c.get("commit_count", 0),
                "active": dev.get("active", True),
                "external": dev.get("external", False),
            })

    # Prefer active internal, then active external, then inactive
    def priority(r: dict) -> tuple:
        return (not r["active"], r["external"], -r["expertise_score"])

    ranked.sort(key=priority)

    top = ranked[0] if ranked else None
    return {
        "module_path": module_path,
        "suggested": top,
        "all_candidates": ranked[:5],
    }


# ---------------------------------------------------------------------------
# Tool: get_gitlab_project_state
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_gitlab_project_state() -> dict:
    """
    Return a compact snapshot of the GitLab project state.

    Includes:
    - Count of open issues and their labels
    - Count of open merge requests
    - Recent commit authors (last 10 commits)

    Useful for the agent to check existing issues before creating duplicates.
    """
    def _run_sync():
        client = GitLabClient()
        issues = client.get_open_issues()
        mrs = client.get_open_merge_requests()
        commits = client.get_recent_commits()[:10]
        return {
            "open_issues": len(issues),
            "issues": [
                {
                    "iid": i["iid"],
                    "title": i["title"],
                    "author": i.get("author"),
                    "bot_authored": i.get("bot_authored", False),
                    "labels": i.get("labels", []),
                    "assignee": i.get("assignee"),
                }
                for i in issues[:20]
            ],
            "open_merge_requests": len(mrs),
            "merge_requests": [
                {"iid": mr["iid"], "title": mr["title"], "author": mr.get("author"), "source_branch": mr.get("source_branch")}
                for mr in mrs[:10]
            ],
            "recent_commit_authors": list({c.get("author_name") for c in commits}),
        }

    return await asyncio.to_thread(_run_sync)


# ---------------------------------------------------------------------------
# Write tools - GitLab actions via the pre-configured GITLAB_TOKEN
# The project is already set in settings; callers must NOT pass a project_id.
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_issue(
    title: str,
    description: str,
    labels: list[str] | None = None,
    assignee_username: str | None = None,
) -> dict:
    """
    Create a new issue in the configured GitLab project.

    Args:
        title: Short issue title (50 chars or less works best).
        description: Markdown body - include context, affected module, and a
                     checklist of recommended actions.
        labels: Optional list of label strings to apply (e.g. ["continuity-risk"]).
        assignee_username: Optional GitLab username to assign the issue to.

    Returns:
        {"iid": <issue iid>, "id": <issue id>, "web_url": <url>}
    """
    def _run() -> dict:
        client = GitLabClient()
        return client.create_issue(
            title=title,
            description=description,
            labels=labels,
            assignee_username=assignee_username,
        )

    return await asyncio.to_thread(_run)


@mcp.tool()
async def add_comment(
    iid: int,
    body: str,
    kind: str = "issue",
) -> dict:
    """
    Post a comment on an existing issue or merge request.

    Args:
        iid: The internal ID (iid) of the issue or MR.
        body: Markdown comment body.
        kind: "issue" (default) or "mr".

    Returns:
        {"note_id": <id>}
    """
    def _run() -> dict:
        client = GitLabClient()
        if kind == "mr":
            return client.comment_on_mr(mr_iid=iid, body=body)
        return client.comment_on_issue(issue_iid=iid, body=body)

    return await asyncio.to_thread(_run)


@mcp.tool()
async def assign_issue(iid: int, assignee_username: str) -> dict:
    """
    Assign an existing issue to a team member.

    Args:
        iid: The internal ID (iid) of the issue.
        assignee_username: GitLab username of the person to assign.

    Returns:
        {"iid": <iid>, "assignee": <username>}
    """
    def _run() -> dict:
        client = GitLabClient()
        return client.assign_issue(issue_iid=iid, assignee_username=assignee_username)

    return await asyncio.to_thread(_run)


@mcp.tool()
async def edit_issue(
    iid: int,
    description: str,
    title: str | None = None,
) -> dict:
    """
    Edit the description (and optionally title) of an existing GitLab issue.

    Use this to correct or update an issue in place rather than creating a
    duplicate.  Prefer this over superseding when the topic is right but the
    content needs updating.

    Args:
        iid: The internal ID (iid) of the issue to edit.
        description: New Markdown body for the issue.
        title: Optional new title. Omit to leave the title unchanged.

    Returns:
        {"iid": <iid>}
    """
    def _run() -> dict:
        client = GitLabClient()
        return client.edit_issue(issue_iid=iid, description=description, title=title)

    return await asyncio.to_thread(_run)


@mcp.tool()
async def close_issue(iid: int) -> dict:
    """
    Close an existing GitLab issue.

    Use this when an issue has been superseded by a newer issue and the old
    one should be marked resolved.  Always add a linking comment on the old
    issue BEFORE closing it so the audit trail is preserved.

    Args:
        iid: The internal ID (iid) of the issue to close.

    Returns:
        {"iid": <iid>, "state": "closed"}
    """
    def _run() -> dict:
        client = GitLabClient()
        return client.close_issue(issue_iid=iid)

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Onboarding / Offboarding artifact generation
# ---------------------------------------------------------------------------

@mcp.tool()
async def generate_onboarding_pack(new_member_username: str) -> dict:
    """
    Generate a structured onboarding guide for a new team member as a GitLab issue.

    Queries the knowledge graph to produce:
    - Active team roster with names and usernames
    - Module map with expert contact for each area
    - Modules flagged as concentrated (bus_factor <= 1) - areas needing care
    - A starter checklist for the new member

    The issue is tagged 'onboarding' and 'mycelium' so it can be filtered later.

    Args:
        new_member_username: GitLab username of the new team member (without @).

    Returns:
        {"iid": <issue iid>, "id": <issue id>, "web_url": <url>}
    """
    db = _db()
    modules = await db["modules"].find({}, {"_id": 0}).to_list(None)
    contributions = await db["contributions"].find({}, {"_id": 0}).to_list(None)
    developers = await db["developers"].find(
        {"active": True, "external": False}, {"_id": 0}
    ).to_list(None)

    # Build module → top experts map
    module_experts: dict[str, list[str]] = {}
    for c in contributions:
        if not c.get("external") and c.get("expertise_score", 0) > 0.1:
            module_experts.setdefault(c["module_path"], []).append(c["developer_username"])

    lines = [
        f"# Onboarding Guide: @{new_member_username}",
        "",
        "Welcome to the team! This guide was generated by Mycelium based on the current knowledge graph.",
        "It maps who knows what so you know who to pair with as you ramp up.",
        "",
        "## Team",
        "",
    ]
    for dev in developers[:15]:
        lines.append(f"- **{dev.get('name', dev['username'])}** - @{dev['username']}")
    lines += ["", "## Codebase - Who Knows What", ""]

    for m in sorted(modules, key=lambda x: x.get("bus_factor", 0)):
        path = m["path"]
        experts = module_experts.get(path, [])
        owners = m.get("owners", [])
        bf = m.get("bus_factor", 0)
        expert_str = ", ".join(f"@{e}" for e in experts[:3]) if experts else "_no data yet_"
        owner_str = ", ".join(f"@{o}" for o in owners) if owners else "_not in CODEOWNERS_"
        concentration = " ⚠️ concentrated" if bf <= 1 else ""
        lines.append(f"### `{path}`{concentration}")
        lines.append(f"- Experts (by commit history): {expert_str}")
        lines.append(f"- Declared owners (CODEOWNERS): {owner_str}")
        lines.append("")

    lines += [
        "## Getting Started Checklist",
        "",
        "- [ ] Read this guide and note who to reach out to for each area you'll touch",
        "- [ ] Set up local development environment (see repo README)",
        "- [ ] Review recent merge requests to understand active work",
        "- [ ] Pick a starter issue and pair with the module expert",
        "- [ ] Schedule a 1:1 with each team member in the list above",
        "- [ ] Review CODEOWNERS to understand declared ownership",
        "",
        "_Generated by [Mycelium Continuity Engine](https://github.com/your-org/mycelium)_",
    ]

    body = "\n".join(lines)

    def _create() -> dict:
        client = GitLabClient()
        return client.create_issue(
            title=f"Onboarding: {new_member_username}",
            description=body,
            labels=["onboarding", "mycelium"],
        )

    return await asyncio.to_thread(_create)


@mcp.tool()
async def generate_offboarding_artifact(departing_member_username: str) -> dict:
    """
    Generate a knowledge handoff artifact for a departing or inactive team member.

    Identifies which modules this person uniquely owns, what knowledge walks out
    the door if they leave, and who is the best transfer candidate for each area.
    Creates a GitLab issue to track the handoff process.

    Args:
        departing_member_username: GitLab username of the departing/inactive member.

    Returns:
        {"iid": <issue iid>, "id": <issue id>, "web_url": <url>}
    """
    db = _db()
    contributions = await db["contributions"].find(
        {"developer_username": departing_member_username, "external": False},
        {"_id": 0},
    ).sort("expertise_score", -1).to_list(None)

    recent_findings = await db["findings"].find(
        {"subject": f"members/{departing_member_username}"},
        {"_id": 0},
    ).sort("created_at", -1).limit(5).to_list(5)

    lines = [
        f"# Knowledge Handoff: @{departing_member_username}",
        "",
        "Generated by Mycelium to document what knowledge this member holds and what needs to transfer.",
        "Use this issue to track the handoff before their context is lost.",
        "",
        "## At-Risk Modules",
        "",
    ]

    high_value = [c for c in contributions if c.get("expertise_score", 0) >= 0.3]
    if not high_value:
        lines.append("_No significant module ownership detected yet - run the pipeline to populate._")
        lines.append("")
    else:
        for c in high_value[:10]:
            path = c["module_path"]
            score = c.get("expertise_score", 0)
            # Find next-best internal candidate
            others = await db["contributions"].find(
                {
                    "module_path": path,
                    "developer_username": {"$ne": departing_member_username},
                    "external": False,
                },
                {"_id": 0},
            ).sort("expertise_score", -1).limit(1).to_list(1)
            candidate = f"@{others[0]['developer_username']}" if others else "_none identified_"
            lines.append(f"### `{path}`")
            lines.append(f"- **Their expertise score**: {score:.2f}")
            lines.append(f"- **Best transfer candidate**: {candidate}")
            lines.append("")

    if recent_findings:
        lines += ["## Recent Analyst Findings", ""]
        for f in recent_findings:
            ct = f.get("concern_type", "?")
            narrative = (f.get("narrative") or "")[:250]
            lines.append(f"**{ct}**: {narrative}")
            actions = f.get("recommended_actions") or []
            for a in actions:
                lines.append(f"- {a}")
            lines.append("")

    lines += [
        "## Handoff Checklist",
        "",
        "- [ ] Identify a new primary owner for each at-risk module above",
        "- [ ] Schedule knowledge transfer sessions before departure",
        "- [ ] Update CODEOWNERS with new owners",
        "- [ ] Document any undocumented architecture decisions in the module READMEs",
        "- [ ] Review and reassign open issues/MRs currently assigned to this member",
        "- [ ] Confirm the new owner can reproduce the development setup independently",
        "",
        "_Generated by [Mycelium Continuity Engine](https://github.com/your-org/mycelium)_",
    ]

    body = "\n".join(lines)

    def _create() -> dict:
        client = GitLabClient()
        return client.create_issue(
            title=f"Knowledge Handoff: {departing_member_username}",
            description=body,
            labels=["offboarding", "knowledge-transfer", "mycelium"],
        )

    return await asyncio.to_thread(_create)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
