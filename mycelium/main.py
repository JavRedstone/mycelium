import asyncio
import json
import logging
import threading
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from config.settings import settings
from agent.pipeline import PipelineRunner
from graph.knowledge_graph import KnowledgeGraph
from gitlab_mcp.client import GitLabClient

# ---------------------------------------------------------------------------
# In-memory log store
# ---------------------------------------------------------------------------
_log_lock = threading.Lock()
_LOG_HISTORY: deque = deque(maxlen=500)
_log_seq = 0

_IGNORED_LOGGERS = ("motor", "pymongo", "urllib3", "httpcore", "httpx",
                    "asyncio", "watchfiles", "sse_starlette")


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
logging.getLogger().addHandler(_UILogHandler())
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------
graph = KnowledgeGraph()
gitlab = GitLabClient()
pipeline = PipelineRunner(gitlab, graph)


async def run_loop():
    log.info("Mycelium pipeline loop started — interval %ds", settings.agent_loop_interval)
    while True:
        await pipeline.run()
        await asyncio.sleep(settings.agent_loop_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
        "high_risk_modules": snap["high_risk_modules"],
    }


# ---------------------------------------------------------------------------
# Pipeline endpoints
# ---------------------------------------------------------------------------

@app.get("/pipeline/history")
async def pipeline_history():
    return {"runs": [r.to_dict() for r in pipeline.run_history]}


@app.get("/pipeline/current")
async def pipeline_current():
    run = pipeline.current_run
    if not run:
        return {"run": None}
    return {"run": run.to_dict()}


@app.post("/pipeline/run")
async def pipeline_run():
    if pipeline.is_running:
        raise HTTPException(status_code=409, detail="Pipeline already running")
    asyncio.create_task(pipeline.run())
    return {"status": "started"}


@app.get("/pipeline/stream")
async def pipeline_stream():
    queue = pipeline.subscribe()

    async def generator():
        # Send current state immediately on connect
        run = pipeline.current_run
        if run:
            yield {"data": json.dumps(run.to_dict())}
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
