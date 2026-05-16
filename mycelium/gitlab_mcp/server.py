"""
GitLab MCP Server

A proper MCP server that exposes GitLab project operations as tools.
Designed to be run as a subprocess:  python -m gitlab_mcp.server

The tool interface mirrors the official GitLab MCP server spec so the
implementation can be swapped to the upstream binary without changing
agent code.
"""
import asyncio
import json
import sys
import os

# Add project root to path when running as subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from gitlab_mcp.client import GitLabClient

server = Server("gitlab-continuity-mcp")

# Lazy-initialized client (created after env is loaded in subprocess)
_gitlab: GitLabClient | None = None


def _get_gitlab() -> GitLabClient:
    global _gitlab
    if _gitlab is None:
        _gitlab = GitLabClient()
    return _gitlab


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="gitlab_list_members",
            description="List all project members with their access levels.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="gitlab_list_issues",
            description="List GitLab issues for the project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Filter by state: opened, closed, or all",
                        "enum": ["opened", "closed", "all"],
                    }
                },
            },
        ),
        types.Tool(
            name="gitlab_list_merge_requests",
            description="List GitLab merge requests.",
            inputSchema={
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Filter: opened, closed, merged, all",
                        "enum": ["opened", "closed", "merged", "all"],
                    }
                },
            },
        ),
        types.Tool(
            name="gitlab_list_commits",
            description=(
                "List recent commits. Returns all authors including external "
                "contributors from the upstream fork who are not project members."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "Branch name, defaults to main",
                    }
                },
            },
        ),
        types.Tool(
            name="gitlab_list_contributors",
            description=(
                "List unique contributors derived from commit history, "
                "with each contributor tagged as internal (project member) "
                "or external (upstream fork author)."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="gitlab_create_issue",
            description="Create a GitLab issue to track a continuity risk or remediation action.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Issue title"},
                    "description": {"type": "string", "description": "Issue body (markdown)"},
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Labels to apply",
                    },
                    "assignee_username": {
                        "type": "string",
                        "description": "GitLab username to assign (optional)",
                    },
                },
                "required": ["title", "description"],
            },
        ),
        types.Tool(
            name="gitlab_comment_on_issue",
            description="Post a comment on an existing GitLab issue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_iid": {"type": "integer", "description": "Issue IID"},
                    "body": {"type": "string", "description": "Comment body (markdown)"},
                },
                "required": ["issue_iid", "body"],
            },
        ),
        types.Tool(
            name="gitlab_assign_issue",
            description="Assign a GitLab issue to a team member.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_iid": {"type": "integer", "description": "Issue IID"},
                    "assignee_username": {"type": "string", "description": "GitLab username"},
                },
                "required": ["issue_iid", "assignee_username"],
            },
        ),
        types.Tool(
            name="gitlab_comment_on_mr",
            description="Post a comment on a GitLab merge request.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mr_iid": {"type": "integer", "description": "MR IID"},
                    "body": {"type": "string", "description": "Comment body (markdown)"},
                },
                "required": ["mr_iid", "body"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.Content]:
    gl = _get_gitlab()
    result: object

    if name == "gitlab_list_members":
        result = gl.get_members()
    elif name == "gitlab_list_issues":
        result = gl.get_open_issues()
    elif name == "gitlab_list_merge_requests":
        result = gl.get_open_merge_requests()
    elif name == "gitlab_list_commits":
        ref = (arguments or {}).get("ref", "main")
        result = gl.get_recent_commits(ref=ref)
    elif name == "gitlab_list_contributors":
        result = gl.get_commit_contributors()
    elif name == "gitlab_create_issue":
        result = gl.create_issue(**arguments)
    elif name == "gitlab_comment_on_issue":
        result = gl.comment_on_issue(**arguments)
    elif name == "gitlab_assign_issue":
        result = gl.assign_issue(**arguments)
    elif name == "gitlab_comment_on_mr":
        result = gl.comment_on_mr(**arguments)
    else:
        result = {"error": f"Unknown tool: {name}"}

    return [types.TextContent(type="text", text=json.dumps(result, default=str))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
