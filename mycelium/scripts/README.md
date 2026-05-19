# Demo Seed Scenarios

Synthetic team data for demoing and testing the pipeline without waiting for a
real repository to accumulate enough history to trigger every concern type.

All seeded entries carry `demo: true` in MongoDB so they are clearly labelled in
the Knowledge Graph UI (purple "demo" chip) and can be removed in one command.
They are **never** passed to agents — the graph snapshot the pipeline uses
filters `demo: true` out before reasoning, so synthetic contributors never
appear in generated GitLab issues.

---

## Usage

Run from the `mycelium/` directory (with your `.env` loaded):

```bash
# Seed the full 4-person team (recommended for demos)
python -m scripts.seed_scenarios team

# Seed individual scenarios
python -m scripts.seed_scenarios new_joiner   # marco.torres only
python -m scripts.seed_scenarios fading       # priya.sharma only
python -m scripts.seed_scenarios sole_owner   # alex.chen sole-holder scenario

# Remove all demo data
python -m scripts.seed_scenarios --clear
```

Re-running a scenario always **deletes its previous entries first**, so the data
is always fresh. You can re-seed between pipeline runs without leftover state.

---

## The demo team

| Username | Name | Status | Key ownership |
|---|---|---|---|
| `alex.chen` | Alex Chen | Active (yesterday) | Sole holder of `app/`, leads `internal/` |
| `priya.sharma` | Priya Sharma | **Inactive 6 months** | Sole holder of `scripts/` — RISK |
| `marco.torres` | Marco Torres | Joined 2 weeks ago | 1 commit in `test/`, no expertise yet |
| `lisa.park` | Lisa Park | Active (3 days ago) | Leads `test/`, backup on `shared/` |

### Module coverage matrix

| Module | bus_factor | Top contributor | Notes |
|---|---|---|---|
| `internal/` | 2 | alex (0.82), lisa (0.31) | Healthy dual-holder |
| `scripts/` | 1 | priya (0.97) | Sole holder, inactive — critical |
| `shared/` | 3 | alex (0.74), lisa (0.68), priya (0.41) | Well distributed |
| `test/` | 3 | lisa (0.71), alex (0.58), marco (0.04) | Marco's entry point |
| `app/` | 1 | alex (0.89) | Concentration risk |

---

## Concern types triggered

| Concern | Triggered by | Expected act output |
|---|---|---|
| `fading_contributor` | priya inactive 6 months, sole scripts/ owner | `generate_offboarding_artifact` |
| `recent_joiner_exposure` | marco joined 2 weeks ago, 1 commit | `generate_onboarding_pack` |
| `knowledge_concentration` | scripts/ bus_factor=1, owner inactive | `create_issue` (Knowledge Transfer) |
| `sole_contributor` | app/ bus_factor=1, alex only | `create_issue` (Knowledge Transfer) |

---

## How demo data is isolated

The `demo` flag propagates through the entire stack:

1. **MongoDB** — `demo: true` field on `developers`, `modules`, `contributions`
2. **Upsert safety** — pipeline `upsert_*` methods use `$setOnInsert` for `demo`,
   so a pipeline run never overwrites `demo: true` to `false` on seeded entries
3. **Agent context** — `snapshot()`, `list_developers()`, and
   `list_concentrated_modules()` all filter `{"demo": {"$ne": true}}` before
   handing data to agents — synthetic users never appear in generated issues
4. **UI** — the Knowledge Graph page shows a purple "demo" chip on every
   seeded contributor, contributor row, and React Flow node; a banner appears
   when any demo data is present; a "Clear demo data" button calls
   `DELETE /graph/demo`

---

## Clearing via the API

```bash
# Check if demo data is present
curl http://localhost:8000/graph/demo

# Delete all demo entries
curl -X DELETE http://localhost:8000/graph/demo
```
