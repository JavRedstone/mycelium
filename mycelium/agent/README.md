# agent/

The autonomous agent pipeline and all agent components.

---

## Files

### pipeline.py - orchestration

The main `Pipeline` class drives the 8-stage cycle. Each run produces a
structured log that the UI reads from `/pipeline/current`.

| Stage | ID | What happens |
|-------|----|-------------|
| 1 | `observe` | Parallel snapshot of GitLab state (members, commits, CODEOWNERS, pipelines, MRs, issues, fork divergence) + MongoDB graph. Captures GitLab baseline (`issue_iids`, `mr_iids`) for REFLECT to diff against. All external reads happen here. |
| 2 | `model` | Builds the module map from CODEOWNERS + commit history; detects high-attention members and flagged modules; upserts developers and contributions into MongoDB |
| 3 | `analyze` | Runs investigator subagents concurrently (one per concentrated module, high-attention member, and upstream drift), then calls analyst agent to synthesise reports into qualitative findings (no numeric scores) |
| 4 | `decide` | Planner agent reads interpretation + graph snapshot and proposes concrete actions; deduplicates `create_issue` actions against pre-existing open issues captured at OBSERVE |
| 5 | `act` | Act agent executes the plan via dual MCP tools (create issues, add comments, assign work through GitLab MCP; read graph through MongoDB MCP) |
| 6 | `reflect` | Re-fetches GitLab state post-ACT; diffs against OBSERVE baseline; annotates each finding with `actioned_at`, `pre_existing`, `duplicate_of`, `gitlab_iid` |
| 7 | `persist` | Persists REFLECT-annotated findings to MongoDB; refreshes bus_factor measurements on all modules |
| 8 | `summary` | Produces the human-readable run summary and writes the complete `pipeline_runs` document |

Key design rule: **no thresholds in the pipeline**. Measurements (bus_factor,
commit counts) are computed algorithmically. Judgments (what matters, what to
do) come entirely from the agents.

---

### investigator.py - subagent file readers

Three async functions that use `genai.Client` directly (not AdkApp) so they
can run concurrently via `asyncio.gather`:

- **`investigate_module(module_path, contributors, gitlab_client)`** - reads
  up to 30 files, recurses up to 3 directory levels, always reads key doc
  files (README, CONTRIBUTING, pyproject.toml, etc.)
- **`investigate_member(member, attention_reason, uniquely_owned_modules, gitlab_client)`** - reads up to 10 files authored primarily by that member
- **`investigate_drift(fork_divergence, gitlab_client)`** - reads upstream
  commit messages and judges urgency from content (e.g. CVE patch vs typo fix)

The investigator has a **shared budget** (`budget: list[int]`) so the total
file reads per subagent are capped regardless of directory depth.

---

### analyst_agent.py - interpretation

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

These concern types are grounded in empirical software engineering research:

| Concern type | Research grounding |
|---|---|
| `knowledge_concentration` / `undeclared_ownership` | Rigby & Bird (2013), FSE - code ownership and review concentration; Bird et al. (2011), ESEC/FSE - ownership breadth and defect correlation |
| `fading_contributor` | Developer turnover literature (MSR); contributor departure risk as a predictor of knowledge loss |
| `upstream_dominance` | Fork-specific extension - modules where bus factor is 0 because all committers are upstream authors outside the org |
| Bus factor threshold (80%) | Ferreira et al. (2019) - empirical analysis of bus factor thresholds across OSS projects |

The vocabulary itself was designed for this system. The underlying risk
concepts - knowledge concentration, ownership breadth, contributor departure,
and knowledge transfer - are well-established in the MSR/SE research
literature cited above and in [`README.md`](../README.md#prior-art-and-research-references).

---

### planner_agent.py - action planning

Reads the analyst interpretation + graph snapshot. Produces a structured list
of proposed actions (create issue, assign, comment) with rationale.

---

### act_agent.py - execution

Executes the planner's output via MCP tools. Has access to the Mycelium
custom MCP (read + write) and the GitLab OAuth MCP. Writes findings as
GitLab issues and comments.

This is also the agent deployed to Vertex AI Agent Engine - see
`deployment/README.md`.

---

### json_utils.py - LLM output parsing

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
