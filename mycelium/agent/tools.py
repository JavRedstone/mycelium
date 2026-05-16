"""
GitLab tool declarations in Gemini function-calling format.

These mirror the official GitLab MCP server tool interface so the agent is
MCP-compatible at the tool contract level, backed by python-gitlab.
"""
from __future__ import annotations

from gitlab_mcp.client import GitLabClient

# ---------------------------------------------------------------------------
# Read-only tool declarations
# ---------------------------------------------------------------------------
GITLAB_READ_DECLARATIONS = [
    {
        "name": "gitlab_list_members",
        "description": "List project members with access levels.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "gitlab_list_issues",
        "description": "List GitLab issues.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "state": {
                    "type": "STRING",
                    "description": "Filter by state: opened, closed, or all",
                    "enum": ["opened", "closed", "all"],
                }
            },
        },
    },
    {
        "name": "gitlab_list_merge_requests",
        "description": "List GitLab merge requests.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "state": {
                    "type": "STRING",
                    "description": "Filter: opened, closed, merged, all",
                    "enum": ["opened", "closed", "merged", "all"],
                }
            },
        },
    },
    {
        "name": "gitlab_list_commits",
        "description": (
            "List recent commits. Includes external contributors — authors present "
            "in commit history but NOT in the project member list."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "ref": {
                    "type": "STRING",
                    "description": "Branch/ref name, default 'main'",
                }
            },
        },
    },
    {
        "name": "gitlab_get_codeowners",
        "description": (
            "Fetch and parse the CODEOWNERS file. Returns path patterns mapped to "
            "declared owner usernames. Declared owners are ground-truth — stronger "
            "signal than inferred commit history. Empty if no CODEOWNERS file exists."
        ),
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "gitlab_list_pipelines",
        "description": (
            "List recent CI/CD pipeline runs with status (passed, failed, running, etc.). "
            "Failing pipelines in modules with low bus factor compound continuity risk."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "ref": {
                    "type": "STRING",
                    "description": "Branch/ref name, default 'main'",
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Max results, default 10",
                },
            },
        },
    },
    {
        "name": "gitlab_list_mr_approvers",
        "description": (
            "List approvers of recently merged MRs. Approvers have reviewed the code "
            "and hold implicit knowledge of those modules even without direct commits."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {
                    "type": "INTEGER",
                    "description": "Max MRs to check, default 20",
                }
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Write tool declarations
# ---------------------------------------------------------------------------
GITLAB_WRITE_DECLARATIONS = [
    {
        "name": "gitlab_create_issue",
        "description": "Create a GitLab issue to track a continuity risk or remediation action.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Issue title"},
                "description": {"type": "STRING", "description": "Issue body (markdown)"},
                "labels": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Labels, e.g. ['continuity', 'risk']",
                },
                "assignee_username": {
                    "type": "STRING",
                    "description": "GitLab username to assign (optional)",
                },
            },
            "required": ["title", "description"],
        },
    },
    {
        "name": "gitlab_comment_on_issue",
        "description": "Post a comment on an existing GitLab issue.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "issue_iid": {"type": "INTEGER", "description": "Issue IID (project-scoped number)"},
                "body": {"type": "STRING", "description": "Comment body (markdown)"},
            },
            "required": ["issue_iid", "body"],
        },
    },
    {
        "name": "gitlab_assign_issue",
        "description": "Assign a GitLab issue to a team member.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "issue_iid": {"type": "INTEGER", "description": "Issue IID"},
                "assignee_username": {"type": "STRING", "description": "GitLab username"},
            },
            "required": ["issue_iid", "assignee_username"],
        },
    },
    {
        "name": "gitlab_comment_on_mr",
        "description": "Post a comment on a GitLab merge request.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mr_iid": {"type": "INTEGER", "description": "MR IID (project-scoped number)"},
                "body": {"type": "STRING", "description": "Comment body (markdown)"},
            },
            "required": ["mr_iid", "body"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executors
# ---------------------------------------------------------------------------

def execute_read_tool(name: str, args: dict, gitlab: GitLabClient) -> dict:
    if name == "gitlab_list_members":
        return {"members": gitlab.get_members()}
    elif name == "gitlab_list_issues":
        state = args.get("state", "opened")
        issues = gitlab.get_open_issues() if state in ("opened", "all") else []
        return {"issues": issues}
    elif name == "gitlab_list_merge_requests":
        return {"merge_requests": gitlab.get_open_merge_requests()}
    elif name == "gitlab_list_commits":
        ref = args.get("ref", "main")
        return {"commits": gitlab.get_recent_commits(ref=ref)}
    elif name == "gitlab_get_codeowners":
        return {"codeowners": gitlab.get_codeowners()}
    elif name == "gitlab_list_pipelines":
        ref = args.get("ref", "main")
        limit = int(args.get("limit", 10))
        return {"pipelines": gitlab.get_pipeline_status(ref=ref, limit=limit)}
    elif name == "gitlab_list_mr_approvers":
        limit = int(args.get("limit", 20))
        return {"mr_approvers": gitlab.get_mr_approvers(limit=limit)}
    return {"error": f"unknown read tool: {name}"}


def execute_write_tool(name: str, args: dict, gitlab: GitLabClient) -> dict:
    try:
        if name == "gitlab_create_issue":
            return gitlab.create_issue(**args)
        elif name == "gitlab_comment_on_issue":
            return gitlab.comment_on_issue(**args)
        elif name == "gitlab_assign_issue":
            return gitlab.assign_issue(**args)
        elif name == "gitlab_comment_on_mr":
            return gitlab.comment_on_mr(**args)
        return {"error": f"unknown write tool: {name}"}
    except Exception as exc:
        return {"error": str(exc)}
