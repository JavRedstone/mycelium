# Mycelium UI

Next.js frontend for the **Mycelium Engineering Continuity Engine**.
Talks to the FastAPI backend at `../mycelium/` over HTTP (and SSE for
live streams) to visualise the knowledge graph, run the agent pipeline,
and explore continuity findings.

> ⚠️ This is **Next.js 16 / React 19** with breaking changes from earlier
> versions - APIs, conventions, and file layout differ. If you're editing
> code, check `node_modules/next/dist/docs/` for the current docs before
> assuming an API exists.

---

## Quick Setup

**1. Install dependencies**

```bash
cd mycelium-ui
npm install
```

**2. Configure environment**

```bash
cp .env.local.example .env.local
```

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | Backend URL used by **browser-side** code (client components, `fetch` in `useEffect`, etc.) |
| `API_URL` | Backend URL used by **server-side** code (server components, route handlers) |

`API_URL` defaults to `http://localhost:8000` (server-side, works fine).
`NEXT_PUBLIC_API_URL` defaults to `http://127.0.0.1:8000` (browser-side) - on
Windows 11, `localhost` resolves to `::1` (IPv6) but uvicorn binds IPv4 only,
so the browser needs the explicit IPv4 address.

**3. Start the dev server**

```bash
npm run dev
```

Opens at [http://localhost:3000](http://localhost:3000).

**4. Backend must be running**

```bash
cd ../mycelium
uvicorn main:app --reload
```

See `../mycelium/README.md` for the full backend setup, agent loop config,
and Google Cloud / MongoDB Atlas requirements.

---

## Pages

The sidebar has three groups (Repository, Pipeline, Insights) plus
Configuration pinned at the bottom. Each page is a thin route component
that renders one or more feature components from `app/components/`.

### Repository group

#### `/repo` - Repository

Renders [`MockRepo`](app/components/MockRepo.tsx). The knowledge graph
shown as a familiar file-browser layout: top-level directories with the
people who hold them, last-touched dates, and dark-knowledge warnings.
Best entry point if you're new to the project - it answers "who owns
what" without forcing the user to understand the graph model.

#### `/history` - Repository History

Renders [`RepoHistory`](app/components/RepoHistory.tsx). Per-contributor
horizontal activity timeline showing when each developer was active in
the repo. Key features:

- **One row per contributor.** Internal team on top, upstream authors below the dashed separator.
- **Bars span contiguous active months,** snapping exactly to the developer's `first_seen` on the left and `last_seen` on the right (no month rounding).
- **Bar colour encodes state:**
  - **Vivid green** - active post-fork contributor (committed within 60 days)
  - **Red** - internal contributor with no commits in 60+ days
  - **Slate gray** - pre-fork commits (upstream history from before this fork)
- **Two global vertical lines:**
  - **`repo start` / `fork date (demo)`** - when this fork was created (or the seeded override)
  - **`inactivity cutoff`** - 60 days before today; bars whose right edge sits to the left of this line are red by definition
- **Hover any bar** → tooltip with the exact date range, commit count, and contributor name. The hovered bar brightens while the others dim.

Below the timeline is a **Module last activity** table summarising every
module's bus factor, lead contributor, and freshness - see the bus factor
explainer in [Concepts](#concepts) below.

#### `/graph` - Knowledge Graph

Renders [`KnowledgeGraph`](app/components/KnowledgeGraph.tsx). This is
the deepest view in the app. It contains:

- **Mode toggle** - *Module breakdown* (default, list view) ↔ *Graph view* (React Flow node-edge map)
- **Demo controls** - `Seed demo data` dropdown with four scenarios (`team`, `new_joiner`, `fading`, `sole_owner`) and a `Clear` button. These only appear when the backend has `DEMO_MODE=true`. Seed creates 4 internal demo developers + upstream authors + a fork-date override; clear removes everything flagged `demo: true`.
- **Per-module cards** showing concentration label, path, bus factor (with an `ⓘ` info tooltip explaining what bus factor means), contributor rows sorted by expertise, and any analyst findings as chips.
- **Contributor rows are clickable** (dotted underline). Clicking opens the bus-factor drawer:
  - **Internal contributor view** - explains how this person ranks in each module's 80% threshold. Bars show their share of internal expertise, with a star at the cumulative-80 mark.
  - **Upstream author view** - orange "not counted in bus factor" banner, then their share of *all* commits per module, and the internal contributors who currently hold the module (if any).
- **Expertise score numbers** (the `0.00–1.00` next to each contributor) are also hoverable for an inline definition.

#### Pipeline group

#### `/pipeline` - Pipeline

Renders the live agent loop. Top: [`RunHistory`](app/components/RunHistory.tsx)
strip with the last N runs. Middle: a stage list ([`Pipeline`](app/components/Pipeline.tsx))
showing the 9-stage flow (Observe Repo → Map Modules → Investigate → Observe
Graph → Analyze → Plan → Execute → Persist → Summary), each stage with status,
duration, and a collapsible JSON payload. Right: [`AgentLog`](app/components/AgentLog.tsx)
streams uvicorn / agent logs over SSE. There's a "Run pipeline" button that
posts to `/pipeline/run`.

#### `/activity` - Agent Activity

Renders [`ActivityFeed`](app/components/ActivityFeed.tsx). A structured
event stream of what the agents are *doing* right now - thinking,
calling tools, spawning subagents, returning judgments. Filtered &
formatted differently from raw `/logs` (which is unstructured uvicorn
output). Backed by `/pipeline/activity/stream` (SSE).

#### `/logs` - Agent Logs

Renders [`AgentLog`](app/components/AgentLog.tsx) full-height. Plain
log stream from uvicorn + Python logging - useful for debugging when
the activity feed is too high-level.

#### `/actions` - Actions

Renders [`Actions`](app/components/Actions.tsx). Append-only log of what
the act agent has actually *done* to GitLab: issues created, comments
posted, assignments made. Each row links back to the run that produced
it. Backed by `/actions`.

### Insights group

#### `/timeline` - Timeline

Renders [`Timeline`](app/components/Timeline.tsx). Chronological merged
feed of pipeline runs, findings detected, and actions taken - answers
"what's happened in the last week?" at a glance.

#### `/investigations` - Investigations

Renders [`Investigations`](app/components/Investigations.tsx). The raw
output from investigator subagents: what they read in the repo, what
they judged, why they thought it mattered. This is the qualitative
counterpart to the Knowledge Graph's structural view - no thresholds,
no scores, just the agent's reasoning.

#### `/analytics` - Analytics

Renders [`Analytics`](app/components/Analytics.tsx). Aggregated charts:
risk distribution across modules, bus-factor breakdown, developer
expertise load. Uses Recharts.

### Bottom

#### `/config` - Configuration

Renders [`ConfigPanel`](app/components/ConfigPanel.tsx). Shows the
current backend runtime settings (GCP project, Gemini model, GitLab
URL/project, MongoDB DB, pipeline-loop interval, demo mode) and the
fork-date override input (which seeds the "repo start" vertical line
on `/history`). Values are read-only here - to change them, edit
`../mycelium/.env` and restart the backend.

---

## Concepts

These terms appear repeatedly across pages. The UI also surfaces most of
them as hover tooltips on `ⓘ` icons - this section is the authoritative
reference.

### Bus factor

**A per-module metric.** Minimum number of *internal* contributors whose
combined expertise covers ≥80% of that module's total internal expertise.

| Bus factor | Meaning |
|---|---|
| `0` | No internal contributors. All knowledge is upstream - a **dark knowledge zone**. |
| `1` | One person covers >80% alone. Their departure breaks the team's confidence in the module. |
| `2+` | Multiple people would have to disappear before knowledge is lost. Safer. |

**Upstream authors are excluded by design** - they're already gone for
knowledge-transfer purposes. See `../mycelium/README.md`
("Bus Factor: Definition and Design Decisions") for the 80% threshold
justification (Ferreira et al. 2019 + Pareto).

### Expertise score

**A per-contributor, per-module value, 0.00–1.00.** Normalised commit
share: the top contributor to each module is always 1.00, others are
proportional. So 0.50 means about half as many commits as the top
contributor.

The bus-factor calculation walks contributors sorted by expertise
descending and stops when cumulative coverage hits 80%.

### Internal vs upstream contributors

- **Internal** - current project member, blue chip / row. Counts toward bus factor.
- **Upstream** - wrote commits but isn't a current member (typical in forks). Orange chip / row. Excluded from bus factor.

A module with strong upstream presence but no internal coverage is a
**dark knowledge zone** - the code is well-developed but no one on the
team owns its mental model.

### Demo mode

`DEMO_MODE=true` on the backend unlocks the seed/clear endpoints and
inserts a fake team into MongoDB so demos & screenshots work without a
live repo accumulating months of history. Every seeded entity carries
`demo: true` and shows a purple "demo" chip in the UI.

- The dropdown to seed and the Clear button only appear when `demoMode` is true.
- The analyst agent is told to treat seeded contributors as real when reasoning, but only when `DEMO_MODE=true`.
- Clearing removes every `demo: true` document from every collection.

### Fork date

The vertical "repo start" line on `/history`. Defaults to the GitLab
project's `created_at`; can be overridden on `/config` (the override
shows as "fork date (demo)"). Used to colour pre-fork bars gray and
distinguish *upstream history that came with the fork* from
*post-fork team contributions*.

### Inactivity cutoff (60 days)

The red vertical line on `/history`. Contributors whose `last_seen` is
older than this threshold get red bars and trigger "no recent commits"
annotations next to their last-active marker. The constant lives in
[`RepoHistory.tsx`](app/components/RepoHistory.tsx) (`INACTIVE_DAYS = 60`).

---

## Component Layout

```
app/
├── layout.tsx                 # Root layout - wraps Sidebar + ThemeRegistry around all pages
├── page.tsx                   # Root page - redirects to /pipeline
├── ThemeRegistry.tsx          # MUI emotion cache + theme provider
│
├── repo/page.tsx              → MockRepo
├── history/page.tsx           → RepoHistory
├── graph/page.tsx             → KnowledgeGraph
├── pipeline/page.tsx          → Pipeline + RunHistory + AgentLog
├── activity/page.tsx          → ActivityFeed
├── logs/page.tsx              → AgentLog
├── actions/page.tsx           → Actions
├── timeline/page.tsx          → Timeline
├── investigations/page.tsx    → Investigations
├── analytics/page.tsx         → Analytics
├── config/page.tsx            → ConfigPanel
│
└── components/
    ├── Sidebar.tsx            # Navigation drawer (Repository / Pipeline / Insights / Configuration)
    ├── MockRepo.tsx           # File-browser view of the knowledge graph
    ├── RepoHistory.tsx        # Per-contributor activity timeline + module table
    ├── KnowledgeGraph.tsx     # Module breakdown + React Flow graph + bus-factor drawer
    ├── Pipeline.tsx           # 9-stage execution panel
    ├── RunHistory.tsx         # Recent runs strip on /pipeline
    ├── ActivityFeed.tsx       # Structured agent event stream (SSE)
    ├── AgentLog.tsx           # Raw uvicorn/Python log stream (SSE)
    ├── AgentTrace.tsx         # Inline trace bubble used inside ActivityFeed
    ├── Actions.tsx            # GitLab actions log
    ├── Timeline.tsx           # Merged run/finding/action chronology
    ├── Investigations.tsx     # Subagent qualitative findings
    ├── Analytics.tsx          # Recharts dashboards
    ├── ConfigPanel.tsx        # Backend settings + fork-date override
    ├── RefreshButton.tsx      # Reusable refresh button
    └── Md.tsx                 # react-markdown wrapper with MUI styling
```

---

## Backend API Used

| Endpoint | Used by |
|---|---|
| `GET /config` | `ConfigPanel`, `KnowledgeGraph` (to gate demo controls) |
| `GET /graph` | `KnowledgeGraph`, `MockRepo` |
| `GET /developers` | `RepoHistory`, `MockRepo` |
| `GET /developers/busfactor?username=…` | `KnowledgeGraph` (drawer) |
| `GET /graph/contribution-history` | `RepoHistory` |
| `GET /settings/fork-date` | `RepoHistory`, `ConfigPanel` |
| `POST /settings/fork-date` | `ConfigPanel` |
| `GET /graph/demo` | `KnowledgeGraph` (to decide whether the Clear button shows) |
| `POST /demo/seed/{scenario}` | `KnowledgeGraph` (Seed menu) - **gated by `DEMO_MODE`** |
| `DELETE /graph/demo` | `KnowledgeGraph` (Clear button) - **gated by `DEMO_MODE`** |
| `GET /pipeline/history` | `RunHistory` |
| `GET /pipeline/current` | `Pipeline` |
| `POST /pipeline/run` | `Pipeline` (Run button) |
| `POST /pipeline/stop` | `Pipeline` (Stop button) |
| `GET /pipeline/stream` (SSE) | `Pipeline` |
| `GET /pipeline/activity` | `ActivityFeed` (seed) |
| `GET /pipeline/activity/stream` (SSE) | `ActivityFeed` (live) |
| `GET /pipeline/{run_id}/events` | `Timeline` (run replay) |
| `GET /logs/stream` (SSE) | `AgentLog` |
| `GET /actions` | `Actions`, `Timeline` |
| `GET /findings` | `Investigations`, `Timeline`, `Analytics` |

See `../mycelium/README.md` § *API Endpoints* and `../mycelium/main.py` for
the request/response shapes.

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Framework | **Next.js 16 (App Router)** | Server components for fast first paint, client components for live data |
| UI kit | **MUI v9** + Emotion | Dense, dark-mode-first components; the dashboard look without a CSS framework rewrite |
| Graph viz | **`@xyflow/react`** (React Flow 12) | Used in the optional Graph view on `/graph` |
| Charts | **Recharts 3** | Lightweight Cartesian charts on `/analytics`; the timeline charts on `/history` are hand-rolled SVG |
| Styling utility | **Tailwind v4 + PostCSS** | Spot use for one-off utility classes - most styling lives in MUI's `sx` prop |
| Markdown | **react-markdown** | Used inside investigator finding cards |
| Streaming | Native **EventSource** | All live data uses SSE - pipeline stream, activity stream, log stream |
| Fonts | Google Sans + Google Sans Code | Loaded in `layout.tsx`; `var(--font-google-sans-code)` is the canonical mono token |

---

## Conventions

- **Server vs client** - components that fetch data on mount or use state are client components (`"use client"` at the top). Page wrappers in `app/<route>/page.tsx` are server components and only render their layout chrome + the client feature component.
- **Colour tokens** - internal blue `#4285f4`, upstream orange `#fa7b17`, active green `#4ade80`, inactive red `#f87171`, pre-fork gray `#94a3b8`, demo violet `#a78bfa`. Used consistently across `KnowledgeGraph`, `RepoHistory`, and `MockRepo`.
- **Iconography** - Material icons only. No unicode glyphs (★, ▶, etc.) - replace with the matching `@mui/icons-material/*Outlined` icon. The block-bar characters used in CLI output (`█░`) are not used in the UI.
- **API URLs** - read once at the top of a client component (`const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";`). Never hardcode `localhost` inline.
- **SSE lifecycle** - open an `EventSource` in `useEffect`, close it in the cleanup. Never re-open in render.
