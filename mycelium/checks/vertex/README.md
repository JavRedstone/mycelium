# checks/vertex/

Vertex AI, ADK, and interactive agent checks.

Run from the project root (`mycelium/mycelium/`):

---

## check_vertex.py — Vertex AI + Gemini endpoint

```
python checks/vertex/check_vertex.py
```

Confirms that:
- Application Default Credentials (ADC) are configured correctly
- The `GOOGLE_CLOUD_PROJECT` environment variable is set
- `google-genai` SDK routes through **Vertex AI** (not Google AI Studio)
- The configured Gemini model responds to a one-word test prompt

**Requires:** `GOOGLE_CLOUD_PROJECT`, ADC (`gcloud auth application-default login`)

---

## check_adk.py — ADK + AdkApp runtime

```
python checks/vertex/check_adk.py
```

Validates the full ADK stack end-to-end:

```
google.adk.agents.Agent
    ↓
vertexai.preview.reasoning_engines.AdkApp
    ↓
Gemini via Vertex AI
```

Creates a no-tools smoke-test agent, runs one prompt through `stream_query`,
then deletes the session. Confirms the Agent Engine local runtime works before
attempting a remote deployment.

**Requires:** `GOOGLE_CLOUD_PROJECT`, ADC

---

## check_ask.py — interactive agent

```
python checks/vertex/check_ask.py
python checks/vertex/check_ask.py "Who has the most knowledge about src/auth?"
```

Spins up the full act agent (GitLab MCP + MongoDB MCP + Mycelium MCP tools),
wraps it in `AdkApp`, and streams the response to one question. Tool calls are
printed as `-> tool_name(arg=value)` so you can see what the agent invokes.

With no argument, prompts interactively. Ctrl+C to quit.

**Requires:** All three MCPs reachable (`MONGODB_URI`, `GITLAB_TOKEN`,
`GITLAB_PROJECT_ID`, `GOOGLE_CLOUD_PROJECT`, ADC)

---

## Prerequisites

All three scripts need Application Default Credentials:

```bash
gcloud auth application-default login
```

And these environment variables in `.env`:

```
GOOGLE_CLOUD_PROJECT=my-gcp-project
GOOGLE_CLOUD_LOCATION=us-central1    # optional, default us-central1
GEMINI_MODEL=gemini-2.5-flash        # optional, default gemini-2.5-flash
```
