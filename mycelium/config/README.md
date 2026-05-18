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
| `GITLAB_TOKEN` | GitLab personal access token (minimum: `api` scope, Developer access) |
| `GITLAB_PROJECT_ID` | Numeric ID of the GitLab project to monitor |

### Optional variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Vertex AI region |
| `GOOGLE_CLOUD_STORAGE_BUCKET` | _(empty)_ | GCS staging bucket for Agent Engine deployment (no `gs://` prefix) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name used by all agents and investigators |
| `MONGODB_DB` | `mycelium` | Database name inside the MongoDB cluster |
| `GITLAB_URL` | `https://gitlab.com` | GitLab host (change for self-hosted instances) |
| `AGENT_LOOP_INTERVAL_SECONDS` | `300` | How often the pipeline loops (seconds) |
| `PIPELINE_LOOP_ENABLED` | `true` | Set to `false` to disable the auto-loop (manual `POST /pipeline/run` still works) |

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
```
