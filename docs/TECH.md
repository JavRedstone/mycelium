# Mycelium — Technology Stack

## AI / Reasoning

| Technology | Role |
|---|---|
| **Gemini** (via Vertex AI) | Primary reasoning model for all agent stages and investigator subagents |
| **Google AI SDK** (`google-genai`) | Gemini API client; used for direct subagent calls and streaming |
| **ADK — Agent Development Kit** (`google-adk`) | Agent runtime for the main pipeline agent (AdkApp); manages tool dispatch and multi-step reasoning |
| **Vertex AI Agent Engine** | Managed runtime that hosts the ADK agent in production on Google Cloud |

## Google Cloud Infrastructure

| Technology | Role |
|---|---|
| **Cloud Run** | Hosts the FastAPI backend; auto-scales to handle webhook bursts and concurrent pipeline runs |
| **Vertex AI** (`google-cloud-aiplatform`) | Platform layer for ADK and Gemini access |
| **Google Cloud Secret Manager** | Stores API keys and credentials securely; retrieved at startup |
| **Google Cloud Logging** | Structured log ingestion from the backend |
| **Docker** | Container image build and deployment to Cloud Run |

## Agent Tools / MCP

| Technology | Role |
|---|---|
| **GitLab MCP** (official) | Executes repository operations — creating issues, posting comments, updating merge requests |
| **Custom GitLab MCP server** | Wraps the GitLab REST API directly; extends the official MCP with continuity-specific tools (onboarding packs, handoff artifacts, stale-issue resolution) |
| **MongoDB MCP** (official) | Gives the ADK agent direct read/write access to the knowledge graph during pipeline execution |
| **MCP protocol** (`mcp`) | Client library used by ADK MCPToolset to connect agent to both MCP servers |

## Data / Persistence

| Technology | Role |
|---|---|
| **MongoDB** | Persistent knowledge graph: ownership weights, contributor history, bus factor signals, findings, action logs, runtime config |
| **Motor** (`motor`) | Async MongoDB driver for Python; used throughout the FastAPI backend |
| **PyMongo** (`pymongo`) | Synchronous MongoDB access for CLI and background tasks |

## Backend

| Technology | Role |
|---|---|
| **FastAPI** | REST API server; handles webhook ingestion, pipeline orchestration, and all UI data endpoints |
| **Uvicorn** | ASGI server running FastAPI on Cloud Run |
| **SSE / sse-starlette** | Server-Sent Events stream that pushes live agent activity to the UI and CLI in real time |
| **python-gitlab** | GitLab REST API client used by the observation and action layers |
| **Pydantic / pydantic-settings** | Request/response validation and settings management |
| **python-dotenv** | Local environment variable loading for development |
| **httpx** | Async HTTP client for outbound calls |

## CLI

| Technology | Role |
|---|---|
| **Click** | CLI framework for the `mycelium` terminal interface |
| **Rich** | Terminal rendering — tables, progress, live streaming output |

## Frontend (Monitoring UI)

| Technology | Role |
|---|---|
| **Next.js 16** | React framework; App Router with SSE-based real-time streaming |
| **React 19** | UI component library |
| **TypeScript** | Type safety across all frontend code |
| **MUI (Material UI v9)** | Component library — layout, data tables, chips, drawers |
| **React Flow (`@xyflow/react`)** | Interactive node-link diagram for the Knowledge Graph page |
| **Recharts** | Charts for the Analytics page (bus factor distribution, findings by type, knowledge load) |
| **Tailwind CSS v4** | Utility-first styling |
| **Emotion** | CSS-in-JS runtime used by MUI |

## Development / Testing

| Technology | Role |
|---|---|
| **pytest / pytest-asyncio** | Backend unit and integration tests |
| **ESLint** | Frontend linting |
| **absl-py** | Flag parsing in the ADK deployment helper (consistent with ADK sample patterns) |
