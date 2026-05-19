# Mycelium — Engineering Continuity Engine

Autonomous agent for engineering knowledge continuity. Observes a GitLab project,
maintains a knowledge graph in MongoDB, predicts continuity risks, and executes
corrective actions in GitLab — all on a closed loop.

Built on the hackathon-required Google agent stack:

```
google.adk.agents.Agent                              # ADK as agent construction framework
        ↓
vertexai.preview.reasoning_engines.AdkApp            # Vertex AI Agent Engine runtime
        ↓
Gemini (via Vertex AI — NOT AI Studio)
        ↓
MCPToolset(GitLab MCP, HTTP)  +  MCPToolset(MongoDB MCP, stdio)
        ↓
GitLab project state  +  MongoDB Atlas knowledge graph
```

**Pipeline:** Observe Repo → Map Modules → Investigate → Observe Graph → Analyze → Plan → Execute → Persist → Summary

---

## Why Agentic, Not Algorithmic

The first design instinct on a problem like *"score continuity risk"* is to write rules: `if bus_factor < 2: flag`, `if commits_behind >= 5: medium`, `if doc_score < 0.2: critical`. Mycelium deliberately rejects that approach. **Thresholds are confessions that the system can't reason.**

Numeric facts (bus_factor, external_ratio, commits_behind, file counts) live in the *measurement layer.* They're observations. Severity, urgency, and recommended action live in the *judgment layer* — and the judgment layer is the agent. The discipline:

| Algorithmic shortcut | What Mycelium does instead |
|---|---|
| `if bus_factor < 2: flag risk` | Member investigator subagent reads the directories that person uniquely touches, samples their recent commits and the surrounding docs, judges what knowledge actually walks out the door if they leave |
| `if commits_behind >= 5: medium` | Drift investigator subagent reads the actual upstream commits and judges urgency from content (CVE patch vs. typo fix) |
| `if doc_score < 0.2: critical` | Module investigator subagent recursively reads READMEs, source samples, and configuration; decides depth adaptively; assesses transferability from what's actually there |
| `score = 0.4*commits + 0.3*recency + 0.3*owners` | Analyst agent reasons over all signals together: numeric facts, investigator findings, raw content excerpts. No fixed weights, no hard cutoffs. |

The architectural reason this matters: the problem space is **partially observable** (ownership is implicit, not declared), **non-stationary** (teams and repos change continuously), and **latent** (the real system is cognitive — who *understands* what — not structural — who *touched* what). Rules operate on the structural surface and miss the underlying state. Agents operate on inference and reconstruct it.

A rule-based system can flag risk. An agentic system can **reconstruct hidden ownership, predict failure modes before they're observable, and actively reshape system state to prevent degradation.** See [`../PROJECT_IDEA.md`](../PROJECT_IDEA.md) for the full structural argument.

---

## What It Does

Mycelium answers: *"If a developer left tomorrow, what knowledge would be lost,
and which modules would be orphaned?"*

For each pipeline run it:

1. **Reads GitLab** — members, issues, MRs, commits, CODEOWNERS, CI pipeline status, MR approvals, fork divergence.
2. **Maps module expertise** — per-directory commit attribution: who touched `app/`, `lib/`, `internal/`, etc.
3. **Investigates** — spawns concurrent subagents that read actual file content (READMEs, source, configs) and reason about transferability. One subagent per high-attention member (sole contributors, recently inactive, recent joiners), one per flagged module (adaptive-depth recursive), one for fork divergence. **No thresholds — the subagents judge.**
4. **Reads the knowledge graph** — current risk scores, tracked developers, open tasks.
5. **Analyzes risks** (ADK + Vertex AI Gemini) — reasons over numeric signals + investigator findings + raw content excerpts. No hardcoded severity thresholds.
6. **Plans actions** (ADK + Vertex AI Gemini) — what GitLab actions to take and what graph updates to write.
7. **Executes** (ADK + Vertex AI Gemini + dual MCP) — the act agent queries the knowledge graph
   over the official MongoDB MCP server, then creates GitLab issues / posts comments / assigns
   work through the official GitLab MCP server, all in a single multi-turn reasoning loop.
8. **Persists** — Writes developer nodes, module nodes, and contribution edges to MongoDB.

---

## Google Stack Compliance

This project is built specifically to satisfy the Google Cloud Rapid Agent Hackathon 2026
requirements (see `../HACKATHON.md`):

| Required | How it's used in Mycelium |
|---|---|
| **Vertex AI SDK** (`google-cloud-aiplatform`) | `vertexai.init(...)` called in `agent/act_agent.py`, `analyst_agent.py`, `planner_agent.py`, and `deployment/deploy.py`. All Gemini traffic routes through Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=True`). |
| **Vertex AI Agent Engine** | Every agent call goes through `vertexai.preview.reasoning_engines.AdkApp`. `deployment/deploy.py` ships the act agent to Agent Engine via `vertexai.agent_engines.create()`. |
| **ADK** (`google.adk.agents.Agent`) | Three ADK agents — `mycelium_act_agent`, `mycelium_analyst_agent`, `mycelium_planner_agent`. |
| **Gemini via Vertex AI** | Default model `gemini-2.5-flash`, configurable via `GEMINI_MODEL`. |
| **Partner MCP servers** | GitLab MCP (HTTP, `/api/v4/mcp`) and MongoDB MCP (stdio, `@mongodb-js/mongodb-mcp-server`), wired into the act agent as two `MCPToolset` instances. |
| **Real-world actions** | GitLab issue creation, assignment, MR comments — all through the official GitLab MCP server. |

---

## Fork-Based Repository Support

Mycelium explicitly handles fork-based contribution workflows, where the majority
of commit history comes from **upstream authors** — contributors to the original
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
- Node.js 18+ with `npx` — required for the official MongoDB MCP server

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
| `GITLAB_TOKEN` | yes | Personal access token (`api` scope). |
| `GITLAB_PROJECT_ID` | yes | Numeric project ID (Settings → General → Project ID). |
| `AGENT_LOOP_INTERVAL_SECONDS` | no | Seconds between autonomous runs (default `300`). |

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

# Inspect a module — contributors, expertise, bus factor
python cli.py inspect module scripts

# Inspect a developer — expertise profile and module ownership
python cli.py inspect developer alex.chen

# Seed demo data (team | new_joiner | fading | sole_owner)
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

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/graph` | Full knowledge graph: modules with per-directory contributor lists |
| `GET` | `/snapshot` | Raw graph snapshot (developers, upstream authors, high-risk modules, open tasks) |
| `POST` | `/pipeline/run` | Trigger a pipeline run immediately |
| `GET` | `/pipeline/current` | Current run state (all stages + outputs) |
| `GET` | `/pipeline/history` | Last 20 run summaries |
| `GET` | `/pipeline/stream` | SSE stream of real-time pipeline events (used by the UI) |
| `GET` | `/logs/stream` | SSE stream of log entries (used by the UI) |

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
│   ├── analyst_agent.py             # ADK Agent — risk reasoning via Vertex AI Gemini
│   ├── planner_agent.py             # ADK Agent — corrective-action planning via Vertex AI Gemini
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

## Architecture

| Concern | Technology |
|---|---|
| Reasoning | Gemini (`gemini-2.5-flash` by default) via **Vertex AI** |
| Agent construction | **ADK** — `google.adk.agents.Agent` |
| Agent runtime | **Vertex AI Agent Engine** — `vertexai.preview.reasoning_engines.AdkApp` |
| GitLab actions | Official **GitLab MCP server** (HTTP) — wired in as an `MCPToolset` |
| MongoDB queries | Official **MongoDB MCP server** (stdio via `npx`) — wired in as an `MCPToolset` |
| GitLab observation | `python-gitlab` (REST wrapper) |
| Knowledge graph | MongoDB Atlas (Motor async driver) |
| API server | FastAPI + uvicorn |
| UI | Next.js + MUI (in `../mycelium-ui/`) |
| Deployment | Cloud Run (for FastAPI) + **Vertex AI Agent Engine** (for the act agent) |

---

## Key Concepts

**Bus factor** — how many developers need to leave before a module loses all
active knowledge holders. Computed from internal (project member) committers
only; upstream authors do not count.

**Upstream authors** — contributors who appear in commit history but are not
current project members. Common in forks of open-source projects. They wrote
the code but are unreachable for knowledge transfer. Their modules are scored
with a dark-knowledge penalty.

**Dark knowledge zone** — a module where the majority of commits were made by
upstream authors. The code works, but its context and design intent lives
outside the team.

**Continuity risk score** — 0.0–1.0. Combines bus factor, upstream author
concentration, CODEOWNERS drift, and pipeline health signals.

---

## Bus Factor: Internal Committers Only

Bus factor is calculated from **internal project members only**. External
contributors (upstream authors of a fork) are excluded regardless of their
commit count.

### Why

If a module's entire commit history was written by upstream contributors who
are not on your team, those people cannot transfer knowledge to you. They are
already gone. Their commits represent knowledge that exists only in the code
and has no organizational owner. Counting them toward bus factor would give a
false sense of safety.

### Example

Suppose `grzesiek.bizon` has 153 commits to `internal/` in a forked project's
history. If `grzesiek.bizon` is an upstream author (not a current project
member), the pipeline marks them as `external=True`. When bus factor for
`internal/` is computed:

```
internal contributors = [c for c in contributions if not c.external and c.commit_count > 0]
bus_factor(internal/) = len(internal contributors) = 0
```

Bus factor is 0 even though 153 commits exist. The module is a **dark knowledge
zone** — fully functional but organizationally orphaned.

This shows up in the Knowledge Graph UI: `internal/` has a bus_factor of 0 with
`grzesiek.bizon` listed under "Upstream Authors" (not "Contributors"), and the
module card shows a dark-knowledge warning.

### What the agent does with this

The analyst and planner agents receive bus_factor as a measurement signal, not a
decision rule. Bus_factor=0 for a module does not automatically create an issue.
The agents reason: is this module being actively changed? Does it have any docs?
Is there a fork-path to understanding it? The issue (if created) reflects that
full picture, not just the number.

---

## Demo Data System

Mycelium includes a seed system for populating MongoDB with realistic synthetic
team data — useful for demos, testing, and developing without waiting for a real
repository to accumulate multi-month history.

All seeded entries are flagged `demo: true` in MongoDB. They are:

- **Visible in the UI** — purple "demo" chip on every contributor row, module
  card, and React Flow node where a demo entry is involved
- **Excluded from agent context** — `snapshot()`, `list_developers()`, and
  `list_concentrated_modules()` all filter `{"demo": {"$ne": true}}`. Synthetic
  contributors never appear in generated GitLab issues.
- **Protected from pipeline overwrites** — `upsert_developer()` / `upsert_module()`
  / `upsert_contribution()` use `$setOnInsert` for the `demo` field, so a real
  pipeline run never flips `demo: true` to `false` on seeded entries.
- **Clearable in one command** — `python -m scripts.seed_scenarios --clear` or
  `DELETE /graph/demo` or the "Clear demo data" button in the UI.

See [`scripts/README.md`](scripts/README.md) for the full demo team roster,
module coverage matrix, and scenario commands.

### Demo API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/graph/demo` | Returns `{"has_demo": true/false}` |
| `DELETE` | `/graph/demo` | Deletes all `demo: true` documents from all collections |

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
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=us-central1,GEMINI_MODEL=gemini-2.5-flash,MONGODB_DB=mycelium,GOOGLE_GENAI_USE_VERTEXAI=True" \
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
