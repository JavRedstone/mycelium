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

The Config page has a **Seed stale issues** button (Demo Mode section) that creates two deliberately outdated GitLab issues:

| Title | Why it is stale |
|---|---|
| `Knowledge concentration: priya.sharma owns scripts/ exclusively` | Wrong title format — the pipeline uses the canonical prefix `Knowledge Transfer:` (or `Knowledge Transfer & Documentation:`). Any issue that doesn't start with a recognised canonical prefix is treated as non-canonical and will be superseded by a properly-titled replacement on the next run. |
| `Recent joiner exposure: marco.torres has no onboarding pair` | Wrong title format — the pipeline uses `generate_onboarding_pack` which produces a structured issue titled `Onboarding Pack: marco.torres`. The non-canonical "Recent joiner exposure:" prefix marks it as a legacy issue. |

When the pipeline runs after seeding, it detects that neither title matches a canonical format, ignores them during deduplication, creates proper replacements, and then closes the originals with a "superseded by #NNN" comment — demonstrating the stale-issue cleanup flow end-to-end.

---

## 7. Closing (10s)

> "The system converts repository activity into continuous operational awareness — and writes actions directly into GitLab."
