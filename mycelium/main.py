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
async def lifespan(app: FastAPI):
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
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
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
    }


@app.get("/snapshot")
async def snapshot():
    return await graph.snapshot()


@app.get("/graph")
async def graph_full():
    """Full knowledge graph state including per-module contribution edges."""
    snap = await graph.snapshot()
    all_modules = await graph.modules.find({}, {"_id": 0}).to_list(None)
    modules_with_contribs = []
    for module in all_modules:
        contribs = await graph.get_module_contributors(module["path"])
        modules_with_contribs.append({**module, "contributors": contribs})
    return {
        "developers": snap["developers"],
        "upstream_authors": snap["upstream_authors"],
        "modules": modules_with_contribs,
        "concentrated_modules": snap.get("concentrated_modules", []),
        "recent_findings": snap.get("recent_findings", []),
    }


@app.delete("/graph/demo")
async def clear_demo_data():
    """Delete all demo-flagged entries from the knowledge graph."""
    return await graph.delete_demo_data()


@app.get("/graph/demo")
async def has_demo_data():
    """Returns whether any demo-flagged data is present."""
    return {"has_demo": await graph.has_demo_data()}


@app.get("/project")
async def project_info():
    """Real GitLab project metadata — name, namespace, URL, branch, stars, forks."""
    return await asyncio.to_thread(gitlab.get_project_info)


@app.get("/developers")
async def all_developers():
    """All developers including demo-flagged entries (used by the mock repo view)."""
    devs = await graph.developers.find({}, {"_id": 0}).to_list(None)
    return {"developers": devs}


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
    """Seed demo data for a scenario: team | new_joiner | fading | sole_owner."""
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
