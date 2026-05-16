from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import settings
from graph.models import DeveloperNode, ModuleNode, TaskNode, ContributionEdge


class KnowledgeGraph:
    def __init__(self):
        self._client = AsyncIOMotorClient(settings.mongodb_uri)
        db = self._client[settings.mongodb_db]
        self.developers = db["developers"]
        self.modules = db["modules"]
        self.tasks = db["tasks"]
        self.contributions = db["contributions"]

    async def setup_indexes(self):
        await self.developers.create_index("username", unique=True)
        await self.modules.create_index("path", unique=True)
        await self.tasks.create_index([("gitlab_id", 1), ("kind", 1)], unique=True)
        await self.contributions.create_index(
            [("developer_username", 1), ("module_path", 1)], unique=True
        )

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

    # --- Modules ---

    async def upsert_module(self, module: ModuleNode):
        await self.modules.update_one(
            {"path": module.path},
            {"$set": module.model_dump()},
            upsert=True,
        )

    async def get_module(self, path: str) -> dict | None:
        return await self.modules.find_one({"path": path}, {"_id": 0})

    async def list_high_risk_modules(self, threshold: float = 0.7) -> list[dict]:
        return await self.modules.find(
            {"continuity_risk_score": {"$gte": threshold}}, {"_id": 0}
        ).to_list(None)

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

    # --- Snapshot for agent context ---

    async def snapshot(self) -> dict:
        return {
            "developers": await self.list_developers(),
            "upstream_authors": await self.list_external_contributors(),
            "high_risk_modules": await self.list_high_risk_modules(),
            "open_tasks": await self.list_open_tasks(),
        }

    def close(self):
        self._client.close()
