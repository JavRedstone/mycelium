# checks/mcp/

MCP (Model Context Protocol) server connectivity checks.
Mycelium uses three MCP servers; this folder has a check for each.

Run from the project root (`mycelium/mycelium/`):

---

## check_mcp_mycelium.py — Mycelium custom MCP

```
python checks/mcp/check_mcp_mycelium.py
```

Starts `connectors/mcp_server.py` as a stdio subprocess and verifies that all
expected tools are registered:

| Tool | Description |
|------|-------------|
| `get_concerns` | Returns analyst findings + concentrated modules |
| `get_module_experts` | Contributors for a given module path |
| `get_orphaned_modules` | Modules with no internal owners |
| `suggest_assignee` | Best available reviewer for a module |
| `get_gitlab_project_state` | Live GitLab snapshot (members, issues, MRs) |
| `create_issue` | Open a new GitLab issue |
| `add_comment` | Post a comment on an issue |
| `assign_issue` | Assign an issue to a team member |

**Requires:** `MONGODB_URI`, `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`

---

## check_mcp_gitlab.py — GitLab OAuth MCP

```
python checks/mcp/check_mcp_gitlab.py
```

Connects to the official GitLab MCP server (`https://gitlab.com/api/v4/mcp`)
via `mcp-remote` and OAuth 2.0. Lists all available tools.

**First run:** opens a browser window for OAuth consent.
**Subsequent runs:** uses the cached token from `~/.mcp-auth/`.

Prerequisites:
- Node.js 20+ (`npx` in PATH)
- GitLab Duo enabled (Premium/Ultimate tier)
- Beta and experimental features turned on (GitLab > Edit profile > Preferences)

Complete the first-run OAuth before running this check automatically:
```
npx -y mcp-remote@latest https://gitlab.com/api/v4/mcp
```

Troubleshooting:
```
# Clear stale OAuth cache
del /s /q %USERPROFILE%\.mcp-auth\mcp-remote*   # Windows
rm -rf ~/.mcp-auth/mcp-remote*                   # Linux/macOS
```

---

## check_mcp_mongo.py — MongoDB MCP

```
python checks/mcp/check_mcp_mongo.py
```

Starts `@mongodb-js/mongodb-mcp-server` via `npx` and passes `MONGODB_URI`
as `MDB_MCP_CONNECTION_STRING`. Lists all available tools.

**Requires:** `MONGODB_URI`, Node.js 20+

---

## check_mcp.py — general MCP client smoke test

```
python checks/mcp/check_mcp.py
```

Lightweight MCP client connectivity check (no specific server). Use the
server-specific scripts above for real validation.
