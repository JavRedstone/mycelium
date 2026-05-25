# risk/

Algorithmic measurements used as inputs to the agent pipeline.

---

## forecasting.py

### `compute_bus_factor(contributions: list[dict]) -> int`

The only numeric measurement remaining in Mycelium. Returns the minimum
number of internal contributors whose combined expertise covers ≥ 80% of the
total for a module.

```python
from risk.forecasting import compute_bus_factor

contribs = [
    {"expertise_score": 0.9, "external": False},
    {"expertise_score": 0.05, "external": False},
    {"expertise_score": 0.05, "external": False},
]
bus_factor = compute_bus_factor(contribs)  # → 1
```

Input is a list of contribution dicts (as returned by
`KnowledgeGraph.get_module_contributors`). Only entries where
`external=False` and `commit_count > 0` are counted toward the bus factor -
external/upstream authors are excluded because their knowledge is already
considered unavailable.

A result of `1` means a single person holds enough context that losing them
would leave the module without a knowledgeable owner. What to do about it is
the agent's decision, not a hardcoded threshold.

---

## What was removed - and why

Earlier versions of Mycelium computed scalar risk scores:
`compute_continuity_risk`, `compute_doc_drift`, `score_all_modules`. These
were removed because:

- Thresholds are arbitrary. `risk >= 0.7` means nothing without context about
  the team size, module criticality, and the actual content of the code.
- Numbers collapse nuance. A module with bus_factor=1 because of a planned
  handover is not the same as one where the sole author is about to leave.
- The agent can reason about the same information without needing a number.
  Gemini reads the commit history, the README, the CODEOWNERS file, the
  member's recent activity, and produces a narrative finding with specific
  recommended actions - something a scalar score cannot do.

See `PROJECT_IDEA.md` for the full rationale.
