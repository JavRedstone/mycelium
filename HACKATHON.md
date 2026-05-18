# Hackathon Requirements (Google Cloud Rapid Agent Hackathon 2026)

This document defines the **non-negotiable technical and architectural requirements** for Mycelium. It is intended to ensure full compliance with the official hackathon rules.

These requirements are derived from the official competition scope and must be preserved during implementation.

---

# 1. Google Agent Stack Requirement (Vertex AI + ADK)

## Mandatory Google Stack

The system must use the official Google agent ecosystem:

### Required components:
- Vertex AI SDK (`google-cloud-aiplatform`)
- Vertex AI Agent Engine
- Agent Development Kit (ADK)
- Gemini models (via Vertex AI)

---

## Correct architecture relationship

ADK is not a standalone replacement for Vertex AI.

### Correct layering:

- Vertex AI = platform + runtime
- Agent Engine = execution environment
- ADK = agent construction framework inside Vertex AI

---

## Required implementation pattern

```python
from google.adk.agents import Agent
from vertexai.agent_engines import AdkApp
````

---

## Key constraint

* AI Studio alone is NOT sufficient
* Direct Gemini API usage without Vertex AI is NOT sufficient
* ADK must be used as part of Vertex AI Agent Engine

---

## Required runtime pattern

```python
app = AdkApp(
    agent=Agent(
        model="gemini-2.5-flash",
        name="mycelium_agent",
        tools=[...]
    )
)
```

---

# 2. Partner MCP Integration Requirement (MANDATORY)

The system MUST integrate at least one official partner MCP server.

Mycelium uses a dual-MCP architecture:

| Partner | MCP Server           | Role                                            |
| ------- | -------------------- | ----------------------------------------------- |
| GitLab  | Official GitLab MCP  | Repository execution (issues, MRs, assignments) |
| MongoDB | Official MongoDB MCP | Knowledge graph + memory operations             |

---

## MCP usage requirements

The system must:

* Connect to real MCP servers (not mocks)
* Execute tool calls dynamically
* Use MCP inside the agent decision loop
* Perform meaningful system actions

---

## MCP role in system loop

```text
Observe → Infer → Decide → Act → Learn
```

Where:

* MongoDB MCP = memory + state access
* GitLab MCP = execution layer (real-world changes)

---

# 3. Agent Requirement (Non-Chat System)

The system must be an autonomous agent, not a chatbot.

## Required capabilities:

* Multi-step reasoning
* Tool execution via MCP
* Persistent memory
* State updates over time
* Autonomous decision-making
* External system actions

---

## Required execution loop

```text
Observe → Infer → Decide → Act → Learn
```

---

## Disallowed patterns:

* Chat-only interfaces
* Static Q&A systems
* Read-only dashboards
* Systems without external actions
* Single-step prompt-response tools

---

# 4. Real-World Action Requirement

The agent must perform real operational work.

## Valid actions include:

* Creating GitLab issues
* Assigning merge requests
* Updating repository metadata
* Detecting ownership changes
* Updating knowledge graphs
* Triggering onboarding/offboarding workflows

---

## Core requirement

The system must modify external system state.

---

# 5. Google Cloud Deployment Requirement

The system must run on Google Cloud infrastructure.

## Required components:

* Vertex AI Agent Engine OR Cloud Run
* Vertex AI SDK integration
* Gemini model access via Vertex AI
* Public deployment endpoint for demo

---

## Required deployment architecture

```text
Vertex AI Agent Engine (ADK Runtime)
        ↓
Mycelium Agent Orchestration Layer
        ↓
MCP Tool Layer (GitLab + MongoDB)
        ↓
External Systems (GitLab, MongoDB Atlas)
```

---

# 6. System Architecture Constraints

The following architecture is required for compliance:

## Core stack:

* Vertex AI SDK (`google-cloud-aiplatform`)
* Vertex AI Agent Engine
* ADK (Agent Development Kit)
* Gemini reasoning model
* MCP tool layer (GitLab + MongoDB)
* Cloud Run or Vertex AI deployment

---

## Required system structure

```text
Vertex AI Agent Engine (ADK runtime)
        ↓
Mycelium Agent Orchestration
        ↓
MCP Tool Layer
        ↓
External Systems
```

---

# 7. Submission Requirements

To be valid, the project must include:

* Hosted working deployment (Google Cloud)
* Public source repository with open-source license
* Demo video (≤ 3 minutes)
* Explicit partner MCP integration
* Clearly demonstrated Google Cloud + Vertex AI usage

---

# 8. Key Compliance Summary

## Must use:

* Vertex AI SDK
* Vertex AI Agent Engine
* ADK (Agent Development Kit)
* Gemini models via Vertex AI
* At least one partner MCP server

---

## Must NOT:

* Rely only on AI Studio
* Omit MCP integration
* Build a non-actionable chatbot
* Avoid Google Cloud deployment
* Use non-Google agent frameworks as primary runtime

---

# 9. Mycelium Compliance Status

Mycelium is designed to fully satisfy requirements:

* ADK used as agent construction layer
* Vertex AI Agent Engine used as runtime
* Gemini used for reasoning and planning
* GitLab MCP + MongoDB MCP used for execution and memory
* System performs real-world GitLab operations
* Continuous autonomous workflow execution loop
