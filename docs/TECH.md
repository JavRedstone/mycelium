# Mycelium Technology Stack

## Google Cloud Technologies

Gemini, Vertex AI, Vertex AI Agent Engine, Google ADK, Cloud Run, Google Cloud Storage

## Other Technologies

GitLab MCP, MongoDB MCP, MongoDB Atlas, GitLab API, GitLab Webhooks, FastAPI, Next.js, Docker

---

## AI / Reasoning

| Technology | Role |
|---|---|
| **Gemini** (via Vertex AI) | Primary reasoning model for all agent stages and investigator subagents |
| **Google AI SDK** | Gemini API client; used for direct subagent calls and streaming |
| **Google ADK** (Agent Development Kit) | Agent runtime for the main pipeline agent; manages tool dispatch and multi-step reasoning |
| **Vertex AI Agent Engine** | Managed runtime that hosts the ADK agent in production on Google Cloud |
| **Vertex AI** | Platform layer for ADK and Gemini access |

## Google Cloud Infrastructure

| Technology | Role |
|---|---|
| **Cloud Run** | Hosts the FastAPI backend; auto-scales to handle webhook bursts and concurrent pipeline runs |
| **Google Cloud Storage** | Staging bucket for ADK Agent Engine deployment artifacts |
| **Google Cloud Secret Manager** | Stores API keys and credentials securely; retrieved at startup |
| **Google Cloud Logging** | Structured log ingestion from the backend |
| **Docker** | Container image build and deployment to Cloud Run |

## Agent Tools / MCP

| Technology | Role |
|---|---|
| **GitLab MCP** (official) | Executes repository operations: creating issues, posting comments, updating merge requests |
| **Custom GitLab MCP server** | Wraps the GitLab REST API directly; extends the official MCP with continuity-specific tools (onboarding packs, handoff artifacts, stale-issue resolution) |
| **MongoDB MCP** (official) | Gives the ADK agent direct read/write access to the knowledge graph during pipeline execution |
| **MCP protocol** | Client library used by ADK MCPToolset to connect the agent to both MCP servers |

## Data / Persistence

| Technology | Role |
|---|---|
| **MongoDB Atlas** | Persistent knowledge graph: ownership weights, contributor history, bus factor signals, findings, action logs, runtime config |
| **Motor** | Async MongoDB driver for Python; used throughout the FastAPI backend |
| **PyMongo** | Synchronous MongoDB access for CLI and background tasks |

## Backend

| Technology | Role |
|---|---|
| **FastAPI** | REST API server; handles webhook ingestion, pipeline orchestration, and all UI data endpoints |
| **GitLab API** | REST API used by the observation and action layers to read repository state and write back to GitLab |
| **GitLab Webhooks** | Push, merge request, issue, and member events that trigger autonomous pipeline runs in real time |
| **Uvicorn** | ASGI server running FastAPI on Cloud Run |
| **SSE** (Server-Sent Events) | Pushes live agent activity to the UI and CLI in real time |
| **Pydantic** | Request/response validation and settings management |
| **httpx** | Async HTTP client for outbound calls |

## CLI

| Technology | Role |
|---|---|
| **Click** | CLI framework for the terminal interface |
| **Rich** | Terminal rendering: tables, progress, live streaming output |

## Frontend (Monitoring UI)

| Technology | Role |
|---|---|
| **Next.js** | React framework; App Router with SSE-based real-time streaming |
| **React** | UI component library |
| **TypeScript** | Type safety across all frontend code |
| **MUI** (Material UI) | Component library: layout, data tables, chips, drawers |
| **React Flow** | Interactive node-link diagram for the Knowledge Graph page |
| **Recharts** | Charts for the Analytics page (bus factor distribution, findings by type, knowledge load) |
| **Tailwind CSS** | Utility-first styling |

## Development / Testing

| Technology | Role |
|---|---|
| **pytest** | Backend unit and integration tests |
| **ESLint** | Frontend linting |
