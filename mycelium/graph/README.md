# graph/

MongoDB knowledge graph: data models and database operations.

---

## models.py — Pydantic data models

### DeveloperNode

Represents a person who appears in the repo.

```python
DeveloperNode(
    username="alice",
    name="Alice Adams",
    active=True,       # False for external/upstream authors
    external=False,    # True for non-members (fork contributors, upstream authors)
    expertise={},      # module_path -> expertise_score, maintained by pipeline
)
```

`external=True` developers are stored in the graph but excluded from the
"active team" view and shown separately as "upstream authors".

### ModuleNode

A tracked file/directory with observational measurements only — no risk scores.

```python
ModuleNode(
    path="src/auth",
    owners=["alice", "bob"],   # from CODEOWNERS
    bus_factor=1,              # count of internal committers covering 80% of commits
)
```

`bus_factor` is the only numeric measurement kept. It is computed by
`risk/forecasting.py`, not assigned by the agent.

### ContributionEdge

An edge between a developer and a module, carrying expertise information.

```python
ContributionEdge(
    developer_username="alice",
    module_path="src/auth",
    expertise_score=1.0,    # 1.0 for CODEOWNERS, 0.6 for MR approver, proportional for commits
    commit_count=42,
    external=False,
    developer_identity="alice@company.com",
)
```

### Finding

Qualitative analyst output. Replaces the old numeric risk score entirely.

```python
Finding(
    id="uuid",
    run_id="pipeline-run-id",
    subject="src/auth",
    concern_type="knowledge_concentration",
    narrative="Alice is the sole internal committer. No README exists...",
    evidence=["investigator/module/src/auth"],
    recommended_actions=["Pair another engineer on src/auth"],
    created_at=datetime.utcnow(),
)
```

`concern_type` is one of: `knowledge_concentration`, `fragile_documentation`,
`fading_contributor`, `recent_joiner_exposure`, `upstream_dominance`,
`upstream_drift`, `stalled_work`, `undeclared_ownership`, `nominal_ownership`,
`ci_instability`, `multi_module_overload`

---

## knowledge_graph.py — database operations

`KnowledgeGraph` wraps Motor (async MongoDB driver) with the five collections:
`developers`, `modules`, `tasks`, `contributions`, `findings`.

### Key methods

| Method | Description |
|--------|-------------|
| `setup_indexes()` | Creates unique indexes on `username`, `path`, etc. |
| `upsert_developer(node)` | Insert or update a developer |
| `upsert_module(node)` | Insert or update a module |
| `upsert_contribution(edge)` | Insert or update a contribution edge |
| `list_developers(active_only)` | Internal developers; `active_only=True` excludes external |
| `list_upstream_authors()` | External/upstream contributors only |
| `get_module_contributors(path)` | Contributions for a module, sorted by expertise desc |
| `list_concentrated_modules(max_bus_factor)` | Modules with bus_factor ≤ threshold |
| `insert_finding(finding)` | Persist an analyst Finding |
| `list_findings(limit, run_id)` | Recent findings, newest first |
| `snapshot()` | Combined read: developers + upstream_authors + concentrated_modules + open_tasks + recent_findings |
| `close()` | Close the Motor client |

The `snapshot()` method is what the analyst agent and the UI `/graph` endpoint
both consume — one call gives a full current picture.
