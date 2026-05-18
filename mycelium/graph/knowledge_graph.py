from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import settings
from graph.models import DeveloperNode, ModuleNode, TaskNode, ContributionEdge, ActionRecord, Finding


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

    # --- Developers ---

    async def upsert_developer(self, dev: DeveloperNode):
        await self.developers.update_one(
            {"username": dev.username},
            {"$set": dev.model_dump()},
            upsert=True,
        )

    async def get_developer(self, username: str) -> dict | None:
        return await self.developers.find_one({"username": username}, {"_id": 0})

    async def list_developers(self, active_only: bool = True) -> list[dict]:
        query = {"active": True, "external": {"$ne": True}} if active_only else {}
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
        await self.modules.update_one(
            {"path": module.path},
            {"$set": module.model_dump()},
            upsert=True,
        )

    async def get_module(self, path: str) -> dict | None:
        return await self.modules.find_one({"path": path}, {"_id": 0})

    async def list_modules(self) -> list[dict]:
        return await self.modules.find({}, {"_id": 0}).to_list(None)

    async def list_concentrated_modules(self, max_bus_factor: int = 1) -> list[dict]:
        """Modules with low contributor concentration (a measurement, not a score).

        Returned as a structural observation only — the analyst decides what
        weight to give it in context. No severity attached.
        """
        return await self.modules.find(
            {"bus_factor": {"$lte": max_bus_factor}}, {"_id": 0}
        ).sort("bus_factor", 1).to_list(None)

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
        await self.contributions.update_one(
            {"developer_username": edge.developer_username, "module_path": edge.module_path},
            {"$set": edge.model_dump()},
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

    # --- Snapshot for agent context ---

    async def snapshot(self) -> dict:
        return {
            "developers": await self.list_developers(),
            "upstream_authors": await self.list_external_contributors(),
            "concentrated_modules": await self.list_concentrated_modules(),
            "open_tasks": await self.list_open_tasks(),
            "recent_findings": await self.list_findings(limit=50),
        }

    def close(self):
        self._client.close()
