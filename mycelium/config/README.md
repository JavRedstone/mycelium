# config/

Runtime configuration loaded from environment variables.

---

## settings.py

All configuration lives in `Settings`. A `.env` file in the project root is
loaded automatically via `python-dotenv`.

### Required variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID for Vertex AI |
| `MONGODB_URI` | MongoDB connection string (Atlas `+srv` or direct) |
| `GITLAB_TOKEN` | Access token for the Mycelium service account (`api` scope, Developer access on the project) |
| `GITLAB_PROJECT_ID` | Numeric ID of the GitLab project to monitor |

### Optional variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Vertex AI region |
| `GOOGLE_CLOUD_STORAGE_BUCKET` | _(empty)_ | GCS staging bucket for Agent Engine deployment (no `gs://` prefix) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name used by all agents and investigators |
| `MONGODB_DB` | `mycelium` | Database name inside the MongoDB cluster |
| `GITLAB_URL` | `https://gitlab.com` | GitLab host (change for self-hosted instances) |
| `GITLAB_BOT_USERNAME` | `mycelium-bot` | GitLab username of the project service account. Issues created by this account are tagged `bot_authored` in the repository snapshot and the account is excluded from team-member analysis. Change this if you used a different username when creating the service account. |
| `AGENT_LOOP_INTERVAL_SECONDS` | `300` | How often the pipeline loops (seconds) |
| `PIPELINE_LOOP_ENABLED` | `true` | Set to `false` to disable the auto-loop (manual `POST /pipeline/run` still works) |
| `DEMO_MODE` | `false` | Set to `true` to include demo-seeded data in agent context and activate the `/demo/seed` endpoint. Keep `false` in production so agents only operate on real data. |

---

## GitLab Service Account

All automated GitLab actions (issue creation, comments, assignments, edits, closes) run under
a **project-level service account**, not a personal account. This ensures:

- Automated actions are immediately distinguishable from human actions (author shows as the bot username)
- The token is scoped to one project and cannot act on upstream or other repositories
- Your personal GitLab activity feed stays clean

### Setup

1. In your GitLab project, go to **Settings → Members → Service accounts → Create service account**
2. Name: `Mycelium`, Username: `mycelium-bot`
3. Add the service account to the project with **Developer** access
   *(Developer is needed to edit and close issues created by others)*
4. Under the service account, generate a **Personal Access Token** with `api` scope
5. Set in `.env`:

```
GITLAB_TOKEN=<service-account-token>
GITLAB_BOT_USERNAME=mycelium-bot   # only needed if you used a different username
```

### What the separation does in code

- `get_members()` excludes the service account so it never appears as a tracked team member
- `get_open_issues()` sets `bot_authored: true` on every issue the service account created
- The planner reads `bot_authored` to decide edit/close permissions:
  - Bot-authored issues → the agent owns them, may edit or supersede freely
  - Human-authored issues → agent is conservative, prefers comments only

### Vertex AI routing

`settings.py` sets `GOOGLE_GENAI_USE_VERTEXAI=True` at import time, which
routes all `google-genai` SDK calls (including those inside ADK) through
Vertex AI rather than Google AI Studio. This is a hackathon requirement — no
AI Studio API keys are used anywhere in the codebase.

### Example `.env`

```
GOOGLE_CLOUD_PROJECT=my-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_CLOUD_STORAGE_BUCKET=my-staging-bucket
GEMINI_MODEL=gemini-2.5-flash

MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGODB_DB=mycelium

GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
GITLAB_PROJECT_ID=12345678

PIPELINE_LOOP_ENABLED=true
AGENT_LOOP_INTERVAL_SECONDS=300

# Set true to include demo-seeded data in agent context (for demos/dev)
DEMO_MODE=false
```
