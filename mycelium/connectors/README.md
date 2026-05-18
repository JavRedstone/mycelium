# connectors/

External data sources: GitLab and the custom Mycelium MCP server.

---

## gitlab_client.py — GitLab API wrapper

`GitLabClient` wraps `python-gitlab` and provides all read + write operations
the pipeline and checks use.

### Read methods

| Method | Returns |
|--------|---------|
| `get_members()` | All project members with access level |
| `get_recent_commits(max_commits=200)` | Commits on the default branch |
| `get_commit_contributors()` | Deduplicated authors, classified internal/external |
| `get_codeowners()` | Parsed CODEOWNERS → `{pattern: [owners]}` |
| `get_pipeline_status(limit=5)` | Recent CI pipeline runs |
| `get_mr_approvers(limit=20)` | Merged MRs with approval records |
| `get_open_issues()` | All open issues |
| `get_open_merge_requests()` | All open MRs |
| `get_directory_tree(dir_path, recursive)` | File tree for a path |
| `get_file_content(file_path, max_bytes)` | Raw file content (capped at 8 KB by default) |
| `get_member_activity_dates()` | First and last commit date per author |
| `get_fork_divergence()` | Upstream commits not yet merged into the fork |
| `get_upstream_commits_since_fork(max_commits)` | Commits on the upstream since the fork point |

### Write methods

| Method | Description |
|--------|-------------|
| `create_issue(title, description, labels, assignee_username)` | Opens a new issue |
| `comment_on_issue(issue_iid, body)` | Posts a note on an issue |
| `assign_issue(issue_iid, assignee_username)` | Assigns an issue to a user |

### Known workaround

`python-gitlab`'s `ListMixin` intercepts the `path` keyword and treats it as a
URL override, causing 404s. Directory-scoped commit lookups use `http_list`
with `query_data={"path": dir_path}` instead:

```python
self._project.http_list("/repository/commits", query_data={"path": dir_path}, ...)
```

---

## mcp_server.py — Mycelium MCP server

Runs as a stdio subprocess. Exposes the knowledge graph and GitLab write
operations as MCP tools that ADK agents call via the MCP protocol.

### Read tools

| Tool | What it returns |
|------|----------------|
| `get_concerns(limit)` | Recent analyst findings + concentrated modules |
| `get_module_experts(module_path)` | Contributors sorted by expertise score |
| `get_orphaned_modules()` | Modules with no CODEOWNERS entry, sorted by bus_factor |
| `suggest_assignee(module_path)` | Best available internal reviewer |
| `get_gitlab_project_state()` | Live snapshot: members, open issues, open MRs, pipeline status |

### Write tools

| Tool | What it does |
|------|-------------|
| `create_issue(title, description, labels, assignee_username)` | Opens a GitLab issue |
| `add_comment(issue_iid, body)` | Posts a comment on an issue |
| `assign_issue(issue_iid, assignee_username)` | Assigns an issue |

### Running the MCP server directly

```
python connectors/mcp_server.py
```

The server blocks on stdio — use `checks/mcp/check_mcp_mycelium.py` to
connect and inspect its tool list without writing any data.
