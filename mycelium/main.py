import asyncio
import json
import logging
import threading
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from config.settings import settings  # initialises Vertex AI env vars on import
from agent.activity_bus import bus as activity_bus
from agent.pipeline import PipelineRunner
from graph.knowledge_graph import KnowledgeGraph
from graph.service import GraphService, is_real_module, is_real_user
from connectors.gitlab_client import GitLabClient

# ---------------------------------------------------------------------------
# In-memory log store
# ---------------------------------------------------------------------------
_log_lock = threading.Lock()
_LOG_HISTORY: deque = deque(maxlen=500)
_log_seq = 0

_IGNORED_LOGGERS = ("motor", "pymongo", "urllib3", "httpcore", "httpx",
                    "asyncio", "watchfiles", "sse_starlette", "google")


class _UILogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        # Reuse logging.Formatter time formatting helpers.
        self._formatter = logging.Formatter()

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(_IGNORED_LOGGERS):
            return
        global _log_seq
        entry = {
            "seq": _log_seq,
            "ts": self._formatter.formatTime(record, "%H:%M:%S"),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        with _log_lock:
            _LOG_HISTORY.append(entry)
            _log_seq += 1


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("agent").setLevel(logging.DEBUG)
# google.genai emits a one-time INFO note about Schema → JSONSchema migration.
# That migration is inside ADK internals (FunctionDeclaration building); we
# can't switch to parameters_json_schema ourselves. Silence INFO from the
# google namespace so we still see WARNINGs and ERRORs.
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger().addHandler(_UILogHandler())
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------
graph = KnowledgeGraph()
service = GraphService(graph)
gitlab = GitLabClient()
pipeline = PipelineRunner(gitlab, graph)


async def run_loop():
    if not settings.pipeline_loop_enabled:
        log.info(
            "Pipeline auto-loop is DISABLED (PIPELINE_LOOP_ENABLED=false). "
            "Use POST /pipeline/run to trigger a run manually."
        )
        return
    log.info("Mycelium pipeline loop started — interval %ds", settings.agent_loop_interval)
    while True:
        await pipeline.run()
        await asyncio.sleep(settings.agent_loop_interval)


@asynccontextmanager
async def lifespan(_app: FastAPI):  # pyright: ignore[reportUnusedParameter]
    activity_bus.set_loop(asyncio.get_event_loop())
    await graph.setup_indexes()
    loop_task = asyncio.create_task(run_loop())
    yield
    loop_task.cancel()
    graph.close()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Mycelium — Continuity Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/config")
async def config():
    """Return non-sensitive runtime configuration for the UI."""
    return {
        "google_cloud_project": settings.google_cloud_project,
        "google_cloud_location": settings.google_cloud_location,
        "gemini_model": settings.gemini_model,
        "gitlab_url": settings.gitlab_url,
        "gitlab_project_id": settings.gitlab_project_id,
        "mongodb_db": settings.mongodb_db,
        "pipeline_loop_enabled": settings.pipeline_loop_enabled,
        "agent_loop_interval_seconds": settings.agent_loop_interval,
        "demo_mode": settings.demo_mode,
    }


@app.get("/snapshot")
async def snapshot():
    return await graph.snapshot()


@app.get("/graph")
async def graph_full():
    """Full knowledge graph state including per-module contribution edges."""
    return await service.full_graph()


@app.delete("/graph/demo")
async def clear_demo_data():
    """Delete all demo-flagged entries from the knowledge graph.

    Requires DEMO_MODE=true. Returns 403 when demo mode is disabled.
    """
    if not settings.demo_mode:
        raise HTTPException(status_code=403, detail="Demo mode is disabled (set DEMO_MODE=true to enable)")
    return await graph.delete_demo_data()


@app.delete("/graph/bots")
async def purge_bot_entries():
    """Delete developer and contribution records whose username looks like a GitLab
    namespace path or bot sanitized form (contains '_' in a namespace-path pattern).

    Matches:
      - usernames that STILL contain '/' (pre-fix pipeline runs)
      - usernames whose original name was a namespace path and got '/' replaced by '_',
        detected by the presence of typical GitLab namespace slug patterns like
        'gitlab-org_' or 'gitlab-bot' prefixes, or the literal 'maintainers_' segment.
    """
    # Broad regex: "word/word" patterns that survived as "word_word" segments.
    # We target the specific known pattern rather than all underscored names.
    all_devs = await graph.developers.find({}, {"_id": 0, "username": 1}).to_list(None)
    bot_usernames = []
    for d in all_devs:
        u = d.get("username", "")
        if "/" in u:          # still has "/" (pre-fix pipeline runs)
            bot_usernames.append(u)
        elif any(seg in u.lower() for seg in [
            "maintainers", "gitlab-org", "gitlab_org", "noreply",
        ]):
            bot_usernames.append(u)

    if not bot_usernames:
        return {"purged_developers": 0, "purged_contributions": 0, "purged_history": 0}

    dev_res = await graph.developers.delete_many({"username": {"$in": bot_usernames}})
    contrib_res = await graph.contributions.delete_many({"developer_username": {"$in": bot_usernames}})
    hist_res = await graph.contribution_history.delete_many({"developer_username": {"$in": bot_usernames}})

    log.info("[purge_bots] removed %d devs, %d contributions, %d history records | usernames: %s",
             dev_res.deleted_count, contrib_res.deleted_count, hist_res.deleted_count, bot_usernames[:10])
    return {
        "purged_developers": dev_res.deleted_count,
        "purged_contributions": contrib_res.deleted_count,
        "purged_history": hist_res.deleted_count,
        "bot_usernames": bot_usernames,
    }


@app.get("/graph/demo")
async def has_demo_data():
    """Returns whether any demo-flagged data is present, plus whether demo mode is enabled."""
    return {
        "has_demo": await graph.has_demo_data(),
        "demo_mode": settings.demo_mode,
    }


@app.get("/project")
async def project_info():
    """Real GitLab project metadata — name, namespace, URL, branch, stars, forks."""
    return await asyncio.to_thread(gitlab.get_project_info)


@app.get("/developers")
async def all_developers():
    """All developers (internal + external), bots excluded."""
    devs = await service.all_developers()
    return {"developers": devs}


@app.get("/developers/busfactor")
async def developer_busfactor(username: str):
    """Per-developer contribution breakdown.

    For internal members: shows bus-factor threshold position per module.
    For upstream/external authors: shows their share of total module expertise
      (internal + external) — they are excluded from bus-factor by design.
    """
    from risk.forecasting import compute_bus_factor

    if not is_real_user(username):
        raise HTTPException(
            status_code=400,
            detail=f"'{username}' looks like a GitLab namespace path, not a developer username. "
                   "These are service accounts from upstream fork history and are not tracked individually.",
        )

    dev = await graph.get_developer(username)
    if dev is None:
        raise HTTPException(status_code=404, detail=f"Developer '{username}' not found in knowledge graph.")

    is_external = dev.get("external", False)
    contributions = await service.developer_modules(username)
    result = []

    for contrib in contributions:
        path = contrib["module_path"]
        dev_score = contrib["expertise_score"]

        all_contribs = await service.module_contributors(path)
        internal = [c for c in all_contribs if not c.get("external", False)]
        external_contribs = [c for c in all_contribs if c.get("external", False)]

        internal_total = sum(c["expertise_score"] for c in internal)  # used for bus-factor threshold only

        # Use raw commit counts for all percentage calculations.
        # expertise_score is normalized (top contributor per module = 1.0), so using it
        # directly for percentages produces misleading "100%" when only one contributor
        # is recorded — even though the proportions are mathematically the same.
        all_commit_total    = sum(c.get("commit_count", 0) for c in all_contribs)
        internal_commit_total = sum(c.get("commit_count", 0) for c in internal)
        dev_commit_count    = contrib.get("commit_count", 0)

        if is_external:
            # Upstream author view.
            # Breakdown shows ALL contributors (internal + external) so the user can see
            # who else has committed, not just the empty internal-only list.
            # Each entry carries external=True/False so the frontend can colour-code them.
            # Mark which internal contributors are inside the 80% bus-factor threshold
            # so the frontend can show ★ markers even when viewing an upstream author's drawer.
            internal_sorted_for_threshold = sorted(internal, key=lambda c: c["expertise_score"], reverse=True)
            bus_threshold_set: set = set()
            cum_exp_running = 0.0
            for _c in internal_sorted_for_threshold:
                bus_threshold_set.add(_c["developer_username"])
                cum_exp_running += _c["expertise_score"]
                if internal_total > 0 and (cum_exp_running / internal_total * 100) >= 80.0:
                    break  # this person is the last one inside the threshold

            all_sorted = sorted(all_contribs, key=lambda c: c.get("commit_count", 0), reverse=True)
            breakdown = []
            for c in all_sorted:
                c_commits = c.get("commit_count", 0)
                share = (c_commits / all_commit_total * 100) if all_commit_total > 0 else 0.0
                is_ext = c.get("external", True)
                breakdown.append({
                    "username": c["developer_username"],
                    "expertise_score": c["expertise_score"],
                    "share_pct": round(share, 2),
                    "cumulative_pct": 0.0,
                    "in_bus_factor": (c["developer_username"] in bus_threshold_set) if not is_ext else False,
                    "commit_count": c_commits,
                    "external": is_ext,
                })

            bus_factor = compute_bus_factor(internal)
            # dev_share: this upstream author's fraction of ALL recorded commits to this module
            dev_share = (dev_commit_count / all_commit_total * 100) if all_commit_total > 0 else 0.0
            result.append({
                "module_path": path,
                "bus_factor": bus_factor,
                "dev_expertise_score": round(dev_score, 4),
                "dev_share_pct": round(dev_share, 2),
                "dev_commit_count": dev_commit_count,
                "total_commit_count": all_commit_total,
                "dev_in_bus_factor": False,
                "total_internal_contributors": len(internal),
                "total_external_contributors": len(external_contribs),
                "breakdown": breakdown,
            })

        else:
            # Internal developer view.
            # Breakdown shows internal contributors only; bus-factor threshold is
            # computed from expertise_score (by design) but displayed as commit %.
            internal_sorted = sorted(internal, key=lambda c: c["expertise_score"], reverse=True)
            cumulative_commits = 0
            threshold_reached = False
            breakdown = []
            for c in internal_sorted:
                c_commits = c.get("commit_count", 0)
                share_pct = (c_commits / internal_commit_total * 100) if internal_commit_total > 0 else 0.0
                cumulative_commits += c_commits
                cum_pct = (cumulative_commits / internal_commit_total * 100) if internal_commit_total > 0 else 0.0
                # Bus-factor threshold is still determined by expertise_score ordering
                # (top expertise contributors cumulatively covering ≥80% of internal expertise).
                score = c["expertise_score"]
                cum_expertise = sum(
                    x["expertise_score"] for x in internal_sorted[:internal_sorted.index(c) + 1]
                )
                in_bus = not threshold_reached
                if (cum_expertise / internal_total * 100) >= 80.0 if internal_total > 0 else True:
                    threshold_reached = True
                breakdown.append({
                    "username": c["developer_username"],
                    "expertise_score": score,
                    "share_pct": round(share_pct, 2),
                    "cumulative_pct": round(cum_pct, 2),
                    "in_bus_factor": in_bus,
                    "commit_count": c_commits,
                    "external": False,
                })

            bus_factor = compute_bus_factor(internal)
            dev_in_bus = any(
                b["username"] == username and b["in_bus_factor"] for b in breakdown
            )
            # dev_share: this developer's fraction of internal-only recorded commits
            dev_share = (dev_commit_count / internal_commit_total * 100) if internal_commit_total > 0 else 0.0
            result.append({
                "module_path": path,
                "bus_factor": bus_factor,
                "dev_expertise_score": round(dev_score, 4),
                "dev_share_pct": round(dev_share, 2),
                "dev_commit_count": dev_commit_count,
                "total_commit_count": internal_commit_total,
                "dev_in_bus_factor": dev_in_bus,
                "total_internal_contributors": len(internal),
                "total_external_contributors": len(external_contribs),
                "breakdown": breakdown,
            })

    # Internal: critical (in threshold) first, then by share desc.
    # External: largest share first (shows the biggest dark-knowledge areas first).
    if is_external:
        result.sort(key=lambda m: -m["dev_share_pct"])
    else:
        result.sort(key=lambda m: (0 if m["dev_in_bus_factor"] else 1, -m["dev_share_pct"]))

    return {
        "username": username,
        "name": dev.get("name") or dev.get("developer_identity") or username,
        "external": is_external,
        "demo": dev.get("demo", False),
        "modules": result,
    }


@app.get("/pipeline/{run_id}/events")
async def get_run_events(run_id: str):
    """Stored activity events for a completed run (used by replay)."""
    events = await graph.list_activity_events(run_id)
    return {"run_id": run_id, "events": events}


@app.post("/onboard/{username}")
async def trigger_onboard(username: str):
    """Directly generate an onboarding pack for a developer (bypasses full pipeline)."""
    from connectors.mcp_server import generate_onboarding_pack
    result = await generate_onboarding_pack(username)
    return result


@app.post("/offboard/{username}")
async def trigger_offboard(username: str):
    """Directly generate an offboarding artifact for a developer."""
    from connectors.mcp_server import generate_offboarding_artifact
    result = await generate_offboarding_artifact(username)
    return result


@app.post("/demo/seed/{scenario}")
async def seed_demo(scenario: str):
    """Seed demo data for a scenario: team | new_joiner | fading | sole_owner.

    Requires DEMO_MODE=true. Returns 403 when demo mode is disabled.
    """
    if not settings.demo_mode:
        raise HTTPException(status_code=403, detail="Demo mode is disabled (set DEMO_MODE=true to enable)")
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scripts.seed_scenarios import (
        scenario_full_team,
        scenario_new_joiner,
        scenario_fading_contributor,
        scenario_sole_owner,
        clear_all,
    )
    handlers = {
        "team":       scenario_full_team,
        "all":        scenario_full_team,
        "new_joiner": scenario_new_joiner,
        "fading":     scenario_fading_contributor,
        "sole_owner": scenario_sole_owner,
        "clear":      clear_all,
    }
    fn = handlers.get(scenario)
    if fn is None:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario}. Valid: {list(handlers)}")
    await fn()
    return {"seeded": scenario}


class ForkDateBody(BaseModel):
    date: str | None = None


@app.get("/settings/fork-date")
async def get_fork_date():
    """Effective fork/repo-start date: MongoDB override if set, else GitLab project created_at."""
    override = await graph.get_fork_date_override()
    project_created = None
    try:
        proj = await asyncio.to_thread(gitlab.get_project_info)
        project_created = proj.get("created_at")
    except Exception:
        pass
    return {
        "override": override,
        "project_created_at": project_created,
        "effective": override or project_created,
    }


@app.post("/settings/fork-date")
async def set_fork_date(body: ForkDateBody):
    """Set or clear the fork date override stored in MongoDB."""
    await graph.set_fork_date_override(body.date)
    return {"set": body.date}


@app.get("/graph/contribution-history")
async def contribution_history(module_path: str | None = None, developer_username: str | None = None):
    """Monthly commit counts per (developer, module) for the repo history timeline."""
    return await graph.get_contribution_history(module_path=module_path, developer_username=developer_username)


@app.get("/actions")
async def list_actions(limit: int = 200, run_id: str | None = None):
    """Agent action log — what the act agent has done across all pipeline runs."""
    if run_id:
        actions = await graph.actions.find({"run_id": run_id}, {"_id": 0}).sort("executed_at", -1).to_list(limit)
        return actions
    return await graph.list_actions(limit=limit)


@app.get("/findings")
async def list_findings(limit: int = 200, run_id: str | None = None):
    """Continuity findings — qualitative analyst output, no scores."""
    return await graph.list_findings(limit=limit, run_id=run_id)


# ---------------------------------------------------------------------------
# Pipeline endpoints
# ---------------------------------------------------------------------------

@app.get("/pipeline/history")
async def pipeline_history(limit: int = 50):
    try:
        runs = await graph.list_runs(limit=limit)
        if runs:
            return {"runs": runs}
    except Exception as exc:
        log.warning("MongoDB pipeline history unavailable (%s) — using in-memory", exc)
    return {"runs": [r.to_dict() for r in pipeline.run_history]}


@app.get("/pipeline/current")
async def pipeline_current():
    run = pipeline.current_run
    if run:
        return {"run": run.to_dict()}
    try:
        latest = await graph.get_latest_run()
        if latest:
            return {"run": latest}
    except Exception:
        pass
    return {"run": None}


@app.post("/pipeline/run")
async def pipeline_run():
    if pipeline.is_running:
        raise HTTPException(status_code=409, detail="Pipeline already running")
    asyncio.create_task(pipeline.run())
    return {"status": "started"}


@app.post("/pipeline/stop")
async def pipeline_stop():
    if not pipeline.is_running:
        raise HTTPException(status_code=409, detail="Pipeline is not running")
    pipeline.request_cancel()
    return {"status": "stop_requested"}


@app.get("/pipeline/stream")
async def pipeline_stream():
    queue = pipeline.subscribe()

    async def generator():
        # Seed with current in-progress run, or last completed run from MongoDB
        run = pipeline.current_run
        if run:
            yield {"data": json.dumps(run.to_dict())}
        else:
            try:
                latest = await graph.get_latest_run()
                if latest:
                    yield {"data": json.dumps(latest)}
            except Exception:
                pass
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {"data": json.dumps(data)}
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            pipeline.unsubscribe(queue)

    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# Activity stream endpoint — structured agent event feed for the UI
# ---------------------------------------------------------------------------

@app.get("/pipeline/activity")
async def pipeline_activity():
    """Return the buffered activity events for the most recent run."""
    return {"events": activity_bus.history()}


@app.get("/pipeline/activity/stream")
async def pipeline_activity_stream():
    """SSE stream of structured agent activity events.

    On connect, replays the current run's buffer so the client catches up,
    then streams new events in real-time as the pipeline and agents run.
    """
    queue = activity_bus.subscribe()

    async def generator():
        for event in activity_bus.history():
            yield {"data": json.dumps(event)}
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {"data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            activity_bus.unsubscribe(queue)

    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# Log stream endpoint
# ---------------------------------------------------------------------------

@app.get("/logs/stream")
async def stream_logs():
    async def generator():
        with _log_lock:
            history = list(_LOG_HISTORY)
        for entry in history:
            yield {"data": json.dumps(entry)}

        last_seq = history[-1]["seq"] if history else -1
        while True:
            await asyncio.sleep(0.3)
            with _log_lock:
                new = [e for e in _LOG_HISTORY if e["seq"] > last_seq]
            for entry in new:
                yield {"data": json.dumps(entry)}
            if new:
                last_seq = new[-1]["seq"]
            else:
                yield {"comment": "keepalive"}

    return EventSourceResponse(generator())
