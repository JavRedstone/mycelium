import asyncio
import json
import logging
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


class _PipelineCancelled(Exception):
    pass


STAGE_DEFS = [
    {"id": "observe_repo", "label": "Observe Repo", "description": "Read GitLab project state: members, issues, MRs, pipelines, CODEOWNERS, fork divergence"},
    {"id": "map_modules", "label": "Map Modules", "description": "Map per-directory upstream authorship — who knows what part of the codebase"},
    {"id": "investigate", "label": "Investigate", "description": "Spawn concurrent subagents to read actual file content and judge transferability"},
    {"id": "observe_graph", "label": "Observe Graph", "description": "Read continuity graph snapshot"},
    {"id": "interpret", "label": "Interpret", "description": "Reason over signals + investigator findings; produce qualitative findings"},
    {"id": "plan", "label": "Plan", "description": "Build recommended remediation actions"},
    {"id": "act", "label": "Execute", "description": "Perform GitLab operations from plan"},
    {"id": "learn", "label": "Persist", "description": "Write back knowledge graph updates and findings"},
    {"id": "summary", "label": "Summary", "description": "Compile run-level outcome metrics"},
]


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
        self._interpretation: dict = {}      # {"synthesis": "...", "findings": [...]}
        self._plan: dict = {}
        self._act_result: dict = {}

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
            logger.warning("[pipeline] Run requested but already running — skipping")
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
            if not await self._execute("observe_repo", self._observe_repo):
                run.status = "failed"
                return

            await self._execute("map_modules", self._observe_modules)

            # Investigate is best-effort: if subagents fail the pipeline still continues
            # with whatever findings were collected.
            await self._execute("investigate", self._investigate)

            if not await self._execute("observe_graph", self._observe_graph):
                run.status = "failed"
                return

            if not await self._execute("interpret", self._interpret):
                run.status = "failed"
                return

            if not await self._execute("plan", self._plan_stage):
                run.status = "failed"
                return

            await self._execute("act", self._act)
            await self._execute("learn", self._learn)
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

    async def _observe_repo(self) -> dict:
        self._repo = await asyncio.to_thread(self._gitlab.snapshot)
        upstream_authors = self._repo.get("upstream_authors", [])
        codeowners = self._repo.get("codeowners", {})
        pipelines = self._repo.get("pipeline_status", [])
        failing_pipelines = [p for p in pipelines if p.get("status") == "failed"]
        is_fork = self._repo.get("is_fork", False)
        upstream_ratio = self._repo.get("upstream_author_ratio", 0.0)
        members = self._repo.get("members", [])

        # Infer project lifecycle from observable signals.
        # Agents use this to calibrate how they interpret risk scores.
        if is_fork and upstream_ratio >= 0.7:
            lifecycle = "fresh_fork"   # team is onboarding, dark knowledge is expected
        elif not members:
            lifecycle = "uninitialized"
        elif len(members) == 1:
            lifecycle = "solo"
        else:
            lifecycle = "active"

        fork_divergence = self._repo.get("fork_divergence")
        return {
            "members": len(members),
            "open_issues": len(self._repo.get("open_issues", [])),
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
            "fork_divergence": fork_divergence,
        }

    async def _observe_modules(self) -> dict:
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

        Detection logic uses observable signals, not severity thresholds —
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

        # 1. Sole contributors — directly from per-module attribution
        for username, modules in sole_owner_modules.items():
            member = member_by_key.get(username) or {"username": username, "name": username}
            if len(modules) >= 2:
                _add(member, "multi_module_concentration", modules)
            else:
                _add(member, "sole_contributor", modules)

        # 2. Recently inactive / recent joiners — from commit timestamps
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

    async def _investigate(self) -> dict:
        """Spawn concurrent investigator subagents over modules, members, and drift.

        This is where the system stops being algorithmic. Each subagent reads
        actual file content (via the GitLab client) and produces a structured
        assessment with its own reasoning. No thresholds — the subagent's
        judgment is the output.
        """
        # Capture member activity for high-attention detection
        try:
            self._repo["member_activity"] = await asyncio.to_thread(
                self._gitlab.get_member_activity_dates
            )
        except Exception as exc:
            logger.warning("[investigate] member activity fetch failed: %s", exc)
            self._repo["member_activity"] = {}

        high_attention = self._detect_high_attention_members()
        logger.info("[investigate] High-attention members: %d", len(high_attention))

        # Member investigators — one per high-attention member, concurrent
        for item in high_attention:
            subject = (item["member"].get("username") or item["member"].get("name") or "?")
            _activity_bus.emit({"type": "subagent_spawn", "stage_id": "investigate",
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

        # Module investigators — one per discovered module, concurrent
        module_tasks = []
        for module_path, contribs in self._module_contributors.items():
            _activity_bus.emit({"type": "subagent_spawn", "stage_id": "investigate",
                                "kind": "module", "subject": module_path})
            module_tasks.append(
                investigator.investigate_module(
                    module_path=module_path,
                    contributors=contribs,
                    gitlab_client=self._gitlab,
                )
            )

        # Drift investigator — only if this is a fork that's behind
        fork_div = self._repo.get("fork_divergence")
        drift_task = None
        if fork_div and fork_div.get("commits_behind", 0) > 0:
            drift_task = investigator.investigate_drift(
                fork_divergence=fork_div,
                gitlab_client=self._gitlab,
            )

        # Run everything concurrently
        all_tasks: list = list(member_tasks) + list(module_tasks)
        if drift_task is not None:
            all_tasks.append(drift_task)

        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # Split results back by category
        m_count = len(member_tasks)
        mod_count = len(module_tasks)

        def _ok(r):
            if isinstance(r, Exception):
                logger.warning("[investigate] subagent raised: %s", r)
                return None
            return r

        member_results = [r for r in (_ok(x) for x in results[:m_count]) if r]
        module_results = [r for r in (_ok(x) for x in results[m_count:m_count + mod_count]) if r]
        drift_result = _ok(results[-1]) if drift_task is not None else None

        # Emit subagent results
        for item, result in zip(high_attention, member_results):
            subject = (item["member"].get("username") or item["member"].get("name") or "?")
            summary = result.get("knowledge_at_risk") or result.get("urgency_reasoning") or "investigated"
            _activity_bus.emit({"type": "subagent_result", "stage_id": "investigate",
                                "kind": "member", "subject": subject,
                                "summary": str(summary)[:200]})
        for module_path, result in zip(self._module_contributors.keys(), module_results):
            summary = result.get("transferability_assessment") or result.get("documentation_state") or "investigated"
            _activity_bus.emit({"type": "subagent_result", "stage_id": "investigate",
                                "kind": "module", "subject": module_path,
                                "summary": str(summary)[:200]})
        if drift_result and drift_result.get("investigated"):
            _activity_bus.emit({"type": "subagent_result", "stage_id": "investigate",
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
            "members": member_results,
            "modules": module_results,
            "drift": drift_result,
        }

    async def _observe_graph(self) -> dict:
        from config.settings import settings
        self._graph_data = await self._graph.snapshot()
        return {
            "developers_tracked": len(self._graph_data.get("developers", [])),
            "upstream_authors_tracked": len(self._graph_data.get("upstream_authors", [])),
            "concentrated_modules": len(self._graph_data.get("concentrated_modules", [])),
            "open_tasks_tracked": len(self._graph_data.get("open_tasks", [])),
            "recent_findings": len(self._graph_data.get("recent_findings", [])),
            "demo_mode": settings.demo_mode,
            "demo_data_present": bool(self._graph_data.get("demo_data_present", False)),
        }

    async def _interpret(self) -> dict:
        """Continuity interpretation stage — replaces the old 'analyze' stage.

        Produces qualitative findings (no scores) by reasoning over signals
        plus investigator outputs.
        """
        self._interpretation = await asyncio.to_thread(
            analyst_agent.analyze, self._repo, self._graph_data, self._investigations
        )
        findings = self._interpretation.get("findings", [])
        for f in findings:
            _activity_bus.emit({"type": "finding", "stage_id": "interpret",
                                "subject": str(f.get("subject", "?")),
                                "concern_type": str(f.get("concern_type", "?")),
                                "narrative": str(f.get("narrative", ""))[:300]})
        return {
            "synthesis": self._interpretation.get("synthesis"),
            "finding_count": len(findings),
            "findings": findings,
            "concern_types": sorted({f.get("concern_type", "?") for f in findings}),
        }

    async def _plan_stage(self) -> dict:
        self._plan = await asyncio.to_thread(
            planner_agent.plan, self._interpretation, self._repo, self._graph_data
        )
        for action in self._plan.get("actions", []):
            params = action.get("params") or {}
            _activity_bus.emit({"type": "action_planned", "stage_id": "plan",
                                "kind": str(action.get("kind", "?")),
                                "title": str(params.get("title", json.dumps(params)[:80]))})
        return {
            "actions_planned": len(self._plan.get("actions", [])),
            "graph_updates_planned": len(self._plan.get("graph_updates", [])),
            "actions": self._plan.get("actions", []),
        }

    async def _act(self) -> dict:
        actions = self._plan.get("actions") or []
        if actions:
            lines = [f"Executing **{len(actions)}** planned action(s):\n"]
            for a in actions[:8]:
                kind = a.get("kind", "?")
                title = (a.get("params") or {}).get("title", "")
                lines.append(f"- `{kind}`: {title}")
            if len(actions) > 8:
                lines.append(f"- *(+{len(actions) - 8} more)*")
            _activity_bus.emit({"type": "agent_text", "stage_id": "act",
                                "text": "\n".join(lines)})
        else:
            _activity_bus.emit({"type": "agent_text", "stage_id": "act",
                                "text": "No actions planned — assessing project state."})
        # act_agent.act is a native coroutine — uses MCP subprocess + async Gemini
        self._act_result = await act_agent.act(self._interpretation, self._repo, self._plan)
        return self._act_result

    async def _learn(self) -> dict:
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

        # Per-directory knowledge attribution — WHO KNOWS WHAT PART of the repo.
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

        # Monthly contribution history — timeline buckets per (developer, module, YYYY-MM)
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
        logger.info("[pipeline] Refreshed bus_factor on %d module(s)", rescored)

        # Persist findings produced by the interpret stage. These replace the
        # old continuity_risk_score field on modules entirely.
        findings_saved = await self._persist_findings()
        logger.info("[pipeline] Persisted %d finding(s)", findings_saved)

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
                # Record the run even when no actions were taken — shows agent assessed
                await self._graph.insert_action(ActionRecord(
                    run_id=run_id,
                    tool="assess",
                    detail=run_summary or "Agent assessed project state — no actions required.",
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

        bus_factor is a measurement — a count of internal committers covering
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
        """Persist analyst-produced findings to the findings collection.

        Findings replace the old continuity_risk_score field. Each finding is a
        qualitative record (subject, concern_type, narrative, evidence,
        recommended_actions) tied to this pipeline run.
        """
        from graph.models import Finding

        findings = (self._interpretation or {}).get("findings", []) or []
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
                logger.error("[pipeline] insert_finding failed: %s", exc)
        return saved

    async def _summary(self) -> dict:
        # Exclude the summary stage itself — it's "running" when this executes, so counting
        # it would give N-1/N. Report only the substantive pipeline stages.
        all_stages = self._current_run.stages if self._current_run else []
        stages = [s for s in all_stages if s.id != "summary"]
        succeeded = sum(1 for s in stages if s.status == "success")
        failed = sum(1 for s in stages if s.status == "failed")
        skipped = sum(1 for s in stages if s.status == "skipped")
        total_ms = sum(s.duration_ms or 0 for s in all_stages if s.duration_ms is not None)
        return {
            "stages_total": len(stages),
            "stages_succeeded": succeeded,
            "stages_failed": failed,
            "stages_skipped": skipped,
            "findings_count": len((self._interpretation or {}).get("findings", [])),
            "actions_planned": len((self._plan or {}).get("actions", [])),
            "graph_updates_planned": len((self._plan or {}).get("graph_updates", [])),
            "total_duration_ms": total_ms,
        }
