# Continuity Engine - Demo Script

## Total runtime: ~3 minutes

---

## 0. Opening (20–30s)

Screen: Knowledge Graph → `scripts/` module

Visible state:
- Priya Sharma → sole strong contributor
- last active: 6 months ago
- no secondary maintainers

Switch briefly to new engineer:
- Marco Torres
- 1 commit in `test/`
- no module familiarity

Statement:

“This is the current state of the system. One critical module has a single real maintainer who is inactive. A new engineer joins with no context.”

---

## 1. Trigger (10–15s)

Split screen: UI + terminal

```bash
curl -X POST http://localhost:8000/demo/seed/team
curl -X POST http://localhost:8000/pipeline/run
```

Or click “Seed Team” then “Run Pipeline” in the UI.

No narration during execution start.

---

## 2. Live system execution (60–90s)

Screen: Activity Feed (left), GitLab Issues (right)

Pipeline stages (in order):

* **observe** — parallel GitLab + MongoDB state capture
* **model** — per-module contributor map built
* **analyze** — investigator subagents spawn concurrently (member, module, drift); analyst synthesizes
* **decide** — planner selects and deduplicates interventions
* **act** — act agent writes into GitLab via MCP
* **reflect** — reconcile actual GitLab state against what was planned
* **persist** — graph + findings + action log saved to MongoDB
* **summary** — cycle outcome compiled

The decide → act → reflect loop repeats (up to 5 passes) until all findings are addressed.

Minimal narration only at transitions:

**During observe / model**

> “Reading repository state.”

**During analyze**

> “Investigating code modules, contributor patterns, and upstream drift.”

**During decide**

> “Selecting interventions.”

**During act**

> “Writing into GitLab.”

**During reflect / persist / summary**

(no commentary — let the UI show the green stages)

---

## 3. Key event

A GitLab issue appears.

Pause for 2–3 seconds.

Read:

> “Knowledge Transfer: scripts/ - sole maintainer inactive”

Follow-up line:

> “This was generated automatically from repository state.”

---

## 4. Onboarding artifact (optional)

If generated, show second issue:

**“Onboarding Pack: marco.torres”**

Brief scroll through:

* team map
* module ownership
* starter tasks

Statement:

> “This is generated automatically for new engineers.”

---

## 5. Before / After comparison (20–30s)

### Before

* ownership unclear until failure
* onboarding manual and inconsistent
* knowledge loss detected late

### After

* risks detected during normal repository activity
* onboarding generated automatically
* GitLab becomes execution layer for continuity actions

---

## 6. Closing line (10s)

> “The system converts repository activity into continuous operational awareness and writes actions directly into GitLab.”