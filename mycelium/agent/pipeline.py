import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Awaitable, Callable, Optional

from agent import analyst_agent, planner_agent
from agent import act_agent
from gitlab_mcp.client import GitLabClient
from graph.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

STAGE_DEFS = [
    {"id": "observe_repo", "label": "Observe Repo", "description": "Read GitLab project state: members, issues, MRs, pipelines, CODEOWNERS"},
    {"id": "map_modules", "label": "Map Modules", "description": "Map per-directory upstream authorship — who knows what part of the codebase"},
    {"id": "observe_graph", "label": "Observe Graph", "description": "Read continuity graph snapshot"},
    {"id": "analyze", "label": "Analyze", "description": "Assess continuity and delivery risks"},
    {"id": "plan", "label": "Plan", "description": "Build recommended remediation actions"},
    {"id": "act", "label": "Execute", "description": "Perform GitLab operations from plan"},
    {"id": "learn", "label": "Persist", "description": "Write back knowledge graph updates"},
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

        # Scratch data passed between stages (not stored in stage.output)
        self._repo: dict = {}
        self._module_contributors: dict = {}
        self._graph_data: dict = {}
        self._risks: dict = {}
        self._plan: dict = {}

    @property
    def current_run(self) -> Optional[PipelineRun]:
        return self._current_run

    @property
    def is_running(self) -> bool:
        return self._running

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
        run = PipelineRun(
            run_id=str(uuid.uuid4()),
            started_at=time.time(),
            stages=[StageState(**d) for d in STAGE_DEFS],
        )
        self._current_run = run
        self._broadcast()

        try:
            if not await self._execute("observe_repo", self._observe_repo):
                run.status = "failed"
                return

            await self._execute("map_modules", self._observe_modules)

            if not await self._execute("observe_graph", self._observe_graph):
                run.status = "failed"
                return

            if not await self._execute("analyze", self._analyze):
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
        except Exception:
            run.status = "failed"
            logger.exception("[pipeline] Unexpected pipeline error")
        finally:
            self._running = False
            self._run_history.append(run)
            self._broadcast()

    async def _execute(self, stage_id: str, coro: Callable[[], Awaitable[dict]]) -> bool:
        stage = next(s for s in self._current_run.stages if s.id == stage_id)
        stage.status = "running"
        stage.started_at = time.time()
        self._broadcast()
        try:
            logger.info("[pipeline] %-12s started", stage.label)
            stage.output = await coro()
            stage.status = "success"
            stage.duration_ms = int((time.time() - stage.started_at) * 1000)
            logger.info("[pipeline] %-12s done in %dms", stage.label, stage.duration_ms)
            return True
        except Exception as exc:
            stage.status = "failed"
            stage.error = str(exc)
            stage.duration_ms = int((time.time() - stage.started_at) * 1000)
            logger.error("[pipeline] %-12s failed: %s", stage.label, exc)
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
        return {
            "members": len(self._repo.get("members", [])),
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

    async def _observe_graph(self) -> dict:
        self._graph_data = await self._graph.snapshot()
        return {
            "developers_tracked": len(self._graph_data.get("developers", [])),
            "upstream_authors_tracked": len(self._graph_data.get("upstream_authors", [])),
            "high_risk_modules": len(self._graph_data.get("high_risk_modules", [])),
            "open_tasks_tracked": len(self._graph_data.get("open_tasks", [])),
        }

    async def _analyze(self) -> dict:
        self._risks = await asyncio.to_thread(
            analyst_agent.analyze, self._repo, self._graph_data
        )
        return {
            "overall_health": self._risks.get("overall_health"),
            "summary": self._risks.get("summary"),
            "risk_count": len(self._risks.get("risk_assessments", [])),
            "risk_assessments": self._risks.get("risk_assessments", []),
        }

    async def _plan_stage(self) -> dict:
        self._plan = await asyncio.to_thread(
            planner_agent.plan, self._risks, self._repo, self._graph_data
        )
        return {
            "actions_planned": len(self._plan.get("actions", [])),
            "graph_updates_planned": len(self._plan.get("graph_updates", [])),
            "actions": self._plan.get("actions", []),
        }

    async def _act(self) -> dict:
        # act_agent.act is a native coroutine — uses MCP subprocess + async Gemini
        return await act_agent.act(self._risks, self._repo)

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
                    username = email.split("@", 1)[0] if email else (name.replace(" ", "_")[:64] or "unknown")

                dev = DeveloperNode(
                    gitlab_id=gitlab_id,
                    username=username,
                    name=(name or email or username),
                    active=not is_external,
                    external=is_external,
                )
                try:
                    await self._graph.upsert_developer(dev)
                except Exception:
                    pass

                edge = ContributionEdge(
                    developer_username=username,
                    module_path="repository",
                    commit_count=1,
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
                        username = email.split("@", 1)[0] if email else (name.replace(" ", "_")[:64] or "unknown")

                    dev = DeveloperNode(
                        gitlab_id=gitlab_id,
                        username=username,
                        name=(name or email or username),
                        active=not is_external,
                        external=is_external,
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

        # Recompute risk scores for all modules now that contributions are seeded
        rescored = await self._rescore_modules()
        logger.info("[pipeline] Rescored %d module(s)", rescored)

        return {"updated": count, "total": total, "modules_rescored": rescored}

    async def _rescore_modules(self) -> int:
        """
        Recompute continuity_risk_score for every tracked module after contributions are seeded.

        Bus factor uses only active internal committers (commit_count > 0, external=False).
        CODEOWNERS-only entries (commit_count=0) are excluded from bus factor — declared
        ownership without commits is not the same as held knowledge.

        An external-concentration penalty is applied when the majority of code was
        written by upstream/fork authors — this is "dark knowledge" risk that the
        standard formula cannot see.
        """
        from graph.models import ModuleNode
        from risk.forecasting import compute_bus_factor, compute_continuity_risk

        try:
            all_modules = await self._graph.modules.find({}, {"_id": 0}).to_list(None)
        except Exception as exc:
            logger.error("[pipeline] Rescore: failed to fetch modules: %s", exc)
            return 0

        updated = 0
        module_fields = set(ModuleNode.model_fields.keys())

        for module in all_modules:
            path = module["path"]
            try:
                all_contribs = await self._graph.get_module_contributors(path)

                # Split by type
                internal_committers = [
                    c for c in all_contribs
                    if not c.get("external", False) and c.get("commit_count", 0) > 0
                ]
                external_committers = [
                    c for c in all_contribs if c.get("external", False)
                ]

                # Base score uses only internal committers for bus factor
                base_score = compute_continuity_risk(internal_committers, module)

                # External concentration penalty — dark knowledge risk
                total_committers = len(internal_committers) + len(external_committers)
                ext_ratio = len(external_committers) / total_committers if total_committers > 0 else 0.0
                ext_penalty = round(ext_ratio * 0.3, 4) if ext_ratio > 0.5 else 0.0

                # No internal committers at all = additional structural risk
                no_internal_penalty = 0.25 if not internal_committers else 0.0

                final_score = round(min(1.0, base_score + ext_penalty + no_internal_penalty), 4)
                bus_factor = compute_bus_factor(internal_committers)

                module_data = {k: v for k, v in module.items() if k in module_fields}
                module_data["continuity_risk_score"] = final_score
                module_data["bus_factor"] = bus_factor

                await self._graph.upsert_module(ModuleNode(**module_data))
                updated += 1
                logger.debug(
                    "[rescore] %s: score=%.2f bus=%d internal=%d external=%d",
                    path, final_score, bus_factor, len(internal_committers), len(external_committers),
                )
            except Exception as exc:
                logger.error("[pipeline] Rescore failed for module %s: %s", path, exc)

        return updated

    async def _summary(self) -> dict:
        stages = self._current_run.stages if self._current_run else []
        succeeded = sum(1 for s in stages if s.status == "success")
        failed = sum(1 for s in stages if s.status == "failed")
        skipped = sum(1 for s in stages if s.status == "skipped")
        total_ms = sum(s.duration_ms or 0 for s in stages if s.duration_ms is not None)
        return {
            "stages_total": len(stages),
            "stages_succeeded": succeeded,
            "stages_failed": failed,
            "stages_skipped": skipped,
            "actions_executed": len((self._plan or {}).get("actions", [])),
            "graph_updates_planned": len((self._plan or {}).get("graph_updates", [])),
            "total_duration_ms": total_ms,
        }
