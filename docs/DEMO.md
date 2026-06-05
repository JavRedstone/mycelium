# Mycelium — Demo Script

## Total runtime: 3 minutes

---

## 0. Intro (10–15s)

> "Mycelium is an autonomous agent system that prevents engineering knowledge loss. It continuously infers who understands what in a codebase, where knowledge is fragile — and acts directly inside GitLab to stabilize it."

---

## 1. The scenario (15–20s)

Screen: Knowledge Graph → `scripts/` module

Visible state:
- Priya Sharma → sole strong contributor
- last active: 6 months ago
- no secondary maintainers

Switch briefly to new engineer:
- Marco Torres, 1 commit in `test/`, no module familiarity

> "This is the current state of the system. One critical module has a single real maintainer who is inactive. A new engineer joins with no context."

---

## 2. Trigger (10s)

Open the UI at **https://mycelium-ui.vercel.app**

Split screen: UI (left) + terminal (right)

```bash
curl -X POST https://mycelium-api-af56qkrypq-uc.a.run.app/demo/seed/team
curl -X POST https://mycelium-api-af56qkrypq-uc.a.run.app/pipeline/run
```

Or click **Seed Team** then **Run Pipeline** directly in the UI.

No narration during execution start.

---

## 3. Live execution (60–75s)

Screen: Activity Feed (left), GitLab Issues (right)

Pipeline stages running in order:

- **Observe** — parallel GitLab + MongoDB state capture
- **Model** — per-module contributor map built
- **Analyze** — member, module, and drift investigator subagents spawn concurrently; analyst synthesizes
- **Decide** — planner selects and deduplicates interventions
- **Act** — act agent writes into GitLab via MCP
- **Reflect** — reconcile actual GitLab state against planned actions
- **Persist** — updated graph, findings, and action log saved to MongoDB
- **Summary** — cycle outcome compiled

The Decide → Act → Reflect loop repeats (up to 5 passes) until all findings are addressed.

Minimal narration at transitions only:

**Observe / Model:**
> "Reading repository state."

**Analyze:**
> "Investigating contributor patterns, module structure, and upstream drift."

**Decide:**
> "Selecting interventions."

**Act:**
> "Writing into GitLab."

**Reflect / Persist / Summary:**
*(no commentary — let the UI show stages completing)*

**During Act**, if time allows, briefly show architecture diagram and name the stack:
> "Vertex AI Agent Engine, Gemini — GitLab MCP, MongoDB MCP."

---

## 4. Key event (10s)

A GitLab issue appears. Pause 2–3 seconds.

> "Knowledge Transfer: scripts/ — sole maintainer inactive."

> "This was generated automatically from repository state."

---

## 5. Onboarding artifact (20s)

Show second issue: **"Onboarding Pack: marco.torres"**

Brief scroll through: team map, module ownership, starter tasks.

> "This is generated automatically for the new engineer."

---

## 6. Before / After (20–25s)

| Before | After |
|---|---|
| Ownership unclear until failure | Risks detected during normal repository activity |
| Onboarding manual and inconsistent | Onboarding generated automatically |
| Knowledge loss detected late | GitLab becomes the execution layer for continuity actions |

---

---

## Appendix — Stale issue seeding

The Config page has a **Seed stale issues** button (Demo Mode section) that creates one deliberately outdated GitLab issue:

| Title | Why it is stale |
|---|---|
| `Upstream Drift: 14 commits behind \`gitlab-org/gitlab-pages\`` | The description was written by a **previous run** that measured 14 commits of drift. The current run measures 26. The planner receives the upstream drift finding alongside this issue's `description_preview` (which shows "14"), compares it against the current snapshot, and corrects the issue in place. |

**What to point to during the demo:**

The issue description makes the outdated data immediately obvious:
- **Commits behind upstream: 14** — the current run's repo snapshot shows 26
- **Analysis period: March 15 – May 12, 2026** — visibly from an earlier run
- The two commit hashes flagged as high-priority (`3a8f021`, `c17d409`) may already have been cherry-picked or merged

**What to say:**

> "This issue was created by a previous Mycelium run. It said 14 commits behind. The repository has kept drifting — now it's 26. Previously, Mycelium would have just ignored this issue because the subject was already covered. Now it passes the current finding alongside the existing issue's description to the planner, which sees the number is wrong and corrects it automatically."

When the pipeline runs after seeding, the planner receives `upstream_drift` as a **covered finding** — meaning it already has an open issue — along with the issue's `description_preview` showing "14 commits". The planner compares that against the current snapshot (26 commits), and plans an `edit_issue` or `add_comment` to bring the issue up to date. This demonstrates Mycelium maintaining accuracy across runs, not just detecting new problems.

---

## 7. Closing (10s)

> "The system converts repository activity into continuous operational awareness — and writes actions directly into GitLab."
