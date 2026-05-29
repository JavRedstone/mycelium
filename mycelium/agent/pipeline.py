import asyncio
import json
import logging
import re
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Optional

from agent import analyst_agent, planner_agent, investigator
from agent import act_agent
from agent.activity_bus import bus as _activity_bus
from connectors.gitlab_client import GitLabClient
from graph.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


def _parse_iso_dt(s: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string from GitLab into a datetime, or return None."""
    if not s:
        return None
    try:
        # GitLab returns e.g. "2024-03-15T09:22:01.000+00:00" or "2024-03-15T09:22:01Z"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _subject_matches_title(subject: str, title_lower: str) -> bool:
    """Return True if a finding subject is represented in an issue title.

    Handles four cases:
      1. Direct containment       – "marco.torres" in "onboarding: marco.torres"
      2. Dot-normalised           – "alex.chen"    matches "alex chen"
      3. Path-base + dot-norm     – "members/alex.chen" → base "alex.chen" → "alex chen"
      4. Significant-word overlap – "upstream sync" → all words >4 chars ("upstream")
                                    appear in "synchronize with upstream: …"
    """
    subject = subject.lower().strip()
    if not subject or not title_lower:
        return False

    # 1. Direct
    if subject in title_lower:
        return True

    # 2. Dot-normalised direct
    subj_norm = subject.replace(".", " ")
    if subj_norm != subject and subj_norm in title_lower:
        return True

    # 3. Path-base (last component) + dot-normalised variant
    if "/" in subject:
        base = subject.split("/")[-1]
        if len(base) > 3:
            if base in title_lower:
                return True
            base_norm = base.replace(".", " ")
            if base_norm != base and base_norm in title_lower:
                return True

    # 4. All significant words (>4 chars) of subject appear in title
    sig_words = [w for w in re.split(r"[\s/._\-]+", subject) if len(w) > 4]
    if sig_words and all(w in title_lower for w in sig_words):
        return True

    return False


class _PipelineCancelled(Exception):
    pass


STAGE_DEFS = [
    {"id": "observe",   "label": "Observe",  "description": "Parallel state capture: repository snapshot, knowledge graph, and GitLab baseline (issues, MRs) — all reads happen here"},
    {"id": "model",     "label": "Model",    "description": "Integrate repository snapshot into knowledge graph; update inferred ownership and contributor-module relationships"},
    {"id": "analyze",   "label": "Analyze",  "description": "Spawn concurrent investigator subagents over modules and members; synthesize findings into structured concern types"},
    {"id": "decide_1",  "label": "Decide",   "description": "Select bounded intervention set; deduplicate against GitLab baseline to prevent redundant action creation"},
    {"id": "act_1",     "label": "Act",      "description": "Execute GitLab mutations: create issues, update MRs, assign ownership, generate artifacts"},
    {"id": "reflect_1", "label": "Reflect",  "description": "Reconcile intended actions against observed GitLab state; annotate findings with causal metadata"},
    {"id": "persist",   "label": "Persist",  "description": "Write updated graph state, annotated findings, and causal action history to MongoDB"},
    {"id": "summary",   "label": "Summary",  "description": "Compile cycle outcome: structural changes, verified interventions, and key metrics"},
]

# Labels/descriptions for dynamically-inserted DAR pass stages (pass 2, 3, …)
_LOOP_STAGE_META: dict[str, tuple[str, str]] = {
    "decide":  ("Decide",  "Select bounded intervention set; deduplicate against GitLab baseline to prevent redundant action creation"),
    "act":     ("Act",     "Execute GitLab mutations: create issues, update MRs, assign ownership, generate artifacts"),
    "reflect": ("Reflect", "Reconcile intended actions against observed GitLab state; annotate findings with causal metadata"),
}


@dataclass
class StageState:
    id: str
    label: str
    description: str
    status: str = "pending"          # pending | running | success | failed | skipped
    started_at: Optional[float] = None
    duration_ms: Optional[int] = None
    output: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class PipelineRun:
    run_id: str
    started_at: float
    status: str = "running"          # running | success | partial | failed
    stages: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "status": self.status,
            "stages": [asdict(s) for s in self.stages],
        }


class PipelineRunner:
    def __init__(self, gitlab: GitLabClient, graph: KnowledgeGraph):
        self._gitlab = gitlab
        self._graph = graph
        self._current_run: Optional[PipelineRun] = None
        self._run_history: deque[PipelineRun] = deque(maxlen=20)
        self._subscribers: set[asyncio.Queue] = set()
        self._running = False

        self._cancel_requested = False

        # Scratch data passed between stages (not stored in stage.output)
        self._repo: dict = {}
        self._module_contributors: dict = {}
        self._investigations: dict = {}      # {"members": [...], "modules": [...], "drift": {...}}
        self._graph_data: dict = {}
        self._interpretation: dict = {}      # {"synthesis": "...", "findings": [...], "annotated_findings": [...]}
        self._plan: dict = {}
        self._act_result: dict = {}
        self._reflect_result: dict = {}

        # GitLab state captured at OBSERVE time — REFLECT diffs against this baseline
        self._pre_run_gitlab_snapshot: dict = {}    # {"issue_iids": set, "mr_iids": set}
        self._pre_run_gitlab_issues: list = []      # full issue objects for DECIDE deduplication

    @property
    def current_run(self) -> Optional[PipelineRun]:
        return self._current_run

    @property
    def is_running(self) -> bool:
        return self._running

    def request_cancel(self) -> None:
        self._cancel_requested = True

    @property
    def run_history(self) -> list:
        return list(self._run_history)

    # ------------------------------------------------------------------
    # SSE subscription
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _broadcast(self) -> None:
        if not self._current_run:
            return
        data = self._current_run.to_dict()
        for q in list(self._subscribers):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        if self._running:
            logger.warning("[pipeline] Run requested but already running - skipping")
            return
        self._running = True
        self._cancel_requested = False
        run = PipelineRun(
            run_id=str(uuid.uuid4()),
            started_at=time.time(),
            stages=[StageState(**d) for d in STAGE_DEFS],
        )
        self._current_run = run
        self._broadcast()
        _activity_bus.reset()
        _activity_bus.start_capture(run.run_id)
        _activity_bus.emit({"type": "run_start", "run_id": run.run_id})

        try:
            # OBSERVE: single unified state ingestion boundary.
            # All reads happen here; all downstream stages operate on a frozen snapshot.
            if not await self._execute("observe", self._observe):
                run.status = "failed"
                return

            # MODEL: integrate repo snapshot into knowledge graph.
            await self._execute("model", self._model)

            # ANALYZE: concurrent investigation + central synthesis.
            # Best-effort — pipeline continues with whatever findings were collected.
            await self._execute("analyze", self._analyze)

            # ── DECIDE → ACT → REFLECT stabilization loop ──────────────────
            # Each pass is a separate set of numbered stages (decide_1/act_1/reflect_1,
            # decide_2/act_2/reflect_2, …).  Pass 2+ stages are injected into
            # run.stages dynamically just before persist so the UI shows them.
            cfg = await self._graph.get_runtime_config()
            # Default 3: the new architecture runs a full decide/act/reflect per pass
            # so the old rampant-agent risk is gone.  Raise via MongoDB settings
            # {"_id":"runtime","act_max_stabilization_passes":N} to increase.
            MAX_DAR_PASSES = max(1, min(10, int(cfg.get("act_max_stabilization_passes", 5))))

            # Snapshot bot issues before the first pass (used for stale-close after loop)
            pre_loop_issues: list[dict] = []
            try:
                pre_loop_issues = await asyncio.to_thread(self._gitlab.list_bot_issues)
            except Exception as exc:
                logger.warning("[pipeline] Could not snapshot pre-loop bot issues: %s", exc)

            # Cross-pass intervention memory
            known_iids:              set[int] = {i["iid"] for i in pre_loop_issues}
            addressed_issue_iids:    list[int] = []
            addressed_subjects:      list[str] = []
            addressed_details:       list[str] = []
            skip_action_titles:      set[str]  = set()
            skip_edit_iids:          set[int]  = set()
            skip_artifact_usernames: set[str]  = set()

            # Accumulated act metrics (for _persist / _summary compatibility)
            all_act_details:    list[dict] = []
            all_act_executed  = 0
            all_act_failed    = 0
            all_act_violations: list[str] = []
            all_act_mcp_calls:  list[dict] = []
            last_act_summary:   str | None = None
            passes_run        = 1
            dar_failed        = False

            for pass_num in range(1, MAX_DAR_PASSES + 1):
                passes_run = pass_num
                decide_id  = f"decide_{pass_num}"
                act_id     = f"act_{pass_num}"
                reflect_id = f"reflect_{pass_num}"

                # Inject stage placeholders for passes beyond the first
                if pass_num > 1:
                    persist_idx = next(
                        i for i, s in enumerate(run.stages) if s.id == "persist"
                    )
                    for base_id in ("decide", "act", "reflect"):
                        lbl, desc = _LOOP_STAGE_META[base_id]
                        run.stages.insert(
                            persist_idx,
                            StageState(id=f"{base_id}_{pass_num}", label=lbl, description=desc),
                        )
                        persist_idx += 1
                    self._broadcast()

                # Build prior-interventions context (None on pass 1)
                prior: dict | None = None
                if pass_num > 1:
                    prior = {
                        "iteration": pass_num,
                        "max_iterations": MAX_DAR_PASSES,
                        "addressed_issue_iids": list(addressed_issue_iids),
                        "addressed_subjects": list(addressed_subjects),
                        "addressed_details": list(addressed_details),
                        "skip_action_titles": list(skip_action_titles),
                        "skip_edit_iids": list(skip_edit_iids),
                        "skip_artifact_usernames": list(skip_artifact_usernames),
                    }

                # DECIDE
                _p, _prior = pass_num, prior
                if not await self._execute(decide_id, lambda: self._decide(_p, _prior)):
                    dar_failed = True
                    break

                # ACT (single pass — no internal loop)
                _p2, _prior2 = pass_num, prior
                await self._execute(act_id, lambda: self._act_single(_p2, _prior2))

                # Harvest pass results from stage output
                act_stage    = next(s for s in run.stages if s.id == act_id)
                pass_result  = act_stage.output or {}
                pass_details = pass_result.get("details", [])
                all_act_details.extend(pass_details)
                all_act_executed   += pass_result.get("executed", 0)
                all_act_failed     += pass_result.get("failed", 0)
                all_act_violations.extend(pass_result.get("boundary_violations", []))
                all_act_mcp_calls.extend(pass_result.get("mcp_calls", []))
                if pass_result.get("summary"):
                    last_act_summary = pass_result["summary"]

                # Update skip sets so next pass doesn't re-execute completed actions
                for d in pass_details:
                    kind   = d.get("kind", "")
                    params = d.get("params", {})
                    if kind == "create_issue":
                        raw   = d.get("detail", "")
                        title = raw.split(" ", 1)[-1] if raw.startswith("#") else raw
                        if title:
                            skip_action_titles.add(title)
                    elif kind in ("edit_issue", "assign_issue"):
                        iid = d.get("iid") or int(params.get("iid", 0) or 0)
                        if iid:
                            skip_edit_iids.add(int(iid))
                    elif kind in ("generate_onboarding_pack", "generate_offboarding_artifact"):
                        username = (
                            params.get("new_member_username")
                            or params.get("departing_member_username")
                            or params.get("username", "")
                        )
                        if username:
                            skip_artifact_usernames.add(username)

                # REFLECT
                await self._execute(reflect_id, self._reflect)

                # Update intervention tracking from newly created issues.
                # Used to build prior_interventions context for the next pass.
                # Uses the same base-component normalisation as _reflect() so that
                # path-style subjects like "members/marco.torres" match issue titles.
                new_issue_count = 0
                try:
                    current_issues = await asyncio.to_thread(self._gitlab.list_bot_issues)
                    for iss in current_issues:
                        if iss["iid"] not in known_iids:
                            known_iids.add(iss["iid"])
                            addressed_issue_iids.append(iss["iid"])
                            addressed_details.append(f"#{iss['iid']} {iss['title']}")
                            new_issue_count += 1
                            title_lower = iss["title"].lower()
                            for f in (self._interpretation or {}).get("findings", []):
                                sub = str(f.get("subject", "")).lower().strip()
                                if sub and _subject_matches_title(sub, title_lower) and sub not in addressed_subjects:
                                    addressed_subjects.append(sub)
                                    break
                except Exception as exc:
                    logger.warning("[pipeline] Pass %d: issue count check failed: %s", pass_num, exc)

                # Convergence: all findings addressed → no point in another pass
                unaddressed = self._reflect_result.get("findings_unaddressed", 0)
                if unaddressed == 0:
                    logger.info("[pipeline] All findings addressed after %d pass(es)", pass_num)
                    break
                # Convergence: nothing was executed at all → further passes won't help.
                # Only check on pass 2+ (pass 1 may legitimately execute nothing if the
                # plan is empty, e.g. all actions were deduplicated).
                if pass_num > 1 and len(pass_details) == 0:
                    logger.info("[pipeline] No actions taken in pass %d - frontier exhausted", pass_num)
                    break

            # Close stale/superseded issues once all passes are done
            stale_closed = 0
            if not dar_failed:
                stale_closed = await self._close_stale_bot_issues(pre_loop_issues)
                if stale_closed:
                    _activity_bus.emit({
                        "type": "agent_text", "stage_id": f"act_{passes_run}",
                        "text": f"Closed {stale_closed} stale or superseded bot issue(s).",
                    })

            # Store accumulated result for _persist / _summary
            self._act_result = {
                "executed": all_act_executed,
                "failed": all_act_failed,
                "details": all_act_details,
                "mcp_calls": all_act_mcp_calls,
                "summary": last_act_summary,
                "boundary_violations": all_act_violations,
                "stabilization_passes": passes_run,
                "stale_issues_closed": stale_closed,
            }
            # ── End stabilization loop ──────────────────────────────────────

            if dar_failed:
                run.status = "failed"
            else:
                # PERSIST: write annotated findings + updated graph to MongoDB.
                await self._execute("persist", self._persist)
                await self._execute("summary", self._summary)

                run.status = (
                    "success"
                    if all(s.status in ("success", "skipped") for s in run.stages)
                    else "partial"
                )
        except _PipelineCancelled:
            run.status = "cancelled"
            logger.info("[pipeline] Run cancelled by user request")
        except Exception:
            run.status = "failed"
            logger.exception("[pipeline] Unexpected pipeline error")
        finally:
            self._running = False
            self._run_history.append(run)
            self._broadcast()
            _activity_bus.emit({"type": "run_end", "run_id": run.run_id, "status": run.status})
            captured_events = _activity_bus.stop_capture()
            try:
                await self._graph.save_run(run.to_dict())
            except Exception as exc:
                logger.error("[pipeline] Failed to persist run to MongoDB: %s", exc)
            try:
                await self._graph.save_activity_events(run.run_id, captured_events)
            except Exception as exc:
                logger.error("[pipeline] Failed to persist activity events: %s", exc)

    async def _execute(self, stage_id: str, coro: Callable[[], Awaitable[dict]]) -> bool:
        if self._cancel_requested:
            for s in self._current_run.stages:
                if s.status == "pending":
                    s.status = "skipped"
            self._broadcast()
            raise _PipelineCancelled()
        stage = next(s for s in self._current_run.stages if s.id == stage_id)
        stage.status = "running"
        stage.started_at = time.time()
        self._broadcast()
        _activity_bus.emit({"type": "stage_start", "stage_id": stage_id, "label": stage.label})
        try:
            logger.info("[pipeline] %-12s started", stage.label)
            stage.output = await coro()
            stage.status = "success"
            stage.duration_ms = int((time.time() - stage.started_at) * 1000)
            logger.info("[pipeline] %-12s done in %dms", stage.label, stage.duration_ms)
            _activity_bus.emit({"type": "stage_end", "stage_id": stage_id, "label": stage.label,
                                "status": "success", "duration_ms": stage.duration_ms})
            return True
        except Exception as exc:
            stage.status = "failed"
            stage.error = str(exc)
            stage.duration_ms = int((time.time() - stage.started_at) * 1000)
            logger.error("[pipeline] %-12s failed: %s", stage.label, exc)
            _activity_bus.emit({"type": "stage_end", "stage_id": stage_id, "label": stage.label,
                                "status": "failed", "duration_ms": stage.duration_ms,
                                "error": str(exc)})
            return False
        finally:
            self._broadcast()

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    async def _observe(self) -> dict:
        """OBSERVE: single unified state ingestion boundary.

        Loads all three state domains in parallel so no domain is stale relative
        to another.  All reads happen here.  Downstream stages operate on this
        frozen snapshot — they do not make additional read calls to GitLab or
        MongoDB (except REFLECT, which re-fetches GitLab to verify ACT outcomes).
        """
        from config.settings import settings

        # Parallel load: repository state (GitLab) + graph state (MongoDB)
        self._repo, self._graph_data = await asyncio.gather(
            asyncio.to_thread(self._gitlab.snapshot),
            self._graph.snapshot(),
        )

        # Extract GitLab baseline — REFLECT diffs against this to determine what
        # actually changed as a result of ACT, vs what was already there.
        self._pre_run_gitlab_issues = self._repo.get("open_issues", [])
        self._pre_run_gitlab_snapshot = {
            "issue_iids": {i["iid"] for i in self._pre_run_gitlab_issues},
            "mr_iids":    {m["iid"] for m in self._repo.get("open_merge_requests", [])},
        }
        logger.info(
            "[observe] Baseline: %d open issues, %d open MRs",
            len(self._pre_run_gitlab_snapshot["issue_iids"]),
            len(self._pre_run_gitlab_snapshot["mr_iids"]),
        )

        # Repo summary metrics
        upstream_authors = self._repo.get("upstream_authors", [])
        codeowners = self._repo.get("codeowners", {})
        pipelines = self._repo.get("pipeline_status", [])
        failing_pipelines = [p for p in pipelines if p.get("status") == "failed"]
        is_fork = self._repo.get("is_fork", False)
        upstream_ratio = self._repo.get("upstream_author_ratio", 0.0)
        members = self._repo.get("members", [])

        if is_fork and upstream_ratio >= 0.7:
            lifecycle = "fresh_fork"
        elif not members:
            lifecycle = "uninitialized"
        elif len(members) == 1:
            lifecycle = "solo"
        else:
            lifecycle = "active"

        # Graph summary metrics (previously the separate observe_graph stage output)
        graph_developers  = len(self._graph_data.get("developers", []))
        graph_upstream    = len(self._graph_data.get("upstream_authors", []))
        graph_concentrated = len(self._graph_data.get("concentrated_modules", []))
        graph_findings    = len(self._graph_data.get("recent_findings", []))

        return {
            # Repository domain
            "members": len(members),
            "open_issues": len(self._pre_run_gitlab_issues),
            "open_mrs": len(self._repo.get("open_merge_requests", [])),
            "commit_contributors": len(self._repo.get("commit_contributors", [])),
            "upstream_authors": len(upstream_authors),
            "upstream_author_list": upstream_authors,
            "codeowners_entries": len(codeowners),
            "pipeline_passing": sum(1 for p in pipelines if p.get("status") == "success"),
            "pipeline_failing": len(failing_pipelines),
            "failing_pipeline_urls": [p.get("web_url") for p in failing_pipelines if p.get("web_url")],
            "mr_approvers_tracked": len(self._repo.get("mr_approvers", [])),
            "is_fork": is_fork,
            "upstream_author_ratio": upstream_ratio,
            "lifecycle_context": lifecycle,
            "fork_divergence": self._repo.get("fork_divergence"),
            # Graph domain (baseline memory state at run start)
            "graph_developers_tracked": graph_developers,
            "graph_upstream_tracked": graph_upstream,
            "graph_concentrated_modules": graph_concentrated,
            "graph_recent_findings": graph_findings,
            "demo_mode": settings.demo_mode,
            "demo_data_present": bool(self._graph_data.get("demo_data_present", False)),
        }

    async def _model(self) -> dict:
        """MODEL: integrate repository snapshot into the ownership graph.

        Walks top-level directories to build a per-module contributor map.
        This is the structural inference step — no agents, no GitLab reads beyond
        what gitlab_client already has cached from OBSERVE.
        """
        self._module_contributors = await asyncio.to_thread(
            self._gitlab.get_module_contributor_map
        )
        total_attributions = sum(len(v) for v in self._module_contributors.values())
        return {
            "modules_discovered": len(self._module_contributors),
            "module_paths": list(self._module_contributors.keys()),
            "total_attributions": total_attributions,
        }

    def _detect_high_attention_members(self) -> list[dict]:
        """Identify which members need investigator attention.

        Detection logic uses observable signals, not severity thresholds -
        it asks 'who should the agent look at,' not 'who is high risk.'
        Severity judgment is delegated to the investigator subagent.
        """
        from datetime import datetime, timedelta, timezone

        members = self._repo.get("members", [])
        commit_contributors = self._repo.get("commit_contributors", [])
        member_activity = self._repo.get("member_activity", {})  # populated below

        # Build a username/name -> dict lookup for members
        member_by_key: dict[str, dict] = {}
        for m in members:
            for key in (m.get("username", "").lower(), m.get("name", "").lower()):
                if key:
                    member_by_key[key] = m

        # Map each module to its sole or dominant internal contributor
        # using per-directory contributor data captured in map_modules.
        sole_owner_modules: dict[str, list[str]] = {}  # username -> [module paths]
        for module_path, contribs in self._module_contributors.items():
            internal = [c for c in contribs if not c.get("external", False) and c.get("commit_count", 0) > 0]
            if len(internal) == 1:
                top = internal[0]
                key = (top.get("name") or top.get("email") or "").lower()
                member_entry = member_by_key.get(key) or {"name": top.get("name"), "username": top.get("email", "").split("@")[0]}
                username = (member_entry.get("username") or top.get("name") or "unknown").lower()
                sole_owner_modules.setdefault(username, []).append(module_path)
            elif len(internal) >= 2:
                # Check for concentration: if top contributor has 3x+ the commits of #2
                internal_sorted = sorted(internal, key=lambda c: c.get("commit_count", 0), reverse=True)
                top, second = internal_sorted[0], internal_sorted[1]
                if top.get("commit_count", 0) >= 3 * max(second.get("commit_count", 1), 1):
                    key = (top.get("name") or top.get("email") or "").lower()
                    member_entry = member_by_key.get(key) or {"name": top.get("name"), "username": top.get("email", "").split("@")[0]}
                    username = (member_entry.get("username") or top.get("name") or "unknown").lower()
                    sole_owner_modules.setdefault(username, []).append(module_path)

        # Temporal signals from commit history (no GitLab member.created_at needed)
        now = datetime.now(timezone.utc)
        recent_window = timedelta(days=30)
        previously_active_window = timedelta(days=90)

        def _parse(ts: str):
            if not ts:
                return None
            try:
                # GitLab returns ISO 8601 with timezone
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                return None

        attention: list[dict] = []
        seen_members: set[str] = set()

        def _add(member: dict, reason: str, modules: list[str]):
            key = (member.get("username") or member.get("name") or "").lower()
            if not key or (key, reason) in seen_members:
                return
            seen_members.add((key, reason))
            attention.append({
                "member": member,
                "attention_reason": reason,
                "uniquely_owned_modules": modules,
            })

        # 1. Sole contributors - directly from per-module attribution
        for username, modules in sole_owner_modules.items():
            member = member_by_key.get(username) or {"username": username, "name": username}
            if len(modules) >= 2:
                _add(member, "multi_module_concentration", modules)
            else:
                _add(member, "sole_contributor", modules)

        # 2. Recently inactive / recent joiners - from commit timestamps
        for c in commit_contributors:
            if c.get("external"):
                continue
            name_key = (c.get("name") or "").lower()
            email_key = (c.get("email") or "").lower()
            activity = member_activity.get(name_key) or member_activity.get(email_key)
            if not activity:
                continue
            first = _parse(activity.get("first_commit", ""))
            last = _parse(activity.get("last_commit", ""))
            if not last:
                continue
            member_entry = member_by_key.get(name_key) or member_by_key.get(email_key) or {
                "name": c.get("name"), "username": email_key.split("@")[0] if email_key else name_key
            }
            username = (member_entry.get("username") or "").lower()
            modules = sole_owner_modules.get(username, [])

            # Recent joiner: first commit within last 30 days
            if first and (now - first) <= recent_window:
                _add(member_entry, "recent_joiner", modules)
            # Recently inactive: was active in the 30-90 day window, silent in last 30
            elif (now - last) > recent_window and (now - last) <= previously_active_window:
                _add(member_entry, "recently_inactive", modules)

        return attention

    async def _run_investigation(self) -> dict:
        """Investigation sub-step of ANALYZE.

        Spawns concurrent investigator subagents over modules, members, and drift.
        This is where the system stops being algorithmic — each subagent reads
        actual file content and produces a structured assessment with its own
        reasoning. No thresholds; the subagent's judgment is the output.
        """
        # Capture member activity for high-attention detection
        try:
            self._repo["member_activity"] = await asyncio.to_thread(
                self._gitlab.get_member_activity_dates
            )
        except Exception as exc:
            logger.warning("[analyze/investigate] member activity fetch failed: %s", exc)
            self._repo["member_activity"] = {}

        high_attention = self._detect_high_attention_members()
        logger.info("[analyze/investigate] High-attention members: %d", len(high_attention))

        # Member investigators - one per high-attention member, concurrent
        for item in high_attention:
            subject = (item["member"].get("username") or item["member"].get("name") or "?")
            _activity_bus.emit({"type": "subagent_spawn", "stage_id": "analyze",
                                "kind": "member", "subject": subject,
                                "reason": item["attention_reason"]})
        member_tasks = [
            investigator.investigate_member(
                member=item["member"],
                attention_reason=item["attention_reason"],
                uniquely_owned_modules=item["uniquely_owned_modules"],
                gitlab_client=self._gitlab,
            )
            for item in high_attention
        ]

        # Module investigators - one per discovered module, concurrent
        module_tasks = []
        for module_path, contribs in self._module_contributors.items():
            _activity_bus.emit({"type": "subagent_spawn", "stage_id": "analyze",
                                "kind": "module", "subject": module_path})
            module_tasks.append(
                investigator.investigate_module(
                    module_path=module_path,
                    contributors=contribs,
                    gitlab_client=self._gitlab,
                )
            )

        # Drift investigator - only if this is a fork that's behind
        fork_div = self._repo.get("fork_divergence")
        drift_task = None
        if fork_div and fork_div.get("commits_behind", 0) > 0:
            drift_task = investigator.investigate_drift(
                fork_divergence=fork_div,
                gitlab_client=self._gitlab,
            )

        # Cap concurrency from runtime config (default 10, hard max 20)
        cfg = await self._graph.get_runtime_config()
        max_inv = max(1, min(20, int(cfg.get("analyst_max_investigators", 10))))
        logger.info("[analyze/investigate] max concurrent investigators: %d", max_inv)
        sem = asyncio.Semaphore(max_inv)

        async def _bounded(coro):
            async with sem:
                return await coro

        all_tasks: list = list(member_tasks) + list(module_tasks)
        if drift_task is not None:
            all_tasks.append(drift_task)

        results = await asyncio.gather(*[_bounded(t) for t in all_tasks], return_exceptions=True)

        # Split results back by category
        m_count = len(member_tasks)
        mod_count = len(module_tasks)

        def _ok(r):
            if isinstance(r, Exception):
                logger.warning("[analyze/investigate] subagent raised: %s", r)
                return None
            return r

        member_results = [r for r in (_ok(x) for x in results[:m_count]) if r]
        module_results = [r for r in (_ok(x) for x in results[m_count:m_count + mod_count]) if r]
        drift_result = _ok(results[-1]) if drift_task is not None else None

        # Emit subagent results
        for item, result in zip(high_attention, member_results):
            subject = (item["member"].get("username") or item["member"].get("name") or "?")
            summary = result.get("knowledge_at_risk") or result.get("urgency_reasoning") or "investigated"
            _activity_bus.emit({"type": "subagent_result", "stage_id": "analyze",
                                "kind": "member", "subject": subject,
                                "summary": str(summary)[:200]})
        for module_path, result in zip(self._module_contributors.keys(), module_results):
            summary = result.get("transferability_assessment") or result.get("documentation_state") or "investigated"
            _activity_bus.emit({"type": "subagent_result", "stage_id": "analyze",
                                "kind": "module", "subject": module_path,
                                "summary": str(summary)[:200]})
        if drift_result and drift_result.get("investigated"):
            _activity_bus.emit({"type": "subagent_result", "stage_id": "analyze",
                                "kind": "drift", "subject": drift_result.get("upstream_project", "upstream"),
                                "summary": str(drift_result.get("urgency_assessment", "investigated"))[:200]})

        self._investigations = {
            "members": member_results,
            "modules": module_results,
            "drift": drift_result,
        }

        return {
            "high_attention_members": len(high_attention),
            "member_investigations": len(member_results),
            "module_investigations": len(module_results),
            "drift_investigated": drift_result is not None and drift_result.get("investigated", False),
        }

    async def _run_interpretation(self) -> dict:
        """Interpretation sub-step of ANALYZE.

        Central synthesis: analyst agent reasons over all investigator findings
        and produces qualitative concern-typed findings.  No thresholds — the
        agent's judgment is the output.
        """
        self._interpretation = await asyncio.to_thread(
            analyst_agent.analyze, self._repo, self._graph_data, self._investigations
        )
        findings = self._interpretation.get("findings", [])
        for f in findings:
            _activity_bus.emit({"type": "finding", "stage_id": "analyze",
                                "subject": str(f.get("subject", "?")),
                                "concern_type": str(f.get("concern_type", "?")),
                                "narrative": str(f.get("narrative", ""))[:300]})
        return {
            "finding_count": len(findings),
            "concern_types": sorted({f.get("concern_type", "?") for f in findings}),
            "synthesis": self._interpretation.get("synthesis"),
        }

    async def _analyze(self) -> dict:
        """ANALYZE: concurrent investigation + central synthesis.

        Runs investigation (parallel subagents) then interpretation (single
        synthesis agent) as sequential sub-steps within the same stage.
        Kept separate internally for parallelism and depth control; exposed as
        one stage to the UI for a clean 8-stage narrative.
        """
        inv = await self._run_investigation()
        interp = await self._run_interpretation()
        return {**inv, **interp}

    def _get_covered_subjects(self, issues: list[dict]) -> set[str]:
        """Return finding subjects already covered by open issues.

        Uses the same subject→title matching as _reflect() so that deduplication
        and reflection stay consistent — if reflect will confirm it, decide will
        not re-plan it.
        """
        findings = (self._interpretation or {}).get("findings", [])
        covered: set[str] = set()
        for f in findings:
            subject = str(f.get("subject", "")).lower().strip()
            if not subject:
                continue
            for iss in issues:
                if _subject_matches_title(subject, iss.get("title", "").lower()):
                    covered.add(subject)
                    break
        return covered

    async def _decide(self, pass_num: int = 1, prior_interventions: dict | None = None) -> dict:
        """DECIDE: select a bounded, deduplicated intervention set.

        Before calling the planner, filters out findings whose subjects are
        already covered by open issues — both from previous runs (OBSERVE
        baseline) and from earlier passes of this run (refreshed on pass 2+).
        This is the primary deduplication gate: the planner never sees a finding
        that already has an open issue, so it cannot re-propose it regardless of
        how it phrases the title.
        """
        # Refresh open issues on pass 2+ so the planner sees issues created
        # by earlier passes of this same run.
        if pass_num > 1:
            try:
                self._pre_run_gitlab_issues = await asyncio.to_thread(
                    self._gitlab.list_bot_issues
                )
                logger.info("[decide] Pass %d: refreshed to %d open issues",
                            pass_num, len(self._pre_run_gitlab_issues))
            except Exception as exc:
                logger.warning("[decide] Pass %d: failed to refresh issue list: %s", pass_num, exc)

        # Subject-based pre-filter: remove findings already covered by open issues.
        # This is done BEFORE calling the planner so it cannot propose duplicate work.
        covered = self._get_covered_subjects(self._pre_run_gitlab_issues)

        # On pass 2+, also mark subjects confirmed actioned by prior reflects.
        if pass_num > 1:
            for f in self._interpretation.get("annotated_findings", []):
                if f.get("actioned_at") or f.get("pre_existing"):
                    covered.add(str(f.get("subject", "")).lower().strip())

        all_findings = self._interpretation.get("findings", [])
        if covered:
            remaining = [
                f for f in all_findings
                if str(f.get("subject", "")).lower().strip() not in covered
            ]
            n_filtered = len(all_findings) - len(remaining)
            if n_filtered:
                logger.info("[decide] Pass %d: pre-filtered %d/%d already-covered finding(s)",
                            pass_num, n_filtered, len(all_findings))
            interpretation = {**self._interpretation, "findings": remaining}
        else:
            interpretation = self._interpretation

        self._plan = await asyncio.to_thread(
            planner_agent.plan, interpretation, self._repo, self._graph_data
        )

        # Secondary dedup: title-substring check catches anything the subject
        # matching misses (e.g. a subject not mentioned verbatim in the title).
        pre_titles = {
            iss.get("title", "").lower()
            for iss in self._pre_run_gitlab_issues
            if iss.get("title")
        }
        deduped = 0
        if pre_titles:
            filtered: list[dict] = []
            for action in self._plan.get("actions", []):
                if action.get("kind") == "create_issue":
                    planned_title = (action.get("params") or {}).get("title", "").lower()
                    if planned_title and any(
                        planned_title in pt or pt in planned_title
                        for pt in pre_titles
                    ):
                        logger.info("[decide] Title-dedup: '%s' matches pre-existing issue",
                                    planned_title)
                        deduped += 1
                        continue
                filtered.append(action)
            if deduped:
                self._plan["actions"] = filtered

        for action in self._plan.get("actions", []):
            params = action.get("params") or {}
            _activity_bus.emit({"type": "action_planned", "stage_id": f"decide_{pass_num}",
                                "kind": str(action.get("kind", "?")),
                                "title": str(params.get("title", json.dumps(params)[:80]))})
        return {
            "actions_planned": len(self._plan.get("actions", [])),
            "actions_deduplicated": deduped,
            "graph_updates_planned": len(self._plan.get("graph_updates", [])),
            "actions": self._plan.get("actions", []),
        }

    async def _act_single(self, pass_num: int = 1, prior_interventions: dict | None = None) -> dict:
        """ACT: execute one pass of the act agent.

        The stabilization loop lives in run(); this method handles exactly one
        pass — building prompt context, calling act_agent.act(), and emitting
        activity bus events.
        """
        actions = self._plan.get("actions") or []
        stage_id = f"act_{pass_num}"

        if pass_num == 1:
            if actions:
                lines = [f"Executing {len(actions)} planned action(s):\n"]
                for a in actions[:8]:
                    kind  = a.get("kind", "?")
                    title = (a.get("params") or {}).get("title", "")
                    lines.append(f"- `{kind}`: {title}")
                if len(actions) > 8:
                    lines.append(f"- (+{len(actions) - 8} more)")
                _activity_bus.emit({"type": "agent_text", "stage_id": stage_id,
                                    "text": "\n".join(lines)})
            else:
                _activity_bus.emit({"type": "agent_text", "stage_id": stage_id,
                                    "text": "No actions planned - assessing project state."})
        else:
            _activity_bus.emit({
                "type": "agent_text", "stage_id": stage_id,
                "text": f"Pass {pass_num}: executing remaining unresolved actions...",
            })

        result = await act_agent.act(
            self._interpretation,
            self._repo,
            self._plan,
            prior_interventions=prior_interventions,
        )

        return {
            "executed":            result.get("executed", 0),
            "failed":              result.get("failed", 0),
            "details":             result.get("details", []),
            "mcp_calls":           result.get("mcp_calls", []),
            "summary":             result.get("summary"),
            "boundary_violations": result.get("boundary_violations", []),
            "trace":               result.get("trace", []),
        }

    async def _close_stale_bot_issues(self, pre_act_issues: list[dict]) -> int:
        """Close open bot issues whose subject is no longer in the current findings.

        Also closes old issues that were superseded by a new issue the act agent
        just created for the same subject.

        Matching heuristic: a finding subject (username or module path) is searched
        for as a substring in the issue title (case-insensitive). This is intentionally
        broad - it is better to leave a marginally relevant issue open than to close
        something incorrectly.

        Returns the number of issues closed.
        """
        if not pre_act_issues:
            return 0

        # Build the set of subjects the current run still considers relevant.
        current_subjects: set[str] = {
            str(f.get("subject", "")).lower().strip()
            for f in (self._interpretation or {}).get("findings", [])
            if f.get("subject")
        }

        # Re-fetch to discover issues the act agent created during this run.
        post_act_issues: list[dict] = []
        try:
            post_act_issues = await asyncio.to_thread(self._gitlab.list_bot_issues)
        except Exception as exc:
            logger.warning("[act] Post-act issue fetch failed - skipping stale cleanup: %s", exc)
            return 0

        pre_iids = {i["iid"] for i in pre_act_issues}

        # Map subject → newly created issue (for superseded-by links)
        new_by_subject: dict[str, dict] = {}
        for iss in post_act_issues:
            if iss["iid"] not in pre_iids:
                title_lower = iss["title"].lower()
                for sub in current_subjects:
                    if sub and sub in title_lower:
                        new_by_subject[sub] = iss
                        break

        closed = 0
        for old_iss in pre_act_issues:
            title_lower = old_iss["title"].lower()

            # Is any current finding subject mentioned in this issue's title?
            matched_subject = next(
                (s for s in current_subjects if s and s in title_lower), None
            )

            if matched_subject is None:
                # Subject no longer in findings - issue is stale
                reason = "stale (subject no longer in current findings)"
                superseded_by = None
            elif matched_subject in new_by_subject:
                # A brand-new issue covers the same subject - old one is superseded
                reason = f"superseded by #{new_by_subject[matched_subject]['iid']}"
                superseded_by = new_by_subject[matched_subject]
            else:
                continue  # still relevant, leave it open

            try:
                await asyncio.to_thread(
                    self._gitlab.close_stale_bot_issue,
                    old_iss["iid"],
                    superseded_by,
                )
                closed += 1
                logger.info(
                    "[act] Closed bot issue #%d ('%s') - %s",
                    old_iss["iid"], old_iss["title"][:60], reason,
                )
            except Exception as exc:
                logger.warning(
                    "[act] Failed to close bot issue #%d: %s", old_iss["iid"], exc
                )

        return closed

    async def _reflect(self) -> dict:
        """REFLECT: external state reconciliation after ACT.

        Re-fetches GitLab state and diffs against the OBSERVE baseline to
        determine which planned actions actually materialized, which findings
        already had open coverage, and which went unaddressed this cycle.

        This is the only stage that bridges intended actions and observed reality.
        Writes causal annotations into self._interpretation for PERSIST to store.
        """
        # Re-fetch post-ACT GitLab state (lightweight — bot issues only)
        try:
            post_act_issues = await asyncio.to_thread(self._gitlab.list_bot_issues)
        except Exception as exc:
            logger.warning("[reflect] GitLab re-fetch failed: %s", exc)
            post_act_issues = []

        pre_iids = self._pre_run_gitlab_snapshot.get("issue_iids", set())

        # Build title → issue lookup for matching findings to issues
        post_by_title: dict[str, dict] = {
            iss["title"].lower(): iss for iss in post_act_issues
        }

        findings = (self._interpretation or {}).get("findings", [])
        newly_created_iids: list[int] = []
        pre_existing_iids: list[int] = []
        unaddressed_subjects: list[str] = []
        annotated: list[dict] = []

        for f in findings:
            subject = str(f.get("subject", "")).lower().strip()
            annotation: dict = {
                "actioned_at": None,
                "gitlab_iid": None,
                "pre_existing": False,
                "duplicate_of": None,
            }

            matched: dict | None = None
            if subject:
                for title_lower, iss in post_by_title.items():
                    if _subject_matches_title(subject, title_lower):
                        matched = iss
                        break

            if matched:
                annotation["gitlab_iid"] = matched["iid"]
                if matched["iid"] in pre_iids:
                    annotation["pre_existing"] = True
                    pre_existing_iids.append(matched["iid"])
                    logger.info("[reflect] Finding '%s' → pre-existing issue #%d", f.get("subject"), matched["iid"])
                else:
                    annotation["actioned_at"] = time.time()
                    newly_created_iids.append(matched["iid"])
                    logger.info("[reflect] Finding '%s' → new issue #%d confirmed", f.get("subject"), matched["iid"])
            else:
                unaddressed_subjects.append(str(f.get("subject", "?")))

            annotated.append({**f, **annotation})

        # Store annotated findings so PERSIST can write causal metadata
        self._interpretation["annotated_findings"] = annotated

        self._reflect_result = {
            "findings_total": len(findings),
            "findings_actioned": len(newly_created_iids),
            "findings_pre_existing": len(pre_existing_iids),
            "findings_unaddressed": len(unaddressed_subjects),
            "newly_created_iids": newly_created_iids,
            "unaddressed_subjects": unaddressed_subjects[:10],  # cap for output size
        }
        logger.info(
            "[reflect] %d actioned, %d pre-existing, %d unaddressed (of %d findings)",
            len(newly_created_iids), len(pre_existing_iids),
            len(unaddressed_subjects), len(findings),
        )
        return self._reflect_result

    async def _persist(self) -> dict:
        count, total = 0, len(self._plan.get("graph_updates", []))
        for update in self._plan.get("graph_updates", []):
            collection = update.get("collection")
            data = update.get("data", {})
            try:
                if collection == "modules":
                    from graph.models import ModuleNode
                    await self._graph.upsert_module(ModuleNode(**data))
                elif collection == "developers":
                    from graph.models import DeveloperNode
                    await self._graph.upsert_developer(DeveloperNode(**data))
                elif collection == "tasks":
                    from graph.models import TaskNode
                    await self._graph.upsert_task(TaskNode(**data))
                elif collection == "contributions":
                    from graph.models import ContributionEdge
                    await self._graph.upsert_contribution(ContributionEdge(**data))
                count += 1
            except Exception as exc:
                logger.error("[pipeline] Graph update failed (%s): %s", collection, exc)
        # Persist observed commit contributors (internal + external/upstream)
        try:
            from graph.models import ContributionEdge, DeveloperNode
            members = self._repo.get("members", [])
            member_by_username = {m.get("username", "").lower(): m for m in members if m.get("username")}
            member_by_name = {m.get("name", "").lower(): m for m in members if m.get("name")}
            for c in self._repo.get("commit_contributors", []):
                name = c.get("name") or ""
                email = c.get("email") or ""
                is_external = bool(c.get("external", False))

                username = None
                gitlab_id = None
                if not is_external:
                    key = name.lower()
                    if key in member_by_username:
                        m = member_by_username[key]
                        username = m.get("username")
                        gitlab_id = m.get("id")
                    elif key in member_by_name:
                        m = member_by_name[key]
                        username = m.get("username")
                        gitlab_id = m.get("id")

                if not username:
                    # Derive a slug from email local-part or from the display name.
                    # Replace "/" so GitLab namespace paths like "gitlab-org/maintainers/gitlab-pages"
                    # (which appear as commit-author names for bots/service accounts) don't pollute
                    # the graph with fake usernames that look like module paths.
                    raw = email.split("@", 1)[0] if email else name.replace(" ", "_")
                    username = raw.replace("/", "_")[:64] or "unknown"

                dev = DeveloperNode(
                    gitlab_id=gitlab_id,
                    username=username,
                    name=(name or email or username),
                    active=not is_external,
                    external=is_external,
                    first_seen=_parse_iso_dt(c.get("first_commit_at")),
                    last_seen=_parse_iso_dt(c.get("last_commit_at")),
                )
                try:
                    await self._graph.upsert_developer(dev)
                except Exception:
                    pass

                edge = ContributionEdge(
                    developer_username=username,
                    module_path="repository",
                    commit_count=c.get("commit_count", 1),
                    lines_changed=0,
                    expertise_score=0.0,
                    external=is_external,
                    developer_identity=(email or name or username),
                )
                try:
                    await self._graph.upsert_contribution(edge)
                except Exception as exc:
                    logger.error("[pipeline] Persisting observed contribution failed for %s: %s", username, exc)
                total += 1
        except Exception as exc:
            logger.error("[pipeline] Persisting observed contributions failed: %s", exc)

        # Per-directory knowledge attribution - WHO KNOWS WHAT PART of the repo.
        # This is the core of the knowledge graph: module nodes keyed by directory path,
        # with contribution edges carrying relative expertise scores per module.
        try:
            from graph.models import ContributionEdge, DeveloperNode, ModuleNode
            _members = self._repo.get("members", [])
            member_by_username = {m.get("username", "").lower(): m for m in _members if m.get("username")}
            member_by_name = {m.get("name", "").lower(): m for m in _members if m.get("name")}
            for module_path, contribs in self._module_contributors.items():
                try:
                    await self._graph.upsert_module(ModuleNode(path=module_path, owners=[]))
                except Exception:
                    pass

                max_commits = max((c.get("commit_count", 1) for c in contribs), default=1)

                for c in contribs:
                    name = c.get("name") or ""
                    email = c.get("email") or ""
                    is_external = bool(c.get("external", False))
                    commit_count = c.get("commit_count", 1)

                    username = None
                    gitlab_id = None
                    if not is_external:
                        key = name.lower()
                        if key in member_by_username:
                            m = member_by_username[key]
                            username = m.get("username")
                            gitlab_id = m.get("id")
                        elif key in member_by_name:
                            m = member_by_name[key]
                            username = m.get("username")
                            gitlab_id = m.get("id")
                    if not username:
                        raw = email.split("@", 1)[0] if email else name.replace(" ", "_")
                        username = raw.replace("/", "_")[:64] or "unknown"

                    dev = DeveloperNode(
                        gitlab_id=gitlab_id,
                        username=username,
                        name=(name or email or username),
                        active=not is_external,
                        external=is_external,
                        first_seen=_parse_iso_dt(c.get("first_commit_at")),
                        last_seen=_parse_iso_dt(c.get("last_commit_at")),
                    )
                    try:
                        await self._graph.upsert_developer(dev)
                    except Exception:
                        pass

                    # Expertise score is relative within this module:
                    # the top contributor scores 1.0, others are proportional.
                    expertise_score = round(min(1.0, commit_count / max_commits), 4)

                    edge = ContributionEdge(
                        developer_username=username,
                        module_path=module_path,
                        commit_count=commit_count,
                        lines_changed=0,
                        expertise_score=expertise_score,
                        external=is_external,
                        developer_identity=(email or name or username),
                    )
                    try:
                        await self._graph.upsert_contribution(edge)
                    except Exception as exc:
                        logger.error("[pipeline] Dir contribution upsert failed %s → %s: %s", username, module_path, exc)
                    total += 1
        except Exception as exc:
            logger.error("[pipeline] Per-directory knowledge attribution failed: %s", exc)

        # Monthly contribution history - timeline buckets per (developer, module, YYYY-MM)
        try:
            from graph.models import ContributionHistory
            _members_h = self._repo.get("members", [])
            _by_uname_h = {m.get("username", "").lower(): m for m in _members_h if m.get("username")}
            _by_name_h = {m.get("name", "").lower(): m for m in _members_h if m.get("name")}
            for module_path, contribs in self._module_contributors.items():
                for c in contribs:
                    monthly_counts = c.get("monthly_counts", {})
                    if not monthly_counts:
                        continue
                    name = c.get("name") or ""
                    email = c.get("email") or ""
                    is_external = bool(c.get("external", False))
                    username = None
                    if not is_external:
                        key = name.lower()
                        if key in _by_uname_h:
                            username = _by_uname_h[key].get("username")
                        elif key in _by_name_h:
                            username = _by_name_h[key].get("username")
                    if not username:
                        raw = email.split("@", 1)[0] if email else name.replace(" ", "_")
                        username = raw.replace("/", "_")[:64] or "unknown"
                    for year_month, count in monthly_counts.items():
                        if not year_month:
                            continue
                        record = ContributionHistory(
                            developer_username=username,
                            module_path=module_path,
                            year_month=year_month,
                            commit_count=count,
                            external=is_external,
                        )
                        try:
                            await self._graph.upsert_contribution_history(record)
                        except Exception as exc:
                            logger.error("[pipeline] Contribution history upsert failed %s/%s/%s: %s", username, module_path, year_month, exc)
        except Exception as exc:
            logger.error("[pipeline] Monthly contribution history storage failed: %s", exc)

        # Seed CODEOWNERS into module ownership (declared owners = ground truth, score 1.0)
        try:
            from graph.models import ModuleNode, ContributionEdge
            codeowners = self._repo.get("codeowners", {})
            for path_pattern, owners in codeowners.items():
                module_path = path_pattern.lstrip("/").rstrip("*").rstrip("/") or "repository"
                try:
                    await self._graph.upsert_module(ModuleNode(path=module_path, owners=owners))
                except Exception:
                    pass
                for owner in owners:
                    edge = ContributionEdge(
                        developer_username=owner,
                        module_path=module_path,
                        commit_count=0,
                        lines_changed=0,
                        expertise_score=1.0,
                        external=False,
                        developer_identity=owner,
                    )
                    try:
                        await self._graph.upsert_contribution(edge)
                    except Exception as exc:
                        logger.error("[pipeline] CODEOWNERS contribution upsert failed for %s: %s", owner, exc)
                    total += 1
        except Exception as exc:
            logger.error("[pipeline] Seeding CODEOWNERS into graph failed: %s", exc)

        # Persist MR approvers as implicit knowledge holders (expertise_score 0.6)
        try:
            from graph.models import ContributionEdge
            for mr_record in self._repo.get("mr_approvers", []):
                branch = mr_record.get("source_branch", "repository")
                module_path = branch.replace("/", "_")[:64] or "repository"
                for approver in mr_record.get("approved_by", []):
                    edge = ContributionEdge(
                        developer_username=approver,
                        module_path=module_path,
                        commit_count=0,
                        lines_changed=0,
                        expertise_score=0.6,
                        external=False,
                        developer_identity=approver,
                    )
                    try:
                        await self._graph.upsert_contribution(edge)
                    except Exception as exc:
                        logger.error("[pipeline] MR approver contribution upsert failed for %s: %s", approver, exc)
                    total += 1
        except Exception as exc:
            logger.error("[pipeline] Persisting MR approver contributions failed: %s", exc)

        # Refresh bus_factor measurements only. No scoring, no aggregation.
        # Severity lives in Finding records (persisted below), not on modules.
        rescored = await self._refresh_bus_factors()
        logger.info("[persist] Refreshed bus_factor on %d module(s)", rescored)

        # Persist findings (with REFLECT causal annotations if available).
        findings_saved = await self._persist_findings()
        logger.info("[persist] Persisted %d finding(s)", findings_saved)

        # Persist agent actions to the actions log
        actions_saved = 0
        try:
            from graph.models import ActionRecord
            run_id = self._current_run.run_id if self._current_run else "unknown"
            run_summary = self._act_result.get("summary")
            act_details = self._act_result.get("details", [])
            for d in act_details:
                await self._graph.insert_action(ActionRecord(
                    run_id=run_id,
                    tool=d.get("kind", "unknown"),
                    detail=d.get("detail", ""),
                    success=True,
                    run_summary=run_summary,
                ))
                actions_saved += 1
            if not act_details:
                # Record the run even when no actions were taken - shows agent assessed
                await self._graph.insert_action(ActionRecord(
                    run_id=run_id,
                    tool="assess",
                    detail=run_summary or "Agent assessed project state - no actions required.",
                    success=True,
                    run_summary=run_summary,
                ))
                actions_saved += 1
        except Exception as exc:
            logger.error("[pipeline] Persisting agent actions failed: %s", exc)

        return {
            "updated": count,
            "total": total,
            "modules_bus_factor_refreshed": rescored,
            "findings_saved": findings_saved,
            "actions_saved": actions_saved,
        }

    async def _refresh_bus_factors(self) -> int:
        """Recompute bus_factor for each tracked module.

        bus_factor is a measurement - a count of internal committers covering
        80% of commits. No severity attached. No scoring. The analyst decides
        what to make of it in context.
        """
        from graph.models import ModuleNode
        from risk.forecasting import compute_bus_factor

        try:
            all_modules = await self._graph.modules.find({}, {"_id": 0}).to_list(None)
        except Exception as exc:
            logger.error("[pipeline] bus_factor refresh: failed to fetch modules: %s", exc)
            return 0

        updated = 0
        module_fields = set(ModuleNode.model_fields.keys())

        for module in all_modules:
            path = module["path"]
            try:
                all_contribs = await self._graph.get_module_contributors(path)
                internal_committers = [
                    c for c in all_contribs
                    if not c.get("external", False) and c.get("commit_count", 0) > 0
                ]
                bus_factor = compute_bus_factor(internal_committers)
                module_data = {k: v for k, v in module.items() if k in module_fields}
                module_data["bus_factor"] = bus_factor
                await self._graph.upsert_module(ModuleNode(**module_data))
                updated += 1
            except Exception as exc:
                logger.error("[pipeline] bus_factor refresh failed for %s: %s", path, exc)

        return updated

    async def _persist_findings(self) -> int:
        """Persist findings to the findings collection.

        Uses annotated findings from REFLECT (with actioned_at, pre_existing,
        gitlab_iid causal metadata) when available.  Falls back to raw
        interpretation findings if REFLECT did not run or failed.
        """
        from graph.models import Finding

        # Prefer annotated findings (produced by REFLECT) for causal traceability
        findings = (
            (self._interpretation or {}).get("annotated_findings")
            or (self._interpretation or {}).get("findings", [])
            or []
        )
        if not findings:
            return 0
        run_id = self._current_run.run_id if self._current_run else None
        saved = 0
        for f in findings:
            try:
                finding = Finding(
                    run_id=run_id,
                    subject=str(f.get("subject", "?")),
                    concern_type=str(f.get("concern_type", "unspecified")),
                    narrative=str(f.get("narrative", "")),
                    evidence=list(f.get("evidence", []) or []),
                    recommended_actions=list(f.get("recommended_actions", []) or []),
                )
                await self._graph.insert_finding(finding)
                saved += 1
            except Exception as exc:
                logger.error("[persist] insert_finding failed: %s", exc)
        return saved

    async def _summary(self) -> dict:
        # Exclude the summary stage itself - it's "running" when this executes, so counting
        # it would give N-1/N. Report only the substantive pipeline stages.
        all_stages = self._current_run.stages if self._current_run else []
        stages = [s for s in all_stages if s.id != "summary"]
        succeeded = sum(1 for s in stages if s.status == "success")
        failed    = sum(1 for s in stages if s.status == "failed")
        skipped   = sum(1 for s in stages if s.status == "skipped")
        total_ms  = sum(s.duration_ms or 0 for s in all_stages if s.duration_ms is not None)

        findings    = (self._interpretation or {}).get("findings", [])
        actions     = (self._plan or {}).get("actions", [])
        graph_upds  = (self._plan or {}).get("graph_updates", [])
        synthesis   = (self._interpretation or {}).get("synthesis", "") or ""

        # ── Natural language narrative ────────────────────────────────────────
        parts: list[str] = []

        # Duration string
        total_s = total_ms / 1000
        if total_s < 60:
            dur = f"{total_s:.0f}s"
        else:
            dur = f"{int(total_s // 60)}m {int(total_s % 60)}s"

        # Stage outcome
        n = len(stages)
        if failed == 0 and skipped == 0:
            parts.append(f"All {n} stages completed in {dur}.")
        elif failed > 0:
            parts.append(f"{succeeded}/{n} stages succeeded in {dur}; {failed} failed.")
        else:
            parts.append(f"{succeeded}/{n} stages ran in {dur} ({skipped} skipped).")

        # Findings
        nf = len(findings)
        if nf == 0:
            parts.append("No continuity concerns were identified this run.")
        else:
            types = sorted({f.get("concern_type", "unknown") for f in findings})
            type_str = ", ".join(t.replace("_", " ") for t in types[:3])
            if len(types) > 3:
                type_str += f" and {len(types) - 3} more"
            parts.append(
                f"{nf} finding{'s' if nf != 1 else ''} identified "
                f"({type_str})."
            )

        # Actions
        na = len(actions)
        stab_passes = (self._act_result or {}).get("stabilization_passes", 1)
        stale_closed = (self._act_result or {}).get("stale_issues_closed", 0)
        if na > 0:
            action_str = (
                f"{na} remediation action{'s' if na != 1 else ''} "
                f"{'were' if na != 1 else 'was'} executed in GitLab"
            )
            if stab_passes > 1:
                action_str += f" across {stab_passes} stabilization passes"
            action_str += "."
            if stale_closed:
                action_str += f" {stale_closed} stale issue{'s' if stale_closed != 1 else ''} closed."
            parts.append(action_str)
        elif nf > 0:
            parts.append("No remediation actions were taken.")

        # Analyst synthesis (qualitative conclusion) - the richest part
        if synthesis:
            trimmed = synthesis if len(synthesis) <= 500 else synthesis[:500].rsplit(" ", 1)[0] + "…"
            parts.append(trimmed)

        narrative = " ".join(parts)
        # ─────────────────────────────────────────────────────────────────────

        return {
            "stages_total": n,
            "stages_succeeded": succeeded,
            "stages_failed": failed,
            "stages_skipped": skipped,
            "findings_count": nf,
            "actions_planned": na,
            "graph_updates_planned": len(graph_upds),
            "stabilization_passes": (self._act_result or {}).get("stabilization_passes", 1),
            "stale_issues_closed": (self._act_result or {}).get("stale_issues_closed", 0),
            "total_duration_ms": total_ms,
            "narrative": narrative,
        }
