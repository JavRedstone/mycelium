from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import settings
from graph.models import DeveloperNode, ModuleNode, TaskNode, ContributionEdge, ActionRecord, Finding, ContributionHistory


class KnowledgeGraph:
    def __init__(self):
        self._client = AsyncIOMotorClient(settings.mongodb_uri)
        db = self._client[settings.mongodb_db]
        self.developers = db["developers"]
        self.modules = db["modules"]
        self.tasks = db["tasks"]
        self.contributions = db["contributions"]
        self.actions = db["actions"]
        self.findings = db["findings"]
        self.pipeline_runs = db["pipeline_runs"]
        self.activity_events = db["activity_events"]
        self.settings = db["settings"]
        self.contribution_history = db["contribution_history"]

    async def setup_indexes(self):
        await self.developers.create_index("username", unique=True)
        await self.modules.create_index("path", unique=True)
        await self.tasks.create_index([("gitlab_id", 1), ("kind", 1)], unique=True)
        await self.contributions.create_index(
            [("developer_username", 1), ("module_path", 1)], unique=True
        )
        await self.actions.create_index([("executed_at", -1)])
        await self.findings.create_index([("created_at", -1)])
        await self.findings.create_index([("run_id", 1)])
        await self.pipeline_runs.create_index([("run_id", 1)], unique=True)
        await self.pipeline_runs.create_index([("started_at", -1)])
        await self.activity_events.create_index([("run_id", 1)])
        await self.activity_events.create_index([("seq", 1)])
        await self.contribution_history.create_index(
            [("developer_username", 1), ("module_path", 1), ("year_month", 1)], unique=True
        )

    # --- Developers ---

    async def upsert_developer(self, dev: DeveloperNode):
        doc = dev.model_dump()
        doc.pop("demo", None)        # never overwrite demo=True set by the seed script
        # first_seen / last_seen use $min/$max so runs never overwrite a better value
        # with None, and incremental runs keep the historical extremes.
        doc.pop("first_seen", None)
        doc.pop("last_seen", None)

        update: dict = {"$set": doc, "$setOnInsert": {"demo": False}}
        if dev.first_seen is not None:
            update["$min"] = {"first_seen": dev.first_seen}
        if dev.last_seen is not None:
            update["$max"] = {"last_seen": dev.last_seen}

        await self.developers.update_one(
            {"username": dev.username},
            update,
            upsert=True,
        )

    async def get_developer(self, username: str) -> dict | None:
        return await self.developers.find_one({"username": username}, {"_id": 0})

    async def list_developers(self, active_only: bool = True, exclude_demo: bool = True) -> list[dict]:
        query: dict = {}
        if active_only:
            query = {"active": True, "external": {"$ne": True}}
        if exclude_demo:
            query["demo"] = {"$ne": True}
        return await self.developers.find(query, {"_id": 0}).to_list(None)

    async def list_external_contributors(self) -> list[dict]:
        return await self.developers.find(
            {"external": True}, {"_id": 0}
        ).to_list(None)

    async def list_upstream_authors(self) -> list[dict]:
        """Alias for list_external_contributors — upstream/fork authors not in current project members."""
        return await self.list_external_contributors()

    # --- Modules ---

    async def upsert_module(self, module: ModuleNode):
        doc = module.model_dump()
        doc.pop("demo", None)  # never overwrite demo=True set by the seed script
        await self.modules.update_one(
            {"path": module.path},
            {"$set": doc, "$setOnInsert": {"demo": False}},
            upsert=True,
        )

    async def get_module(self, path: str) -> dict | None:
        return await self.modules.find_one({"path": path}, {"_id": 0})

    async def list_modules(self) -> list[dict]:
        return await self.modules.find({}, {"_id": 0}).to_list(None)

    async def list_concentrated_modules(self, max_bus_factor: int = 1, exclude_demo: bool = True) -> list[dict]:
        """Modules with low contributor concentration (a measurement, not a score).

        Returned as a structural observation only — the analyst decides what
        weight to give it in context. No severity attached.
        """
        query: dict = {"bus_factor": {"$lte": max_bus_factor}}
        if exclude_demo:
            query["demo"] = {"$ne": True}
        return await self.modules.find(query, {"_id": 0}).sort("bus_factor", 1).to_list(None)

    # --- Tasks ---

    async def upsert_task(self, task: TaskNode):
        await self.tasks.update_one(
            {"gitlab_id": task.gitlab_id, "kind": task.kind},
            {"$set": task.model_dump()},
            upsert=True,
        )

    async def list_open_tasks(self, assignee: str | None = None) -> list[dict]:
        query: dict = {"status": "open"}
        if assignee:
            query["assignee"] = assignee
        return await self.tasks.find(query, {"_id": 0}).to_list(None)

    # --- Contributions ---

    async def upsert_contribution(self, edge: ContributionEdge):
        doc = edge.model_dump()
        doc.pop("demo", None)  # never overwrite demo=True set by the seed script
        await self.contributions.update_one(
            {"developer_username": edge.developer_username, "module_path": edge.module_path},
            {"$set": doc, "$setOnInsert": {"demo": False}},
            upsert=True,
        )

    async def get_module_contributors(self, module_path: str) -> list[dict]:
        return await self.contributions.find(
            {"module_path": module_path}, {"_id": 0}
        ).sort("expertise_score", -1).to_list(None)

    async def get_developer_modules(self, username: str) -> list[dict]:
        return await self.contributions.find(
            {"developer_username": username}, {"_id": 0}
        ).sort("expertise_score", -1).to_list(None)

    # --- Actions ---

    async def insert_action(self, action: ActionRecord) -> None:
        await self.actions.insert_one(action.model_dump())

    async def list_actions(self, limit: int = 200) -> list[dict]:
        return await self.actions.find(
            {}, {"_id": 0}
        ).sort("executed_at", -1).limit(limit).to_list(limit)

    # --- Findings (qualitative analyst output, replaces scalar risk scoring) ---

    async def insert_finding(self, finding: Finding) -> None:
        await self.findings.insert_one(finding.model_dump())

    async def list_findings(self, limit: int = 200, run_id: str | None = None) -> list[dict]:
        query: dict = {"run_id": run_id} if run_id else {}
        return await self.findings.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)

    # --- Pipeline run history ---

    async def save_run(self, run_dict: dict) -> None:
        await self.pipeline_runs.update_one(
            {"run_id": run_dict["run_id"]},
            {"$set": run_dict},
            upsert=True,
        )

    async def get_latest_run(self) -> dict | None:
        docs = await self.pipeline_runs.find(
            {}, {"_id": 0}
        ).sort("started_at", -1).limit(1).to_list(1)
        return docs[0] if docs else None

    async def list_runs(self, limit: int = 50) -> list[dict]:
        return await self.pipeline_runs.find(
            {}, {"_id": 0}
        ).sort("started_at", -1).limit(limit).to_list(limit)

    # --- Activity events (replay) ---

    async def save_activity_events(self, run_id: str, events: list[dict]) -> None:
        if not events:
            return
        docs = [{"run_id": run_id, "seq": i, **e} for i, e in enumerate(events)]
        await self.activity_events.insert_many(docs, ordered=False)

    async def list_activity_events(self, run_id: str) -> list[dict]:
        return await self.activity_events.find(
            {"run_id": run_id}, {"_id": 0}
        ).sort("seq", 1).to_list(None)

    # --- Snapshot for agent context ---

    async def snapshot(self) -> dict:
        """Graph snapshot for agent consumption.

        Demo-seeded entries are only included when DEMO_MODE=true is set in the
        environment AND demo data is actually present in the database. In production
        (DEMO_MODE unset or false) demo entries are always excluded.
        """
        from config.settings import settings
        demo_active = settings.demo_mode and await self.has_demo_data()
        return {
            "developers": await self.list_developers(exclude_demo=not demo_active),
            "upstream_authors": await self.list_external_contributors(),
            "concentrated_modules": await self.list_concentrated_modules(exclude_demo=not demo_active),
            "open_tasks": await self.list_open_tasks(),
            "recent_findings": await self.list_findings(limit=50),
            "demo_data_present": demo_active,
        }

    async def delete_demo_data(self) -> dict:
        """Delete all documents flagged demo=True across every collection."""
        filter_ = {"demo": True}
        devs  = await self.developers.delete_many(filter_)
        mods  = await self.modules.delete_many(filter_)
        contribs = await self.contributions.delete_many(filter_)
        return {
            "deleted_developers": devs.deleted_count,
            "deleted_modules": mods.deleted_count,
            "deleted_contributions": contribs.deleted_count,
        }

    async def has_demo_data(self) -> bool:
        return bool(await self.developers.find_one({"demo": True})) \
            or bool(await self.modules.find_one({"demo": True})) \
            or bool(await self.contributions.find_one({"demo": True}))

    # --- Settings ---

    async def get_fork_date_override(self) -> str | None:
        doc = await self.settings.find_one({"_id": "config"})
        return (doc or {}).get("fork_date_override")

    async def set_fork_date_override(self, date_iso: str | None) -> None:
        if date_iso is None:
            await self.settings.update_one(
                {"_id": "config"}, {"$unset": {"fork_date_override": ""}}, upsert=True
            )
        else:
            await self.settings.update_one(
                {"_id": "config"}, {"$set": {"fork_date_override": date_iso}}, upsert=True
            )

    # --- Contribution history (monthly timeline buckets) ---

    async def upsert_contribution_history(self, record: ContributionHistory) -> None:
        doc = record.model_dump()
        doc.pop("demo", None)
        await self.contribution_history.update_one(
            {
                "developer_username": record.developer_username,
                "module_path": record.module_path,
                "year_month": record.year_month,
            },
            {"$set": doc, "$setOnInsert": {"demo": False}},
            upsert=True,
        )

    async def get_contribution_history(
        self,
        module_path: str | None = None,
        developer_username: str | None = None,
    ) -> list[dict]:
        query: dict = {}
        if module_path:
            query["module_path"] = module_path
        if developer_username:
            query["developer_username"] = developer_username
        return await self.contribution_history.find(
            query, {"_id": 0}
        ).sort("year_month", 1).to_list(None)

    def close(self):
        self._client.close()
