# agent/

The autonomous agent pipeline and all agent components.

---

## Files

### pipeline.py — orchestration

The main `Pipeline` class drives the 9-stage cycle. Each run produces a
structured log that the UI reads from `/pipeline/current`.

| Stage | ID | What happens |
|-------|----|-------------|
| 1 | `observe_repo` | Pulls live GitLab state: members, commits, CODEOWNERS, pipelines, MRs, issues, fork divergence |
| 2 | `map_modules` | Builds the module map from CODEOWNERS + commit history; upserts developers and contributions into MongoDB |
| 3 | `investigate` | Spawns concurrent Gemini Flash subagents (one per concentrated module, high-attention member, and upstream drift) to read actual file content |
| 4 | `observe_graph` | Takes a snapshot of the knowledge graph: developers, modules, concentrated modules, recent findings |
| 5 | `interpret` | Analyst agent synthesises investigator reports into qualitative findings (no numeric scores) |
| 6 | `plan` | Planner agent reads interpretation + graph snapshot and proposes concrete actions |
| 7 | `act` | Act agent executes the plan via MCP tools (create issues, add comments, assign work) |
| 8 | `learn` | Persists findings to MongoDB; refreshes bus_factor measurements on all modules |
| 9 | `summary` | Produces the human-readable run summary |

Key design rule: **no thresholds in the pipeline**. Measurements (bus_factor,
commit counts) are computed algorithmically. Judgments (what matters, what to
do) come entirely from the agents.

---

### investigator.py — subagent file readers

Three async functions that use `genai.Client` directly (not AdkApp) so they
can run concurrently via `asyncio.gather`:

- **`investigate_module(module_path, contributors, gitlab_client)`** — reads
  up to 30 files, recurses up to 3 directory levels, always reads key doc
  files (README, CONTRIBUTING, pyproject.toml, etc.)
- **`investigate_member(member, attention_reason, uniquely_owned_modules, gitlab_client)`** — reads up to 10 files authored primarily by that member
- **`investigate_drift(fork_divergence, gitlab_client)`** — reads upstream
  commit messages and judges urgency from content (e.g. CVE patch vs typo fix)

The investigator has a **shared budget** (`budget: list[int]`) so the total
file reads per subagent are capped regardless of directory depth.

---

### analyst_agent.py — interpretation

ADK `Agent` wrapped in `AdkApp`. Receives the investigator findings plus the
knowledge graph snapshot and produces:

```json
{
  "synthesis": "narrative summary",
  "findings": [
    {
      "subject": "src/auth",
      "concern_type": "knowledge_concentration",
      "narrative": "...",
      "evidence": ["..."],
      "recommended_actions": ["..."]
    }
  ]
}
```

Concern type vocabulary: `knowledge_concentration`, `fragile_documentation`,
`fading_contributor`, `recent_joiner_exposure`, `upstream_dominance`,
`upstream_drift`, `stalled_work`, `undeclared_ownership`, `nominal_ownership`,
`ci_instability`, `multi_module_overload`

---

### planner_agent.py — action planning

Reads the analyst interpretation + graph snapshot. Produces a structured list
of proposed actions (create issue, assign, comment) with rationale.

---

### act_agent.py — execution

Executes the planner's output via MCP tools. Has access to the Mycelium
custom MCP (read + write) and the GitLab OAuth MCP. Writes findings as
GitLab issues and comments.

This is also the agent deployed to Vertex AI Agent Engine — see
`deployment/README.md`.

---

### json_utils.py — LLM output parsing

`try_parse_json(text: str) -> dict | None`

Handles the common cases where Gemini wraps JSON in markdown fences or
prefixes it with prose. Strips fences, finds the first `{`, parses. Returns
`None` on failure.

---

## Running the pipeline manually

Via the FastAPI app (requires `.env`):

```
cd mycelium/mycelium
python main.py          # starts on port 8000
# then POST /pipeline/run
```

Or run one stage interactively through `checks/vertex/check_ask.py`.
