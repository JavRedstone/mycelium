# deployment/

Deploy the Mycelium act agent to Vertex AI Agent Engine.

---

## deploy.py

Packages the act agent and supporting modules, then creates or manages a
remote `ReasoningEngine` on Vertex AI Agent Engine.

### Prerequisites

1. A GCS bucket for staging (no `gs://` prefix in the env var)
2. Vertex AI API enabled in the project
3. Application Default Credentials: `gcloud auth application-default login`
4. All required env vars in `.env` (see `config/README.md`)

### Commands

```bash
# Deploy (create or replace)
python deployment/deploy.py --create

# List deployed agents
python deployment/deploy.py --list

# Delete a deployed agent
python deployment/deploy.py --delete --resource_id projects/.../reasoningEngines/...
```

### What gets bundled

The deployment bundles these local packages into the Agent Engine runtime:

```
agent/        - pipeline, analyst, planner, act agent, investigator, json_utils
config/       - settings
graph/        - models, knowledge_graph
connectors/   - gitlab_client, mcp_server
risk/         - forecasting (bus_factor)
```

Python dependencies (`requirements.txt`) are declared in `_REQUIREMENTS` inside
`deploy.py` and installed by Agent Engine at deploy time.

Environment variables (`GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `MONGODB_URI`,
etc.) are forwarded to the remote runtime via `env_vars`.

---

## Docker (Cloud Run)

The `Dockerfile` at `mycelium/mycelium/Dockerfile` is used for Cloud Run
deployments of the FastAPI app (`main.py`). It exposes port 8080 and
runs `uvicorn main:app`.

Build and deploy:

```bash
# Build image
docker build -t mycelium-api .

# Push to Artifact Registry (replace with your registry)
docker tag mycelium-api gcr.io/YOUR_PROJECT/mycelium-api
docker push gcr.io/YOUR_PROJECT/mycelium-api

# Deploy to Cloud Run
gcloud run deploy mycelium-api \
  --image gcr.io/YOUR_PROJECT/mycelium-api \
  --region us-central1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=...,MONGODB_URI=...,GITLAB_TOKEN=...,GITLAB_PROJECT_ID=...
```

The Cloud Run instance runs the full pipeline loop (`PIPELINE_LOOP_ENABLED=true`)
and serves the REST API consumed by the UI.
