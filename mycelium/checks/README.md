# checks/

Connectivity and smoke tests for every external dependency Mycelium relies on.
Each check is a standalone script — no agent logic runs, nothing is written to
production data unless the script name includes `write`.

Run from the project root (`mycelium/mycelium/`):

```
cd mycelium/mycelium
```

---

## Run everything at once

```
python checks/check_all.py
```

Runs all checks in order: MongoDB → GitLab read → GitLab write → Vertex AI →
ADK → Mycelium MCP → GitLab MCP → MongoDB MCP. Stops on first failure within
each script but continues to the next script regardless.

---

## Inspect the live data (read-only)

```
python checks/show.py              # full report: GitLab state + knowledge graph
python checks/show.py --gitlab     # GitLab only
python checks/show.py --graph      # MongoDB graph only
python checks/show.py --rescore    # recompute bus_factor measurements from graph
python checks/show.py --commits 50 # show last 50 commits (default 20)
```

`show.py` prints exactly what the agent sees — members, commits, CODEOWNERS,
pipelines, MRs, issues, findings, concentrated modules. Nothing is modified.

---

## Subfolders

| Folder | What it checks |
|--------|---------------|
| `mongo/` | MongoDB Atlas connectivity |
| `gitlab/` | GitLab read access + write operations (create/comment/assign/close issue) |
| `vertex/` | Vertex AI Gemini endpoint + ADK runtime + interactive agent |
| `mcp/` | All three MCP servers: Mycelium custom MCP, GitLab OAuth MCP, MongoDB MCP |

See the README in each subfolder for individual commands and prerequisites.

---

## Prerequisites

All checks read from `.env` in the project root. Required variables:

```
GOOGLE_CLOUD_PROJECT=...
GOOGLE_CLOUD_LOCATION=us-central1
MONGODB_URI=mongodb+srv://...
GITLAB_TOKEN=glpat-...
GITLAB_PROJECT_ID=12345678
```

Optional:
```
GEMINI_MODEL=gemini-2.5-flash   # default
GOOGLE_CLOUD_STORAGE_BUCKET=... # only needed for deployment checks
```
