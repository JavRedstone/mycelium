# Mycelium - Engineering Continuity Engine

Autonomous agent for engineering knowledge continuity. Observes a GitLab project,
maintains a knowledge graph in MongoDB, predicts continuity risks, and executes
corrective actions in GitLab - all on a closed loop.

Built on the hackathon-required Google agent stack:

```
google.adk.agents.Agent                              # ADK as agent construction framework
        ↓
vertexai.preview.reasoning_engines.AdkApp            # Vertex AI Agent Engine runtime
        ↓
Gemini (via Vertex AI - NOT AI Studio)
        ↓
MCPToolset(GitLab MCP, HTTP)  +  MCPToolset(MongoDB MCP, stdio)
        ↓
GitLab project state  +  MongoDB Atlas knowledge graph
```

**Pipeline:** Observe → Model → Analyze → Decide → Act → Reflect → Persist → Summary

---

## Why Agentic, Not Algorithmic

The first design instinct on a problem like *"score continuity risk"* is to write rules: `if bus_factor < 2: flag`, `if commits_behind >= 5: medium`, `if doc_score < 0.2: critical`. Mycelium deliberately rejects that approach. **Thresholds are confessions that the system can't reason.**

Numeric facts (bus_factor, external_ratio, commits_behind, file counts) live in the *measurement layer.* They're observations. Severity, urgency, and recommended action live in the *judgment layer* - and the judgment layer is the agent. The discipline:

| Algorithmic shortcut | What Mycelium does instead |
|---|---|
| `if bus_factor < 2: flag risk` | Member investigator subagent reads the directories that person uniquely touches, samples their recent commits and the surrounding docs, judges what knowledge actually walks out the door if they leave |
| `if commits_behind >= 5: medium` | Drift investigator subagent reads the actual upstream commits and judges urgency from content (CVE patch vs. typo fix) |
| `if doc_score < 0.2: critical` | Module investigator subagent recursively reads READMEs, source samples, and configuration; decides depth adaptively; assesses transferability from what's actually there |
| `score = 0.4*commits + 0.3*recency + 0.3*owners` | Analyst agent reasons over all signals together: numeric facts, investigator findings, raw content excerpts. No fixed weights, no hard cutoffs. |

The architectural reason this matters: the problem space is **partially observable** (ownership is implicit, not declared), **non-stationary** (teams and repos change continuously), and **latent** (the real system is cognitive - who *understands* what - not structural - who *touched* what). Rules operate on the structural surface and miss the underlying state. Agents operate on inference and reconstruct it.

A rule-based system can flag risk. An agentic system can **reconstruct hidden ownership, predict failure modes before they're observable, and actively reshape system state to prevent degradation.** See [`../PROJECT_IDEA.md`](../PROJECT_IDEA.md) for the full structural argument.

---

## What It Does

Mycelium answers: *"If a developer left tomorrow, what knowledge would be lost,
and which modules would be orphaned?"*

For each pipeline run it:

1. **Observe** - Parallel snapshot of GitLab state (members, commits, CODEOWNERS, CI pipelines, MRs, issues, fork divergence) and the MongoDB knowledge graph. All reads happen here; no external calls in later stages.
2. **Model** - Builds the module map from CODEOWNERS + commit history; detects high-attention members and flagged modules; spawns concurrent Gemini Flash investigator subagents that read actual file content and reason about transferability. **No thresholds - the subagents judge.**
3. **Analyze** - Analyst agent (ADK + Vertex AI Gemini) synthesises investigator reports + graph snapshot into qualitative findings. No hardcoded severity thresholds.
4. **Decide** - Planner agent (ADK + Vertex AI Gemini) translates findings into concrete GitLab actions; deduplicates against issues that already exist in GitLab.
5. **Act** (ADK + Vertex AI Gemini + dual MCP) - Act agent executes the plan via the official GitLab MCP server (create issues, post comments, assign work) and queries the knowledge graph via the official MongoDB MCP server, all in a single multi-turn reasoning loop.
6. **Reflect** - Re-fetches GitLab state post-ACT and diffs against the OBSERVE baseline to verify what was actually created vs. what was pre-existing or duplicated. Annotates each finding with causal metadata (`actioned_at`, `pre_existing`, `duplicate_of`, `gitlab_iid`).
7. **Persist** - Writes developer nodes, module nodes, contribution edges, and REFLECT-annotated findings to MongoDB; refreshes bus-factor measurements on all modules.
8. **Summary** - Produces the human-readable run summary and writes the complete `pipeline_runs` document.

---

## Google Stack Compliance

This project is built specifically to satisfy the Google Cloud Rapid Agent Hackathon 2026
requirements (see `../HACKATHON.md`):

| Required | How it's used in Mycelium |
|---|---|
| **Vertex AI SDK** (`google-cloud-aiplatform`) | `vertexai.init(...)` called in `agent/act_agent.py`, `analyst_agent.py`, `planner_agent.py`, and `deployment/deploy.py`. All Gemini traffic routes through Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=True`). |
| **Vertex AI Agent Engine** | Every agent call goes through `vertexai.preview.reasoning_engines.AdkApp`. `deployment/deploy.py` ships the act agent to Agent Engine via `vertexai.agent_engines.create()`. |
| **ADK** (`google.adk.agents.Agent`) | Three ADK agents - `mycelium_act_agent`, `mycelium_analyst_agent`, `mycelium_planner_agent`. |
| **Gemini via Vertex AI** | Default model `gemini-2.5-flash`, configurable via `GEMINI_MODEL`. |
| **Partner MCP servers** | GitLab MCP (HTTP, `/api/v4/mcp`) and MongoDB MCP (stdio, `@mongodb-js/mongodb-mcp-server`), wired into the act agent as two `MCPToolset` instances. |
| **Real-world actions** | GitLab issue creation, assignment, MR comments - all through the official GitLab MCP server. |

---

## Fork-Based Repository Support

Mycelium explicitly handles fork-based contribution workflows, where the majority
of commit history comes from **upstream authors** - contributors to the original
project who are not current team members. These authors wrote code that is still
running in production, but their knowledge lives only in the commit log.

Modules with high upstream-author concentration are flagged as **dark knowledge
zones** and scored with a penalty above their internal-committer bus factor.

---

## Requirements

- Python 3.12+
- A Google Cloud project with Vertex AI enabled and Application Default Credentials configured (`gcloud auth application-default login`)
- MongoDB Atlas cluster (free tier works)
- GitLab account with a project and a personal access token (`api` scope)
- Node.js 18+ with `npx` - required for the official MongoDB MCP server

---

## Setup

**1. Create virtual environment and install**

```bash
cd mycelium
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
source .venv/bin/activate    # Mac/Linux
pip install -r requirements.txt
```

**2. Configure environment**

Copy `.env.example` to `.env` (or create one) and fill in:

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | yes | GCP project ID with Vertex AI enabled. |
| `GOOGLE_CLOUD_LOCATION` | no | Vertex AI region (default `us-central1`). |
| `GOOGLE_CLOUD_STORAGE_BUCKET` | deploy-only | GCS bucket name for Agent Engine staging (no `gs://`). |
| `GEMINI_MODEL` | no | Vertex-AI-served Gemini model (default `gemini-2.5-flash`). |
| `MONGODB_URI` | yes | Atlas connection string (`mongodb+srv://…`). |
| `MONGODB_DB` | no | Database name (default `mycelium`). |
| `GITLAB_URL` | no | GitLab instance URL (default `https://gitlab.com`). |
| `GITLAB_TOKEN` | yes | Service account token (`api` scope) - see **GitLab Service Account** below. |
| `GITLAB_PROJECT_ID` | yes | Numeric project ID (Settings → General → Project ID). |
| `GITLAB_BOT_USERNAME` | no | Service account username (default `mycelium-bot`). Change if you chose a different username. |
| `GITLAB_WEBHOOK_SIGNING_TOKEN` | no | Signing token set in GitLab → Settings → Webhooks. If set, every incoming webhook request is verified via HMAC-SHA256. Leave empty to skip verification (local dev only). |
| `CORS_ORIGINS` | no | Comma-separated list of allowed CORS origins. Set to `*` in production to allow Vercel and other frontends. Default: `http://localhost:3000,http://127.0.0.1:3000`. |
| `AGENT_LOOP_INTERVAL_SECONDS` | no | Seconds between autonomous runs (default `300`). |
| `DEMO_MODE` | no | Set to `true` to include demo-seeded data in agent snapshots and activate the `/demo/seed` endpoint. Default `false` - keep `false` in production. |

**GitLab Service Account** (recommended - keeps bot actions separate from human actions):

All automated GitLab writes (issue creation, comments, edits, closes) should run
under a dedicated project service account, not a personal token. This makes
automated actions immediately distinguishable in the issue tracker and scopes the
token to a single project.

1. In your GitLab project: **Settings → Members → Service accounts → Create service account**
   - Name: `Mycelium`, Username: `mycelium-bot`
2. Add the service account to the project with **Developer** access
   *(needed to edit and close issues created by others)*
3. Generate a **Personal Access Token** for the service account with `api` scope
4. Use that token as `GITLAB_TOKEN` in your `.env`

What this enables in code:
- `get_members()` excludes the bot so it never appears as a tracked team member
- `get_open_issues()` sets `bot_authored: true` on issues the bot created, so the planner knows it can freely edit or supersede them without touching human-authored issues

**Authenticate to Google Cloud** (ADC for local runs):

```bash
gcloud auth application-default login
gcloud config set project $GOOGLE_CLOUD_PROJECT
gcloud services enable aiplatform.googleapis.com
```

**3. Verify connections**

```bash
python checks/mongo/check_mongo.py          # MongoDB Atlas
python checks/gitlab/check_gitlab.py        # GitLab token + project (read)
python checks/gitlab/check_write.py         # GitLab write: create_issue → comment → assign → close
python checks/vertex/check_vertex.py        # Vertex AI Gemini endpoint
python checks/vertex/check_adk.py           # ADK Agent + AdkApp end-to-end
python checks/mcp/check_mcp_mycelium.py     # Mycelium MCP (read + write tools)
python checks/mcp/check_mcp_gitlab.py       # GitLab MCP (OAuth via mcp-remote)
python checks/mcp/check_mcp_mongo.py        # MongoDB MCP (stdio via npx)
python checks/check_all.py                  # All of the above
```

**4. Try a one-shot interactive question**

```bash
python checks/vertex/check_ask.py "Which modules have the highest dark knowledge risk?"
```

---

## CLI

`cli.py` provides a terminal interface to the running server. Run from the
`mycelium/` directory with the virtual environment active:

```bash
# Check connections and print config
python cli.py init

# Trigger a pipeline run (fire and forget)
python cli.py run

# Trigger a run and stream the Activity Feed live in the terminal
python cli.py run --watch

# Show graph state: concentrated modules, recent findings, run history
python cli.py status

# Generate an onboarding pack for a new team member (creates a GitLab issue)
python cli.py onboard marco.torres

# Generate an offboarding/handoff artifact
python cli.py offboard priya.sharma

# Inspect a module - contributors, expertise, bus factor
python cli.py inspect module scripts

# Inspect a developer - expertise profile and module ownership
python cli.py inspect developer alex.chen

# Seed demo data - requires DEMO_MODE=true in .env (team | new_joiner | fading | sole_owner)
python cli.py demo seed team

# Clear all demo entries from the graph
python cli.py demo clear

# Replay the last pipeline run's activity stream
python cli.py replay

# Replay a specific run at 2× speed
python cli.py replay --run-id <uuid> --speed 2.0
```

Override the server URL with `--url` or the `MYCELIUM_URL` environment variable:

```bash
MYCELIUM_URL=https://mycelium.example.com python cli.py status
```

---

## Running Locally

```bash
uvicorn main:app --reload
```

The agent loop starts automatically on startup and runs every
`AGENT_LOOP_INTERVAL_SECONDS`. Trigger a manual run immediately via
`POST /pipeline/run`.

### API Endpoints

Grouped by what they power in the UI. All defined in [`main.py`](main.py).

**Health / Configuration**

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check - returns `{"status": "ok"}`. |
| `GET` | `/config` | Non-sensitive runtime settings (GCP project, region, Gemini model, GitLab URL/project, MongoDB DB, pipeline-loop flag/interval, demo mode). Drives the Configuration page and gates demo controls in the UI. |
| `GET` | `/project` | GitLab project metadata - name, namespace, URL, default branch, stars, forks. |

**Knowledge graph (read)**

| Method | Path | Description |
|---|---|---|
| `GET` | `/graph` | Full graph: developers, upstream authors, modules with per-module contribution lists, concentrated modules, recent findings. The Knowledge Graph and Repository pages read this. |
| `GET` | `/snapshot` | Compact graph snapshot (no per-module contribution edges) used by the agents and lighter UI views. |
| `GET` | `/developers` | All developers - internal + upstream - including demo-flagged entries. |
| `GET` | `/developers/busfactor?username=…` | Per-module breakdown for one developer: their expertise share, the bus-factor threshold position (internal), or the dark-knowledge view (external). Query param (not path) because GitLab usernames can contain slashes. Powers the bus-factor drawer. |
| `GET` | `/graph/contribution-history?module_path=&developer_username=` | Monthly commit counts per `(developer, module, year_month)` - the backbone of the Repo History timeline. |

**Settings (graph-level overrides)**

| Method | Path | Description |
|---|---|---|
| `GET` | `/settings/fork-date` | Effective fork date - the override stored in MongoDB or the upstream GitLab `project.created_at` fallback. |
| `POST` | `/settings/fork-date` | Set or clear the override (`{"date": "YYYY-MM-DD"}` or `{"date": null}`). |

**Pipeline control**

| Method | Path | Description |
|---|---|---|
| `POST` | `/pipeline/run` | Kick off a pipeline run immediately. Returns `409` if a run is already in flight. |
| `POST` | `/pipeline/stop` | Cooperatively cancel the running pipeline. |
| `GET` | `/pipeline/current` | Snapshot of the in-flight run (stage list, statuses, outputs). |
| `GET` | `/pipeline/history?limit=50` | Recent run summaries, MongoDB-backed with in-memory fallback. |
| `GET` | `/pipeline/{run_id}/events` | All activity events captured for a specific historical run - used by the Timeline replay. |
| `GET` | `/pipeline/stream` | **SSE** - pushes pipeline-run state changes (stage transitions, summaries). |
| `GET` | `/pipeline/activity` | Buffered structured activity events for the most recent run. |
| `GET` | `/pipeline/activity/stream` | **SSE** - live structured agent activity (thinking, tool calls, subagent spawns). |
| `GET` | `/logs/stream` | **SSE** - raw uvicorn + Python log lines, in-memory buffer of last 500. |

**Agent output**

| Method | Path | Description |
|---|---|---|
| `GET` | `/actions?limit=200&run_id=` | What the act agent has actually done in GitLab (issue creates, comments, edits, closes). Powers the Actions page. |
| `GET` | `/findings?limit=200&run_id=` | Qualitative continuity findings produced by the analyst. Powers Investigations and parts of the Knowledge Graph. |

**Direct agent triggers (bypass full pipeline)**

| Method | Path | Description |
|---|---|---|
| `POST` | `/onboard/{username}` | Generate an onboarding pack for a developer and post it to GitLab. |
| `POST` | `/offboard/{username}` | Generate an offboarding/handoff artifact for a leaving developer. |

**GitLab webhooks**

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhooks/gitlab` | Receives GitLab webhook events and triggers the pipeline. Verifies the HMAC-SHA256 `webhook-signature` header when `GITLAB_WEBHOOK_SIGNING_TOKEN` is set. |

**Demo data (gated by `DEMO_MODE=true`)**

| Method | Path | Description |
|---|---|---|
| `GET` | `/graph/demo` | `{"has_demo": bool, "demo_mode": bool}` - both flags drive UI button visibility. |
| `POST` | `/demo/seed/{scenario}` | Seed `team` / `new_joiner` / `fading` / `sole_owner` / `clear`. Returns `403` if demo mode is disabled. |
| `DELETE` | `/graph/demo` | Delete every `demo: true` document across collections. Returns `403` if demo mode is disabled. |

---

## GitLab Webhooks

Mycelium can react to repository events in real time rather than waiting for the
scheduled loop. When a webhook fires, the pipeline runs immediately.

### Setup

**1. Generate a signing token**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Add it to `mycelium/.env`:

```
GITLAB_WEBHOOK_SIGNING_TOKEN=<your_generated_token>
```

**2. Configure the webhook in GitLab**

Go to your GitLab project → **Settings → Webhooks → Add new webhook**:

| Field | Value |
|---|---|
| **URL** | `https://<your-cloud-run-url>/webhooks/gitlab` |
| **Signing token** | The token from step 1 |
| **Secret token** | Leave blank (signing token is more secure) |
| **SSL verification** | ✅ Enabled |

Enable these trigger checkboxes:

- ✅ **Push events** — new commits
- ✅ **Comments** — notes on issues / MRs
- ✅ **Work item events** — issue created, updated, closed
- ✅ **Merge request events** — MR opened, merged, closed
- ✅ **Pipeline events** — CI status changes

Click **Add webhook**, then **Test** to verify the endpoint responds with `{"status":"triggered"}` or `{"status":"ignored"}`.

**3. Redeploy the backend**

```bash
python deploy.py backend
```

### How it works

GitLab sends a `POST` to `/webhooks/gitlab` with an HMAC-SHA256 signature in
the `webhook-signature` header. The backend:

1. Verifies the signature against `GITLAB_WEBHOOK_SIGNING_TOKEN`
2. Checks the `X-Gitlab-Event` header against the list of trigger events
3. If the pipeline is idle → starts a run immediately
4. If the pipeline is already running → logs the event and returns `{"status":"queued"}`
   (the scheduled loop will pick it up on its next cycle)

Events that trigger a run: `push`, `merge_request`, `issue` / `work_item`, `note` (comments), `member`, `pipeline`.

---

## Project Structure

```
mycelium/
├── main.py                          # FastAPI app + agent loop scheduler
├── config/
│   └── settings.py                  # Vertex AI + MongoDB + GitLab config
├── agent/
│   ├── pipeline.py                  # 9-stage orchestrator (SSE broadcast)
│   ├── act_agent.py                 # ADK Agent + Mycelium/GitLab/MongoDB MCP, wrapped in AdkApp
│   ├── analyst_agent.py             # ADK Agent - risk reasoning via Vertex AI Gemini
│   ├── planner_agent.py             # ADK Agent - corrective-action planning via Vertex AI Gemini
│   ├── investigator.py              # Concurrent subagents: member, module (recursive), drift
│   └── json_utils.py                # Robust JSON extraction helper
├── connectors/
│   ├── gitlab_client.py             # python-gitlab observation layer (read + write)
│   └── mcp_server.py                # Mycelium custom MCP server (graph + GitLab write tools)
├── graph/
│   ├── models.py                    # Pydantic models for graph entities
│   └── knowledge_graph.py           # MongoDB operations (Motor async)
├── risk/
│   └── forecasting.py               # Bus factor + base continuity-risk measurement (numeric only)
├── checks/                          # Connection / runtime smoke tests
│   ├── check_all.py                 # Run every check
│   ├── show.py                      # Read-only data inspector
│   ├── gitlab/
│   │   ├── check_gitlab.py
│   │   └── check_write.py           # create_issue → comment → assign → close (cleanup)
│   ├── mcp/
│   │   ├── check_mcp.py
│   │   ├── check_mcp_gitlab.py
│   │   ├── check_mcp_mongo.py
│   │   └── check_mcp_mycelium.py
│   ├── vertex/
│   │   ├── check_vertex.py
│   │   ├── check_adk.py
│   │   └── check_ask.py             # Interactive ADK agent runner
│   └── mongo/
│       └── check_mongo.py
├── deployment/
│   └── deploy.py                    # Deploy act agent to Vertex AI Agent Engine
├── tests/
│   ├── test_unit.py
│   └── test_integration.py
└── Dockerfile
```

---

## Module Function Reference

The key functions inside each Python module, grouped by responsibility.
For full signatures and behaviour, read the source - this is an
orientation map, not exhaustive API docs.

### `main.py` - FastAPI server + agent loop

- `lifespan(_app)` - startup hook: registers the activity-bus event loop, sets up MongoDB indexes, schedules `run_loop()` as a background task; cancels everything on shutdown.
- `run_loop()` - autonomous pipeline scheduler. Calls `pipeline.run()` every `AGENT_LOOP_INTERVAL_SECONDS` until cancelled. No-op when `PIPELINE_LOOP_ENABLED=false`.
- The endpoint functions are thin adapters that delegate to `graph.*` (MongoDB), `pipeline.*` (runs), `gitlab.*` (project metadata), or `activity_bus.*` (SSE streams). One helper class `_UILogHandler` injects every uvicorn/Python log line into an in-memory deque the `/logs/stream` endpoint streams over SSE.

### `agent/pipeline.py` - the 8-stage orchestrator

The full pipeline lives on `PipelineRunner`. Stages run sequentially; each
records timings, status, and a JSON payload that flows to subsequent stages
and the UI via `_broadcast()`.

| Stage | Method | What it does |
|---|---|---|
| 1. Observe | `_observe()` | Parallel `asyncio.gather` of `gitlab.snapshot()` + `graph.snapshot()`. Captures GitLab baseline (`issue_iids`, `mr_iids`) for REFLECT to diff against. All external reads happen here. |
| 2. Model | `_model()` | Walks top-level directories, builds module map + commit attribution; detects high-attention members; spawns concurrent investigator subagents (member / module / drift). |
| 3. Analyze | `_analyze()` | Calls `_run_investigation()` then `_run_interpretation()`: investigator subagents read actual file content; analyst agent synthesises reports into qualitative findings. |
| 4. Decide | `_decide()` | Calls `planner_agent.plan_async()` - translates findings into concrete actions; deduplicates `create_issue` actions against pre-existing open issues captured at OBSERVE. |
| 5. Act | `_act()` | Calls `act_agent.act()` - ADK + dual MCP loop; creates GitLab issues / posts comments / assigns work through the official GitLab MCP server. |
| 6. Reflect | `_reflect()` | Re-fetches GitLab state post-ACT; diffs against OBSERVE baseline; annotates each finding with `actioned_at`, `pre_existing`, `duplicate_of`, `gitlab_iid`; stores in `self._interpretation["annotated_findings"]`. |
| 7. Persist | `_persist()` | Writes developer/module/contribution updates, monthly history records, and REFLECT-annotated findings to MongoDB; refreshes bus factors via `_refresh_bus_factors()`. |
| 8. Summary | `_summary()` | Writes `pipeline_runs` document with stage outputs + activity events. |

Cross-cutting:
- `subscribe()` / `unsubscribe()` / `_broadcast()` - SSE fan-out queues for `/pipeline/stream`.
- `request_cancel()` - cooperative cancellation; checked between stages.
- `_parse_iso_dt(s)` - module-level helper converting GitLab's ISO-8601 strings (with `"Z"` suffix or `"+00:00"`) into `datetime`, used when propagating `first_seen` / `last_seen` from commit data to `DeveloperNode`.

### `agent/analyst_agent.py` - qualitative risk reasoning

- `analyze(repo_snapshot, graph_snapshot, investigator_findings)` - sync entry point.
- `analyze_async(...)` - async wrapper used by the pipeline.
- `_run_through_adk(prompt, stage_id)` - runs the prompt through ADK + Vertex AI Gemini, falling back to a plain Gemini call if Agent Engine is unreachable. Streams thinking text into `activity_bus` so the UI shows it live.
- `_fallback_risk_assessment(...)` - last-resort numeric summary (no LLM) when both ADK and direct Gemini fail.
- In demo mode (`settings.demo_mode and graph contains demo: true`) injects a `demo_note` that explicitly forbids sole-contributor findings derived from raw git counts - see `mycelium-ui/.../KnowledgeGraph.tsx` for why this matters.

### `agent/planner_agent.py` - corrective-action planning

- `plan(interpretation, repo_snapshot, graph_snapshot)` - sync entry.
- `plan_async(...)` - async wrapper.
- Same ADK-then-Gemini-then-fallback pattern as the analyst. Output is a list of proposed GitLab actions (create issue / comment / assign / close) that the act agent will execute.

### `agent/act_agent.py` - multi-turn execution via dual MCP

- `build_root_agent()` - assembles the ADK `Agent` with three `MCPToolset` instances: Mycelium MCP, GitLab MCP, MongoDB MCP. Returns an `AdkApp`-ready agent.
- `_gitlab_toolset() / _mongodb_toolset() / _mycelium_toolset()` - toolset factories. Each one configures connection + tool allowlists.
- `act(interpretation, repo_snapshot, plan)` - runs the agent loop. The agent first queries MongoDB to confirm graph state, then creates GitLab issues, comments, and assignments. Every tool call is captured via `_collect_tool_calls()` and `_collect_trace()` and pushed to `activity_bus` for the UI.
- `_direct_execute_actions(...)` - fallback path that executes planned actions directly through `gitlab_client` when MCP is unavailable.
- `_audit_boundary(...)` - guard that prevents the agent from touching issues not authored by the bot user.

### `agent/investigator.py` - concurrent subagent investigations

- `investigate_member(username, ...)` - reads the directories a high-attention person uniquely touches, samples their commits and surrounding docs, judges what knowledge actually leaves with them.
- `investigate_module(path, ...)` - recursive adaptive-depth read: starts at the module root, decides how deep to go based on what it finds (READMEs, docstring density, config files), returns a transferability judgment.
- `investigate_drift()` - reads actual upstream commits the fork hasn't merged, judges urgency from content (security patch vs typo).
- `_read_directory_files(...)` - controlled directory traversal with file-size limits.
- `_format_files_for_prompt(tree)` - pretty-prints a file tree for prompt context.
- `_count_files(tree)` - used to decide recursion depth.

### `agent/activity_bus.py` - SSE fan-out for agent events

- `bus.publish(event)` - broadcast a structured agent event.
- `bus.subscribe()` / `bus.unsubscribe(q)` - per-client async queue.
- `bus.history()` - buffered events for the most recent run (lets clients catch up on connect).

### `connectors/gitlab_client.py` - read + write layer

- `get_members()` - project members, with `mycelium-bot` filtered so it never appears as a "tracked" person.
- `get_open_issues()` - open issues, with `bot_authored: true` on the ones the service account created (so planner can edit them safely).
- `get_open_merge_requests()` - open MRs + approvals.
- `get_recent_commits(since)` - flat commit list.
- `get_commit_contributors(ref)` - unique authors with commit counts and `external` flag.
- `get_repository_tree(path, recursive)` - directory listing.
- `get_top_level_dirs()` - root directory names (drives Map Modules).
- `get_directory_contributors(path, max_commits)` - per-directory commit attribution.
- `get_directory_contributors_with_history(path, max_commits)` - same plus `monthly_counts: {YYYY-MM: N}` *and* exact `first_commit_at` / `last_commit_at` per author. The exact dates flow through to `DeveloperNode.first_seen` / `last_seen` and let the timeline draw bars that snap to the actual commit dates instead of month boundaries.
- `get_codeowners()` - parsed `CODEOWNERS` file from common locations.
- `get_pipeline_status(ref, limit)` - CI pipeline list.
- `_is_member(name, email)` - internal lookup that decides `external` flag based on the cached member set. Membership cache is invalidated by `invalidate_cache()`.

### `connectors/mcp_server.py` - Mycelium's custom MCP server

Surfaces three tool families to the act agent: knowledge-graph reads
(modules, developers, contributions), GitLab writes (issue/comment/assign),
and continuity artefact generators (onboarding pack, offboarding artifact).

### `graph/models.py` - Pydantic graph entities

`DeveloperNode`, `ModuleNode`, `ContributionEdge`, `ContributionHistory`,
`TaskNode`, `Finding`, `ActionRecord`. Datetime fields are `Optional` and
default to `None`; the upsert logic in `KnowledgeGraph` uses `$min` / `$max`
to preserve the best value across pipeline runs (so a later run can't
clobber an earlier exact `first_seen` with `None`).

### `graph/knowledge_graph.py` - MongoDB Motor wrapper

Async I/O for every collection. Key methods grouped by area:

- **Developers** - `upsert_developer`, `get_developer`, `list_developers`, `list_external_contributors`, `list_upstream_authors`. `upsert_developer` uses `$min` on `first_seen` and `$max` on `last_seen` so incremental runs widen the observed window monotonically.
- **Modules** - `upsert_module`, `get_module`, `list_modules`, `list_concentrated_modules`.
- **Contributions** - `upsert_contribution`, `get_module_contributors`, `get_developer_modules`.
- **Contribution history** - `upsert_contribution_history`, `get_contribution_history` (the monthly buckets the timeline reads).
- **Tasks** - `upsert_task`, `list_open_tasks`.
- **Findings / actions** - `insert_finding` / `list_findings`, `insert_action` / `list_actions`.
- **Pipeline runs** - `save_run`, `get_latest_run`, `list_runs`.
- **Activity events** - `save_activity_events`, `list_activity_events` (for run replay).
- **Settings** - `get_fork_date_override`, `set_fork_date_override`.
- **Demo lifecycle** - `delete_demo_data` (bulk-removes everything flagged `demo: true`), `has_demo_data`.
- **Snapshot** - `snapshot()` composes the canonical agent-facing view.

### `risk/forecasting.py` - bus factor measurement

- `compute_bus_factor(contributions)` - sorts internal contributors by `expertise_score` desc, walks until cumulative coverage reaches 80%, returns the count. Returns `0` if no internal contributors exist (dark knowledge zone). Used by `pipeline._refresh_bus_factors()` and the `/developers/busfactor` endpoint.

### `checks/show.py` - read-only data inspector (also a CLI subcommand)

- `inspect_module(graph, path)` - module → contributors with bus-factor bars.
- `inspect_developer(graph, username)` - developer → modules they hold + threshold position.
- `inspect_busfactor(graph)` - every module sorted by bus factor with per-contributor bars (CLI mirror of the UI Knowledge Graph view).
- `_bus_factor_breakdown(contribs)` - shared helper that annotates each contributor with `share_pct`, `cumulative_pct`, `in_bus`.

### `scripts/seed_scenarios.py` - demo team seeder

Four scenario functions plus `clear_all()`. Each function seeds developers,
contributions, modules, contribution history, and a fork-date override
flagged `demo: true`. Used by `POST /demo/seed/{scenario}` and by the
"Seed demo data" menu in the Knowledge Graph UI.

| Scenario | Use case |
|---|---|
| `team` | Full 4-person team with mixed bus factors - the default demo. |
| `new_joiner` | One person hasn't accumulated expertise yet. |
| `fading` | A senior contributor going quiet - sets up the analyst's "fading_contributor" finding. |
| `sole_owner` | One person owns a critical module alone - bus factor 1 scenario. |

---

## UI ↔ Backend Mapping

Quick lookup: which UI page reads which endpoint(s).

| UI page | Backend endpoints |
|---|---|
| `/repo` (Repository) | `GET /graph`, `GET /developers` |
| `/history` (Repo History) | `GET /developers`, `GET /graph`, `GET /settings/fork-date`, `GET /graph/contribution-history` |
| `/graph` (Knowledge Graph) | `GET /graph`, `GET /config` (for demo gate), `GET /graph/demo`, `GET /developers/busfactor?username=…`, `POST /demo/seed/{scenario}`, `DELETE /graph/demo` |
| `/pipeline` (Pipeline) | `GET /pipeline/current`, `GET /pipeline/history`, `POST /pipeline/run`, `POST /pipeline/stop`, `GET /pipeline/stream` (SSE), `GET /logs/stream` (SSE) |
| `/activity` (Agent Activity) | `GET /pipeline/activity`, `GET /pipeline/activity/stream` (SSE) |
| `/logs` (Agent Logs) | `GET /logs/stream` (SSE) |
| `/actions` (Actions) | `GET /actions` |
| `/timeline` (Timeline) | `GET /pipeline/history`, `GET /actions`, `GET /findings`, `GET /pipeline/{run_id}/events` |
| `/investigations` (Investigations) | `GET /findings` |
| `/analytics` (Analytics) | `GET /graph`, `GET /findings`, `GET /actions` |
| `/config` (Configuration) | `GET /config`, `GET /settings/fork-date`, `POST /settings/fork-date` |

---

## Architecture

| Concern | Technology |
|---|---|
| Reasoning | Gemini (`gemini-2.5-flash` by default) via **Vertex AI** |
| Agent construction | **ADK** - `google.adk.agents.Agent` |
| Agent runtime | **Vertex AI Agent Engine** - `vertexai.preview.reasoning_engines.AdkApp` |
| GitLab actions | Official **GitLab MCP server** (HTTP) - wired in as an `MCPToolset` |
| MongoDB queries | Official **MongoDB MCP server** (stdio via `npx`) - wired in as an `MCPToolset` |
| GitLab observation | `python-gitlab` (REST wrapper) |
| Knowledge graph | MongoDB Atlas (Motor async driver) |
| API server | FastAPI + uvicorn |
| UI | Next.js + MUI (in `../mycelium-ui/`) |
| Deployment | Cloud Run (for FastAPI) + **Vertex AI Agent Engine** (for the act agent) |

---

## Key Concepts

**Bus factor** - the minimum number of internal contributors whose combined commit
expertise covers at least 80% of a module's total expertise. Computed from
project members only; upstream authors do not count. A bus factor of 1 means one
person's departure drops the module below 80% internal coverage.

**Upstream authors** - contributors who appear in commit history but are not
current project members. Common in forks of open-source projects. They wrote
the code but are unreachable for knowledge transfer. Their modules are flagged
as dark knowledge zones.

**Dark knowledge zone** - a module where the majority of commits were made by
upstream authors. The code works, but its context and design intent lives
outside the team.

---

## Bus Factor: Definition and Design Decisions

### What it measures

```
bus_factor(module) = min number of internal contributors
                     whose combined expertise_score covers >= 80% of module total
```

Contributors are sorted by expertise score descending. The bus factor is the
index at which the cumulative sum first reaches 80%. This is a **count of
people**, not a score.

### The 80% threshold

The 80% threshold is borrowed from empirical software engineering research on
contributor concentration:

- Ferreira et al. (2019) *"An Analysis of the Bus Factor in Open Source
  Projects"* studies both 50% and 80% thresholds across hundreds of OSS
  projects. They find 80% is the more useful threshold because:
  - 50% triggers too easily (any module with one dominant committer flags, even
    if three others have partial knowledge)
  - 90%–100% triggers too late (misses genuinely fragile situations where one
    person holds the large majority of understanding)
  - 80% maps naturally to the **Pareto principle**: in practice, 80% of
    meaningful understanding of a module is held by a small number of its
    authors, and losing that group is what creates operational risk

- The remaining 20% is recoverable: a developer unfamiliar with a module can
  read the code, documentation, and commit history to reconstruct understanding.
  The 80% threshold approximates the point at which that reconstruction cost
  becomes prohibitive.

- Alternative thresholds we considered:

  | Threshold | Problem |
  |---|---|
  | 50% | Flags any module with one dominant committer regardless of team depth - too noisy |
  | 90% | Only triggers on near-total concentration - misses the practical risk zone |
  | 100% | Requires sole contributor - ignores 2-person fragility |
  | 80% | Covers the practical "hit by a bus" scenario: one person's departure breaks the team's ability to work confidently in the module |

### Why internal-only

Bus factor is calculated from **internal project members only**. External
contributors (upstream authors of a fork) are excluded regardless of commit
count.

If a module's entire commit history was written by upstream contributors who
are not on your team, those people cannot transfer knowledge to you - they are
already gone. Counting them toward bus factor would give a false sense of
safety. Their commits represent knowledge that exists only in the code, with no
organizational owner.

### Example

Suppose `grzesiek.bizon` has 153 commits to `internal/` in a forked project's
history. If `grzesiek.bizon` is an upstream author (not a current project
member), the pipeline marks them `external=True`. When bus factor for
`internal/` is computed:

```python
internal = [c for c in contributions if not c.external and c.commit_count > 0]
bus_factor = compute_bus_factor(internal)   # returns 0 - no internal committers
```

Bus factor is 0 even though 153 commits exist. The module is a **dark knowledge
zone** - fully functional but organizationally orphaned.

This shows up in the Knowledge Graph UI: `internal/` has `bus_factor=0` with
`grzesiek.bizon` listed under "Upstream Authors", and the module card shows a
dark-knowledge warning.

### Expertise score

Each contributor's `expertise_score` is their proportional share of a module's
total commit count (normalised to 1.0 for the top contributor). This is a
structural fact, not a judgment. The analyst agent uses bus factor as one signal
among many when it reasons about actual risk.

### What the agent does with this

Bus factor is a **measurement**, not a decision rule. Bus factor 1 does not
automatically create an issue. The analyst reasons: is this module being
actively changed? Are there docs? Is the sole committer still active? The
planner decides whether to act and what form the action takes.

A bus factor of 1 on a module with excellent documentation and a stable,
long-tenured author is different from bus factor 1 on an undocumented module
whose sole contributor has been inactive for 60 days. The number alone cannot
distinguish these. The agent can.

### CLI inspection

```bash
# Bus-factor breakdown for every module (sorted from most concentrated)
python checks/show.py --busfactor

# Drill into one developer: which modules are they in the 80% threshold for?
python checks/show.py --dev <username>
```

---

## Demo Data System

Mycelium includes a seed system for populating MongoDB with realistic synthetic
team data - useful for demos, testing, and developing without waiting for a real
repository to accumulate multi-month history.

All seeded entries are flagged `demo: true` in MongoDB. Whether they influence
the pipeline agents is controlled by the `DEMO_MODE` environment variable.

| `DEMO_MODE` | Agent behaviour |
|---|---|
| `false` (default) | Demo entries are excluded from all graph snapshots - agents only reason over real data. Safe for production. |
| `true` | Demo entries are included in the snapshot and a note is injected into analyst/planner prompts instructing them to treat demo contributors as real. Use during demos and development. |

All seeded entries are:

- **Visible in the UI** - purple "demo" chip on every contributor row, module
  card, and React Flow node where a demo entry is involved
- **Protected from pipeline overwrites** - `upsert_developer()` / `upsert_module()`
  / `upsert_contribution()` use `$setOnInsert` for the `demo` field, so a real
  pipeline run never flips `demo: true` to `false` on seeded entries.
- **Clearable in one command** - `python -m scripts.seed_scenarios --clear` or
  `DELETE /graph/demo` or the "Clear demo data" button in the UI.

See [`scripts/README.md`](scripts/README.md) for the full demo team roster,
module coverage matrix, and scenario commands.

### Demo API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/graph/demo` | Returns `{"has_demo": true/false}` |
| `DELETE` | `/graph/demo` | Deletes all `demo: true` documents from all collections |
| `POST` | `/demo/seed/{scenario}` | Seeds a scenario (`team`, `new_joiner`, `fading`, `sole_owner`). **Requires `DEMO_MODE=true`** - returns `403` otherwise. |

---

## Deploying

### 1. Act agent → Vertex AI Agent Engine

```bash
# Set up GCS staging bucket once
gsutil mb -p $GOOGLE_CLOUD_PROJECT -l us-central1 gs://$GOOGLE_CLOUD_STORAGE_BUCKET

# Deploy the act agent (wraps root_agent in AdkApp and ships it)
python deployment/deploy.py --create

# List / delete
python deployment/deploy.py --list
python deployment/deploy.py --delete --resource_id <projects/.../reasoningEngines/...>
```

### 2. FastAPI front → Cloud Run

```bash
gcloud run deploy mycelium \
  --source . \
  --region us-central1 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=us-central1,GEMINI_MODEL=gemini-2.5-flash,MONGODB_DB=mycelium,GOOGLE_GENAI_USE_VERTEXAI=True,DEMO_MODE=false" \
  --set-secrets "MONGODB_URI=mongodb-uri:latest,GITLAB_TOKEN=gitlab-token:latest,GITLAB_PROJECT_ID=gitlab-project-id:latest"
```

Store secrets first:

```bash
echo -n "your-value" | gcloud secrets create mongodb-uri --data-file=-
echo -n "your-value" | gcloud secrets create gitlab-token --data-file=-
echo -n "your-value" | gcloud secrets create gitlab-project-id --data-file=-
```

Cloud Run's runtime service account needs the **Vertex AI User** role
(`roles/aiplatform.user`).

---

## Prior Art and Research References

### Bus factor / truck factor

The term originates from a 1994 mailing-list discussion and was popularized in
software engineering as a measure of risk concentration: how many contributors
could be "hit by a bus" before a project loses the ability to continue? Later
formalized in empirical research:

- Ferreira et al. (2019) *"An Analysis of the Bus Factor in Open Source
  Projects"* - systematic study of 80% and 50% thresholds across hundreds of OSS
  repositories. Source of the 80% threshold used by this system.
- Cosentino et al. (2015) *"Findings from GitHub: Methods, Datasets and
  Limitations"* - early large-scale contributor concentration analysis.

Mycelium's bus factor computation is described in detail in the
[Bus Factor: Definition and Design Decisions](#bus-factor-definition-and-design-decisions)
section above.

---

### Code ownership / CODEOWNERS

GitHub introduced the `CODEOWNERS` file format (2017); GitLab adopted it
shortly after. There is no single canonical academic paper - the practice
emerged from industry tooling, not research.

The limitation CODEOWNERS has is central to this system's design: declared
ownership is static metadata. It records who *should* review changes, not who
*understands* the code. The two diverge quickly as teams and codebases evolve.

Mycelium treats inferred ownership (derived from contribution density, recency,
and review behavior) as the authoritative signal. CODEOWNERS data is ingested
as one input to the pipeline's `observe_repo` stage but is not treated as ground truth.

---

### Knowledge transfer risk

Studied extensively in the software engineering literature under the labels
"code ownership," "developer expertise," and "knowledge concentration":

- **Rigby & Bird (2013)** *"Convergent Contemporary Software Peer Review
  Practices"*, FSE 2013 - analysis of code ownership and review patterns across
  multiple large software projects; establishes the relationship between
  concentrated ownership and knowledge transfer risk.
- Bird et al. (2011) *"Don't Touch My Code! Examining the Effects of Ownership
  on Software Quality"*, ESEC/FSE 2011 - empirical evidence that low ownership
  breadth correlates with higher defect rates.

These are the academic grounding for the `knowledge_concentration` and
`undeclared_ownership` concern types used by the analyst agent.

---

### Contributor departure risk

Studied under the label "developer turnover" in Mining Software Repositories
(MSR) literature:

- Turnover impact on software projects is documented in several MSR studies
  showing that contributor loss on modules with low ownership breadth
  significantly increases defect probability and slows development velocity.
- Rigby & Bird (2013) (cited above) also covers the review ownership patterns
  that predict knowledge loss risk when contributors leave.

The `fading_contributor` concern type models early-stage departure risk:
a contributor whose activity has declined below a threshold that suggests
they are no longer actively maintaining their knowledge of a module.
