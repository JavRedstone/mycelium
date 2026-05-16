# Mycelium — Engineering Continuity Engine

An autonomous AI agent that maintains engineering knowledge continuity across team changes. It observes a GitLab repository, builds a knowledge graph in MongoDB, predicts continuity risks, and executes corrective actions — all on a configurable loop.

**Pipeline:** Observe Repo → Map Modules → Observe Graph → Analyze → Plan → Execute → Persist → Summary

---

## What It Does

Mycelium answers: *"If a developer left tomorrow, what knowledge would be lost, and who would be most at risk of being overwhelmed?"*

For each pipeline run it:

1. **Reads GitLab** — members, issues, MRs, commits, CODEOWNERS, CI pipeline status, MR approvals
2. **Maps module expertise** — per-directory commit attribution: who touched `app/`, `lib/`, `internal/`, etc.
3. **Reads the knowledge graph** — current risk scores, tracked developers, open tasks
4. **Analyzes risks** — Gemini identifies bus factor problems, dark knowledge zones, stalled work
5. **Plans actions** — Gemini decides what GitLab actions to take and what graph updates to write
6. **Executes** — Creates GitLab issues, assigns work, posts comments via the **official GitLab MCP server**
7. **Persists** — Writes developer nodes, module nodes, and contribution edges to MongoDB
8. **Rescores** — Recomputes continuity risk and bus factor for every module after new data arrives

---

## Fork-Based Repository Support

Mycelium explicitly handles fork-based contribution workflows, where the majority of commit history comes from **upstream authors** — contributors to the original project who are not current team members. These authors wrote code that is still running in production, but their knowledge lives only in the commit log.

Modules with high upstream-author concentration are flagged as **dark knowledge zones** and scored with a penalty above their internal-committer bus factor. This surfaces risks that member-only analysis would miss entirely.

---

## Requirements

- Python 3.12+
- MongoDB Atlas cluster (free tier works)
- GitLab account with a project and a personal access token (`api` scope)
- Google AI Studio API key (for Gemini)
- Node.js 18+ with `npx` — required for the MongoDB MCP server

---

## Setup

**1. Clone and create virtual environment**

```bash
cd mycelium
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
source .venv/bin/activate    # Mac/Linux
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure environment**

Copy `.env.example` to `.env` and fill in your values:

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | API key from [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `GEMINI_MODEL` | Model name (default: `gemma-3-27b-it`) |
| `MONGODB_URI` | Atlas connection string (`mongodb+srv://…`) |
| `MONGODB_DB` | Database name (default: `mycelium`) |
| `GITLAB_URL` | GitLab instance URL (default: `https://gitlab.com`) |
| `GITLAB_TOKEN` | Personal access token with `api` scope |
| `GITLAB_PROJECT_ID` | Numeric project ID (Settings → General → Project ID) |
| `AGENT_LOOP_INTERVAL_SECONDS` | Seconds between autonomous runs (default: `600`) |

> **Rate limits:** The free-tier Gemini API allows ~15 RPM. Mycelium runs 2–3 Gemini calls per pipeline cycle and backs off automatically (5 s → 15 s → 40 s). For higher throughput, use Vertex AI or a paid Google AI Studio plan.

**4. Verify connections**

```bash
python checks/check_mongo.py    # MongoDB
python checks/check_gitlab.py   # GitLab
python checks/check_gemini.py   # Gemini API
python checks/check_all.py      # All of the above
```

---

## Running Locally

```bash
uvicorn main:app --reload
```

The agent loop starts automatically on startup and runs every `AGENT_LOOP_INTERVAL_SECONDS`.
Trigger a manual run immediately via `POST /pipeline/run`.

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

---

## Project Structure

```
mycelium/
├── main.py                      # FastAPI app + agent loop scheduler
├── config/
│   └── settings.py              # Environment variable config
├── agent/
│   ├── pipeline.py              # Pipeline orchestrator (8 stages, SSE broadcast)
│   ├── analyst_agent.py         # Gemini risk assessment (analyze stage)
│   ├── planner_agent.py         # Gemini action planning (plan stage)
│   └── act_agent.py             # Gemini + GitLab MCP execution (execute stage)
├── gitlab_mcp/
│   ├── client.py                # GitLab observation layer (python-gitlab wrapper)
│   └── server.py                # Local MCP server for dev/testing (stdio transport)
├── graph/
│   ├── models.py                # Pydantic models: DeveloperNode, ModuleNode, ContributionEdge
│   └── knowledge_graph.py       # MongoDB operations (Motor async)
├── risk/
│   └── forecasting.py           # Bus factor + continuity risk scoring
├── checks/
│   ├── check_mongo.py           # MongoDB connection test
│   ├── check_gitlab.py          # GitLab connection test
│   ├── check_gemini.py          # Gemini API test
│   └── check_all.py             # Run all checks
└── Dockerfile                   # Cloud Run deployment
```

---

## Architecture

| Concern | Technology |
|---|---|
| Reasoning | Gemini (`gemma-3-27b-it`) via Google AI Studio API |
| GitLab actions | [GitLab MCP server](https://docs.gitlab.com/user/gitlab_duo/model_context_protocol/mcp_server/) (official, HTTP/streamable-HTTP transport) |
| MongoDB queries | [MongoDB MCP server](https://www.mongodb.com/docs/mcp-server/) (official, stdio via npx) |
| GitLab observation | `python-gitlab` (REST API wrapper) |
| Knowledge graph | MongoDB Atlas (Motor async driver) |
| API server | FastAPI + uvicorn |
| UI | Next.js + MUI (in `mycelium-ui/`) |
| Deployment | Cloud Run |

---

## Key Concepts

**Bus factor** — how many developers need to leave before a module loses all active knowledge holders. Computed from internal (project member) committers only; upstream authors do not count.

**Upstream authors** — contributors who appear in commit history but are not current project members. Common in forks of open-source projects. They wrote the code but are unreachable for knowledge transfer. Their modules are scored with a dark-knowledge penalty.

**Dark knowledge zone** — a module where the majority of commits were made by upstream authors. The code works, but its context and design intent lives outside the team.

**Continuity risk score** — 0.0–1.0. Combines bus factor, upstream author concentration, CODEOWNERS drift, and pipeline health signals.

---

## Deploying to Cloud Run

```bash
gcloud run deploy mycelium \
  --source . \
  --region us-central1 \
  --set-env-vars "GEMINI_MODEL=gemma-3-27b-it,MONGODB_DB=mycelium" \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,MONGODB_URI=mongodb-uri:latest,GITLAB_TOKEN=gitlab-token:latest,GITLAB_PROJECT_ID=gitlab-project-id:latest"
```

Store secrets before deploying:

```bash
echo -n "your-value" | gcloud secrets create gemini-api-key --data-file=-
echo -n "your-value" | gcloud secrets create mongodb-uri --data-file=-
echo -n "your-value" | gcloud secrets create gitlab-token --data-file=-
echo -n "your-value" | gcloud secrets create gitlab-project-id --data-file=-
```
