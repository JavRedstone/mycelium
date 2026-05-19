# Continuity Engine — Demo Script

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
python -m scripts.seed_scenarios team
curl -X POST http://localhost:8000/pipeline/run
````

Or click “Run Pipeline”.

No narration during execution start.

---

## 2. Live system execution (60–90s)

Screen: Activity Feed (left), GitLab Issues (right)

Pipeline stages:

* observe_repo
* map_modules
* investigate
* analyze
* plan
* act

Minimal narration only at transitions:

**During observe / map**

> “Reading repository state.”

**During investigate**

> “Inspecting code modules and contribution history.”

**During analyze**
(no commentary)

**During plan**

> “Deciding whether action is needed.”

**During act**

> “Writing into GitLab.”

---

## 3. Key event

A GitLab issue appears.

Pause for 2–3 seconds.

Read:

> “Knowledge Transfer: scripts/ — sole maintainer inactive”

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