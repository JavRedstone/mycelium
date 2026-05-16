# Continuity Engine (Mycelium)
GitLab Track

## Overview

Continuity Engine is an autonomous AI agent system that maintains engineering knowledge continuity across team changes. It treats organizational knowledge as a **dynamic system property**, not static documentation.

The system continuously models how knowledge exists inside a codebase, detects when that knowledge is at risk, and takes corrective action through GitLab.

---

## Problem

Engineering organizations routinely lose critical context due to:

- Developer onboarding delays and unclear system understanding
- Untracked or implicit code ownership
- Knowledge loss when engineers leave or become inactive
- Orphaned or stalled work in repositories
- Over-reliance on individual experts (low bus factor)

These failures are typically only detected after productivity loss occurs.

---

## Solution

Continuity Engine is an AI agent system that continuously:

- Observes GitLab repository and team activity
- Builds and updates a knowledge graph in MongoDB
- Infers ownership, expertise, and dependency structure
- Predicts knowledge loss and continuity risks
- Executes corrective actions through GitLab MCP
- Learns from outcomes to refine future decisions

It operates as a closed-loop autonomous system:

**Observe → Infer → Decide → Act → Learn**

---

## Why This Must Be an AI Agent System (Core Design Rationale)

This problem cannot be solved with static rules, dashboards, or traditional automation because:

### 1. The system state is dynamic and incomplete
- Code ownership is not explicitly defined
- Expertise is inferred from behavior, not declared
- Dependencies evolve continuously across commits and PRs

A deterministic system cannot reliably model this complexity.

---

### 2. Decisions require contextual reasoning
The system must evaluate:
- Who actually understands a module (not just who last edited it)
- Whether a change introduces knowledge concentration risk
- How to redistribute work without breaking ongoing development

These are probabilistic, context-dependent decisions that require reasoning over multiple signals.

---

### 3. Actions affect future system state
Every action changes:
- ownership distribution
- workload balance
- knowledge graph structure

This creates a feedback loop where the system must continuously re-evaluate its own assumptions.

---

### 4. The system must generalize across unseen scenarios
Examples:
- unexpected engineer departure
- rapidly changing repositories
- partial or conflicting ownership signals

Hard-coded logic fails in these cases. An agent is required to generalize decisions.

---

### Conclusion

This is fundamentally an **adaptive decision-making system over evolving organizational state**, which requires an AI agent architecture rather than static automation.

---

## Core Innovation

The system introduces **Continuity as a System Property**:

- Knowledge is continuously inferred, not manually documented
- Ownership is probabilistic, not explicit
- Risk is predicted before failure, not after
- Actions are executed autonomously, not suggested

---

## Core Components

### 1. Knowledge Graph (MongoDB)
Persistent memory layer representing:

- Code ownership distribution (inferred)
- Developer expertise per module
- Task and contribution history
- Dependency relationships between components
- Continuity risk signals over time

---

### 2. Continuity Agent (Gemini)
The reasoning engine responsible for:

- Detecting onboarding and offboarding events
- Identifying knowledge concentration and gaps
- Evaluating system-wide continuity risk
- Prioritizing interventions based on impact
- Generating structured context transfers

---

### 3. GitLab Action Layer (MCP)
Execution interface that performs real system changes:

- Issue creation and assignment
- Merge request annotations with context
- Task reassignment based on inferred expertise
- Onboarding/offboarding workflow automation
- Documentation updates based on detected drift

---

### 4. Continuity Risk Forecasting Engine
A predictive layer that estimates:

- Knowledge loss probability per module
- Ownership concentration risk (“bus factor”)
- Documentation drift vs active development
- Emerging single points of failure

This enables proactive intervention before failures occur.

---

## System Loop

1. Observe GitLab activity and repository state via MCP
2. Infer ownership structure and knowledge distribution using Gemini
3. Decide required continuity actions (onboarding, offboarding, mitigation)
4. Act through GitLab MCP (issues, assignments, annotations)
5. Learn by updating MongoDB knowledge graph
6. Repeat continuously as the system evolves

---

## Key Workflows

### Onboarding Flow
Triggered when a new engineer joins.

The system:

- Analyzes repository structure and active development
- Identifies key modules and inferred experts
- Generates a contextual onboarding pack:
  - current system state summary
  - relevant maintainers per subsystem
  - prioritized starter tasks
- Assigns tasks directly in GitLab

Goal: reduce time-to-context and accelerate meaningful contribution.

---

### Offboarding Flow
Triggered when an engineer becomes inactive or leaves.

The system:

- Identifies all active and incomplete work
- Extracts implicit knowledge from recent contributions
- Generates structured handoff summaries per task
- Reassigns ownership based on inferred expertise similarity
- Updates knowledge graph to reflect structural changes

Goal: prevent knowledge loss and stalled execution.

---

### Continuity Risk Mitigation (Predictive Behavior)
Continuously evaluates system health:

- Modules with single-point knowledge dependency
- Declining engagement in critical areas
- Hidden ownership concentration risks

When thresholds are exceeded, the system:

- Creates GitLab issues proactively
- Triggers documentation generation
- Reassigns or balances workload automatically

Goal: prevent failure before it occurs.

---

## System Metrics

The system exposes operational indicators of organizational health:

- **Ownership Coverage**: diversity of contributors per module
- **Knowledge Concentration Risk**: dependency on single engineers
- **Onboarding Velocity**: time to first meaningful contribution
- **Context Completeness**: alignment between code activity and documentation
- **Continuity Risk Score**: predicted probability of knowledge loss

These metrics are used to drive actions, not just display information.

---

## Architecture

- **Reasoning Engine:** Gemini
- **Memory Layer:** MongoDB (knowledge graph + state + history)
- **Execution Layer:** GitLab MCP (repository operations)
- **Orchestration:** Google Cloud Agent Builder / Vertex AI Agent Runtime

---

## System Behavior Summary

Continuity Engine is not a passive assistant.

It is an autonomous AI system that:

- Models engineering knowledge as a dynamic graph
- Predicts structural risks in team knowledge distribution
- Executes corrective actions inside GitLab
- Continuously updates its internal understanding of the system

---

## Demo Narrative

The system is demonstrated as a lifecycle:

1. **Baseline:** unclear ownership, fragmented knowledge, outdated context
2. **Onboarding event:** system generates context pack and assigns tasks
3. **Risk detection:** identifies knowledge concentration and triggers mitigation
4. **Offboarding event:** extracts implicit knowledge and reassigns work
5. **Outcome:** stabilized ownership graph and preserved system knowledge

---

## Value Proposition

Continuity Engine transforms engineering knowledge from a fragile human-dependent asset into a continuously maintained, predictive, and self-correcting system layer inside software development workflows.

---

## Implementation Decisions

This section records concrete decisions made during development — what we're using, what we skipped, and why.

---

### Dual-MCP Architecture

Mycelium's act agent connects to **two official MCP servers simultaneously** during each execute stage:

| MCP Server | Transport | Tools exposed | Purpose |
|---|---|---|---|
| **GitLab MCP** (`/api/v4/mcp`) | HTTP / streamable-HTTP | Write tools only — `create_issue`, `create_merge_request`, `add_comment`, etc. | Execute corrective actions in the GitLab project |
| **MongoDB MCP** (`@mongodb-js/mongodb-mcp-server`) | stdio via `npx` | All tools — `find`, `aggregate`, `insertOne`, etc. | Query and update the Mycelium knowledge graph directly |

Both sessions are opened concurrently. Their tool sets are merged into a single registry keyed by tool name; Gemini selects from the combined surface in each turn. This is implemented in `agent/act_agent.py` via:

- `streamablehttp_client` (mcp ≥ 1.27) for GitLab MCP
- `stdio_client` + `StdioServerParameters` for MongoDB MCP (non-fatal — falls back to GitLab-only if `npx` is unavailable)

This architecture satisfies **both** the GitLab and MongoDB partner MCP requirements in a single agent, and allows Gemini to reason over live graph data (MongoDB) before deciding which GitLab actions to take.

---

### GitLab Integration

**What we use:**
- **python-gitlab** (`gitlab_mcp/client.py`) — observation layer, reads commit history, members, CODEOWNERS, CI status, MR approvals.
- **Official GitLab MCP server** (`/api/v4/mcp`, HTTP transport) — execution layer, used directly in `act_agent.py` via `streamablehttp_client`.
- **GitLab Webhooks → Mycelium** (planned) — `POST /webhook/gitlab` endpoint for push/MR/pipeline events. Makes the system event-driven rather than timer-only. Requires a public URL (Cloud Run for production).

**What we skip (and why):**

| Feature | Decision | Reason |
|---|---|---|
| **Custom Flows (Beta)** | Skip until Cloud Run deployed | Flows run inside GitLab's infra and cannot reach a local Mycelium. Worth adding post-deploy to post MR reviewer recommendations inline. |
| **Custom Agents (GA)** | Skip for now | Conversational interface within GitLab — requires Mycelium public URL. Lower priority than webhooks. |

**Right sequence for GitLab features:**
1. Webhook endpoint (event-driven triggers, works with ngrok today)
2. Cloud Run deploy (permanent public URL, required for submission)
3. Custom Flow (post-deploy, calls Mycelium's Cloud Run URL, posts MR comments with graph data)

---

### Fork-Based Repository Handling

Mycelium is explicitly designed for organizations using a fork-based workflow (e.g., open-source projects maintained as forks). In this model, the majority of commit history was authored by upstream contributors who are not current project members. This creates "dark knowledge" — code written by people with no current organizational relationship.

Key design decisions:
- `DeveloperNode.external = True` flags upstream/fork authors separately from internal members
- `ContributionEdge.expertise_score` for external contributors still contributes to module risk scoring via an external concentration penalty (`ext_ratio * 0.3` when >50% of committers are upstream)
- Bus factor uses **only internal active committers** (`commit_count > 0`, `external = False`) — declared CODEOWNERS-only entries don't count
- The UI surfaces upstream authors distinctly under "dark knowledge" with a warning, not mixed into the internal developer list

---

### Per-Module Knowledge Attribution

The core of the knowledge graph is not WHO contributed globally, but WHO KNOWS WHAT PART of the codebase.

Implementation:
- `get_top_level_dirs()` discovers meaningful code directories (skips `vendor/`, `.git/`, etc.)
- `get_directory_contributors(path)` uses GitLab's path-filtered commit API to count how many times each author touched that specific directory
- `ContributionEdge.expertise_score` is relative within each module: top contributor scores 1.0, others are proportional to their commit share
- `_rescore_modules()` runs after each learn stage, recomputing `continuity_risk_score` and `bus_factor` per module using the updated contribution edges

This means the graph answers: "Alice owns `internal/` at 1.0, Bob is secondary at 0.2, no internal committers for `app/` (all upstream — CRITICAL)"

---

### Deployment Plan

| Step | What | Why |
|---|---|---|
| 1 | Add `POST /webhook/gitlab` to `main.py` | Event-driven triggers — pipeline runs on push/MR, not just on timer |
| 2 | `Dockerfile` for FastAPI backend | Containerize for Cloud Run |
| 3 | `Dockerfile` for Next.js frontend | Containerize UI |
| 4 | Deploy both to Cloud Run | Permanent public URLs, satisfies Google Cloud partner track, enables webhooks |
| 5 | Configure GitLab project webhook → Cloud Run URL | Mycelium reacts to real repo events |
| 6 | (Optional) Custom Flow YAML | Triggered on MR ready → calls Mycelium `/graph` → posts reviewer comment on MR |

---

### What's Built

- **Pipeline:** 8 stages (observe_repo → map_modules → observe_graph → analyze → plan → act → learn → summary), fully async, SSE-streamed to UI
- **Knowledge Graph:** MongoDB Atlas, four collections (developers, modules, tasks, contributions), per-module risk scoring with bus factor + upstream concentration penalties
- **GitLab signals collected:** commit history (global + per-directory), project members, CODEOWNERS, CI pipeline status, MR approvals
- **Fork awareness:** upstream authors detected, stored separately, dark knowledge risk quantified; surface distinctly in UI
- **Dual-MCP execution:** act agent connects to official GitLab MCP (HTTP) + official MongoDB MCP (stdio) simultaneously; Gemini reasons over live graph data before taking GitLab actions
- **Gemma model:** `gemma-3-27b-it` via Google AI Studio; all three Gemini calls (analyze, plan, act) use exponential backoff (5s → 15s → 40s) against free-tier rate limits
- **UI:** Next.js + MUI dark theme — pipeline timeline with per-stage drill-down, knowledge graph with who-knows-what per module, upstream authors panel with per-module expertise bars