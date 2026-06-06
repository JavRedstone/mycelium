# Setup Guide

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Backend runtime |
| Node.js 18+ with `npx` | Required for the MongoDB MCP server and the frontend |
| Google Cloud project | Vertex AI API must be enabled |
| MongoDB Atlas cluster | Free tier works |
| GitLab account | A project and a personal access token with `api` scope |
| Docker Desktop | Required for Cloud Run deployment |
| `gcloud` CLI | For Google Cloud auth and deployment |

---

## 1. Clone and install

**Backend**

```bash
cd mycelium/mycelium
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
source .venv/bin/activate    # Mac / Linux
pip install -r requirements.txt
```

**Frontend**

```bash
cd mycelium/mycelium-ui
npm install
```

---

## 2. Configure environment variables

Copy `mycelium/.env.example` to `mycelium/.env` and fill in the values:

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | yes | GCP project ID with Vertex AI enabled |
| `GOOGLE_CLOUD_LOCATION` | no | Vertex AI region (default `us-central1`) |
| `GOOGLE_CLOUD_STORAGE_BUCKET` | deploy only | GCS bucket for Agent Engine staging (no `gs://` prefix) |
| `GEMINI_MODEL` | no | Model name (default `gemini-2.5-flash`) |
| `MONGODB_URI` | yes | Atlas connection string (`mongodb+srv://...`) |
| `MONGODB_DB` | no | Database name (default `mycelium`) |
| `GITLAB_URL` | no | GitLab instance URL (default `https://gitlab.com`) |
| `GITLAB_TOKEN` | yes | Service account token with `api` scope — see section below |
| `GITLAB_PROJECT_ID` | yes | Numeric project ID — Settings > General > Project ID |
| `GITLAB_BOT_USERNAME` | no | Service account username (default `mycelium-bot`) |
| `GITLAB_WEBHOOK_SIGNING_TOKEN` | no | Signing token set in GitLab Webhooks settings. If set, all incoming webhook requests are verified. Leave empty for local dev. |
| `CORS_ORIGINS` | no | Comma-separated allowed origins. Set to `*` in production. Default: `http://localhost:3000` |
| `DEMO_MODE` | no | Set to `true` to enable demo data seeding. Default `false`. |

For the frontend, create `mycelium-ui/.env.local`:

```
API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Point both values at your Cloud Run URL once deployed.

---

## 3. GitLab service account

All automated GitLab writes (issue creation, comments, edits, closes) should run under a dedicated project service account rather than a personal token. This keeps bot actions visually distinct in the issue tracker and scopes the token to one project.

1. In your GitLab project: **Settings > Members > Service accounts > Create service account**
   - Name: `Mycelium`, Username: `mycelium-bot`
2. Add the service account to the project with **Developer** access (needed to edit and close issues)
3. Generate a **Personal Access Token** for the service account with `api` scope
4. Set that token as `GITLAB_TOKEN` in your `.env`

---

## 4. Authenticate to Google Cloud

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com
```

---

## 5. Verify connections

Run the individual checks from inside `mycelium/mycelium/` with the virtual environment active:

```bash
python checks/mongo/check_mongo.py           # MongoDB Atlas
python checks/gitlab/check_gitlab.py         # GitLab token + project read
python checks/gitlab/check_write.py          # GitLab write: create, comment, assign, close
python checks/vertex/check_vertex.py         # Vertex AI Gemini endpoint
python checks/vertex/check_adk.py            # ADK Agent + AdkApp end-to-end
python checks/mcp/check_mcp_mycelium.py      # Mycelium custom MCP server
python checks/mcp/check_mcp_gitlab.py        # Official GitLab MCP
python checks/mcp/check_mcp_mongo.py         # Official MongoDB MCP
python checks/check_all.py                   # All of the above in one pass
```

---

## 6. Run locally

```bash
# From mycelium/mycelium/ with .venv active
uvicorn main:app --reload
```

```bash
# From mycelium/mycelium-ui/
npm run dev
```

The backend starts at `http://localhost:8000` and the UI at `http://localhost:3000`.

The autonomous pipeline loop is off by default. Enable it and configure the interval from the Config page in the UI, or trigger a one-off run via the Pipeline page or CLI.

---

## 7. GitLab webhooks (optional)

Webhooks let Mycelium react to repository events in real time rather than waiting for the scheduled loop.

**Generate a signing token:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Add it to `mycelium/.env` as `GITLAB_WEBHOOK_SIGNING_TOKEN`.

**Configure in GitLab:** Settings > Webhooks > Add new webhook

| Field | Value |
|---|---|
| URL | `https://<your-cloud-run-url>/webhooks/gitlab` |
| Signing token | The token generated above |
| SSL verification | Enabled |

Enable: Push events, Comments, Work item events, Merge request events, Pipeline events.

---

## 8. Deploy

From the `mycelium/` directory with `mycelium/.env` filled in:

```bash
# Full deploy: Cloud Run backend + Vercel frontend
uv run deploy.py

# Backend only
uv run deploy.py backend

# Frontend only
uv run deploy.py frontend

# Act agent to Vertex AI Agent Engine only
uv run deploy.py agent
```

The deploy script reads `mycelium/.env` and handles Docker build, GCR push, Cloud Run deployment, and Vercel deployment automatically.

**Required before first deploy:**

```bash
# Create the GCS staging bucket (once, for Agent Engine)
gsutil mb -p $GOOGLE_CLOUD_PROJECT -l us-central1 gs://$GOOGLE_CLOUD_STORAGE_BUCKET
```

Cloud Run's service account needs the **Vertex AI User** role (`roles/aiplatform.user`).
