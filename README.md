# Continuity Engine (Mycelium)
GitLab Track

## What this is

Continuity Engine is an autonomous agent system that prevents engineering knowledge loss as teams and codebases evolve.

It continuously models:
- who understands what in a codebase (inferred, not declared)
- where knowledge is concentrated or fragile
- how that structure changes over time

Then it acts directly inside GitLab to stabilize it.

Core loop:

**Observe → Infer → Decide → Act → Learn**

---

## Why this exists

Most engineering orgs rely on:
- CODEOWNERS
- tribal knowledge
- static documentation
- manual onboarding

These assume knowledge is:
- explicit
- stable
- evenly distributed

In reality it is:
- implicit
- shifting
- unevenly distributed

Continuity Engine treats engineering knowledge as a **dynamic system property**, not documentation.

---

## Core idea

The system is built around a simple premise:

> organizational knowledge is latent structure embedded in repository activity

Not:
- tickets
- READMEs
- ownership metadata

Knowledge must be inferred continuously from:
- contribution behavior
- review patterns
- module interaction
- temporal activity
- dependency structure

The graph is the source of truth.
Generated artifacts are temporary views over that graph.

---

## What makes this different

### 1. It infers real ownership (not declared ownership)

Most systems assume:
- “who edited the file owns it”

This system estimates:
- who actually understands the module
- using contribution density, recency, review behavior, and cross-module interaction

Ownership becomes:
> inferred cognitive structure, not static metadata

---

### 2. It maintains a live knowledge graph (not dashboards)

Instead of static metrics, it builds a continuously updated graph:

- developers ↔ modules
- inferred expertise weights
- dependency relationships
- temporal knowledge evolution
- upstream vs internal ownership structure

This graph is not reporting.

It is system memory.

---

### 3. It closes the loop

Most tools stop at:
> “this looks risky”

This system continues:
> observe → interpret → intervene → observe impact → update model

The system actively modifies the environment it models.

---

### 4. It operates under incomplete information

Engineering organizations contain:
- hidden ownership
- stale documentation
- silent expertise concentration
- abandoned subsystem knowledge
- forked histories

The system reconstructs structure from weak signals instead of requiring explicit declarations.

---

## Why this must be agentic

This problem cannot be solved with deterministic automation because:

- ownership is latent
- expertise is probabilistic
- context changes continuously
- actions modify future system state

A rules engine assumes:
- stable inputs
- explicit structure
- fixed mappings

Real engineering systems have none of those properties.

So instead of:
> rules over static data

This system uses:
> inference + contextual reasoning + execution over evolving state

---

## Important design decision: no scalar risk score

The system intentionally avoids:
- global risk scores
- weighted aggregate metrics
- threshold-triggered decisions

Reason:
- engineering fragility is structural, not scalar
- aggregation destroys context
- thresholds create brittle behavior and false certainty

A human staff engineer does not think:
> “risk = 0.82”

They think:
- “this module only has one real maintainer”
- “this subsystem is upstream-dominated”
- “knowledge here is stale”
- “this dependency chain is fragile”

The system mirrors that reasoning model.

---

## Continuity interpretation model

Instead of computing a single score, the system:

1. extracts structured graph signals
2. investigates areas of concern
3. reasons over findings contextually
4. selects interventions

Signals include:
- ownership concentration
- contributor dispersion
- dependency exposure
- knowledge freshness
- upstream dominance
- review bottlenecks
- onboarding isolation

No scalar aggregation is required.

---

## Investigator-based reasoning model

Numeric values are observational only.

They are not conclusions.

The system spawns specialized investigative subagents that inspect graph regions and repository state in parallel.

### Member investigators
Analyze developers tied to fragile modules.

Questions:
- what knowledge is uniquely concentrated here?
- what disappears if this person leaves?
- how transferable is their context?

---

### Module investigators
Recursively inspect subsystems.

They:
- read source structure
- inspect READMEs/configuration
- inspect contribution history
- adapt investigation depth dynamically

Goal:
- determine how understandable and transferable the subsystem actually is

---

### Drift investigator
Analyzes divergence between upstream and local fork history.

Not:
- “commits behind”

But:
- semantic impact of missing changes
- security relevance
- architectural drift

---

## Core components

### Knowledge Graph (MongoDB)

Persistent memory layer containing:
- inferred ownership structure
- contributor-module relationships
- expertise distributions
- dependency graph
- historical evolution of knowledge

The graph is the persistent system state.

---

### Continuity Agent (Gemini)

Reasoning layer that:
- interprets graph state
- detects continuity threats
- synthesizes onboarding/handoff context
- prioritizes interventions
- selects GitLab actions

Operates on structured state, not raw logs.

---

### GitLab Action Layer (MCP)

Execution layer:
- create/assign issues
- annotate merge requests
- redistribute tasks
- generate onboarding packs
- generate handoff summaries
- trigger documentation updates

This is where reasoning becomes system change.

---

## System loop

1. Pull repository + activity state
2. Update graph memory
3. Infer ownership and expertise structure
4. Spawn investigative subagents
5. Reason over findings
6. Select interventions
7. Execute actions inside GitLab
8. Observe resulting state changes
9. Repeat continuously

---

## Key workflows

### Onboarding flow

Triggered when a new engineer joins.

System:
- maps repository structure
- identifies active subsystem experts
- synthesizes onboarding context pack:
  - subsystem overview
  - dependency map
  - key maintainers
  - starter tasks
  - active architectural areas

Goal:
> reduce time-to-context, not just time-to-first-commit

---

### Offboarding flow

Triggered when an engineer becomes inactive or leaves.

System:
- identifies active/incomplete work
- reconstructs implicit context from commits + reviews
- synthesizes handoff artifacts
- redistributes ownership
- updates graph structure

Goal:
> preserve operational continuity after knowledge loss events

---

### Continuous stabilization loop

Always running.

Detects:
- single-maintainer dependency structures
- isolated subsystem ownership
- stale critical modules
- upstream-heavy dark knowledge areas
- review bottlenecks
- onboarding dead zones

Interventions are:
- contextual
- ranked
- agent-selected

Never threshold-triggered.

---

## Onboarding and handoff artifacts

The system can synthesize:
- onboarding context packs
- subsystem summaries
- handoff artifacts
- transition-oriented operational context

These are not generic “AI-generated docs.”

They are:
> continuity-preserving projections of graph state for humans during transition events

The graph remains the source of truth.

Artifacts are generated views over it.

---

## Metrics (observational only)

Metrics describe state.

They do not drive decisions directly.

Examples:
- ownership distribution
- contributor diversity
- onboarding velocity
- documentation alignment
- subsystem isolation
- review concentration

No aggregate continuity score exists.

---

## Architecture

- Reasoning: Gemini
- Memory: MongoDB knowledge graph
- Execution: GitLab MCP
- Orchestration: Google Cloud Agent Runtime

---

## MCP architecture

Two MCP servers run concurrently:

| System | Role |
|---|---|
| GitLab MCP | executes repository actions |
| MongoDB MCP | maintains and queries graph state |

Both tool surfaces are merged into a unified reasoning environment.

The agent reasons over live graph state before taking actions.

---

## Fork-aware design

Designed explicitly for fork-based repositories.

Key issue:
- much of the code may have been written by upstream contributors no longer present internally

This creates:
> dark knowledge

System handles this by:
- separating external vs internal contributors
- weighting organizational ownership independently
- identifying upstream-dominant modules
- surfacing structurally orphaned subsystems

---

## Per-module ownership model

Ownership is modeled per directory/module.

Implementation:
- path-filtered contribution analysis
- normalized expertise weighting
- continuous recomputation after each learning cycle

Result:
> every subsystem has its own evolving ownership topology

Not:
> global contributor averages

---

## System behavior summary

Continuity Engine is not:
- a dashboard
- a static analyzer
- a documentation bot
- a rules engine
- a risk scoring system

It is:
- a continuously updating cognitive model of engineering knowledge
- an autonomous reasoning system over repository state
- a closed-loop intervention engine that stabilizes knowledge continuity over time

---

## Demo narrative

1. Initial state:
   - fragmented ownership
   - stale documentation
   - implicit subsystem knowledge

2. Onboarding:
   - system synthesizes context pack
   - assigns meaningful starter work

3. Investigation:
   - agent identifies fragile ownership structures

4. Offboarding:
   - implicit knowledge extracted into handoff artifacts
   - ownership redistributed

5. Stabilized state:
   - improved knowledge distribution
   - preserved continuity
   - reduced dependency on single individuals

---

## Value

Transforms engineering knowledge from:
- fragile
- implicit
- person-dependent

into:
- continuously modeled
- actively maintained
- operationally transferable
- structurally resilient

inside the development workflow itself.