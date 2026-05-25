"""
Integration tests - requires a live MongoDB connection (.env must be configured).
Uses an isolated 'mycelium_test' database - safe to run, will not touch production data.

Run with: pytest tests/test_integration.py -v
"""
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from graph.knowledge_graph import KnowledgeGraph
from graph.models import ContributionEdge, DeveloperNode, ModuleNode
from config.settings import settings


# ---------------------------------------------------------------------------
# Isolated test graph - same logic as production, different DB
# ---------------------------------------------------------------------------

class _TestGraph(KnowledgeGraph):
    def __init__(self):
        self._client = AsyncIOMotorClient(settings.mongodb_uri)
        db = self._client["mycelium_test"]
        self.developers = db["developers"]
        self.modules = db["modules"]
        self.tasks = db["tasks"]
        self.contributions = db["contributions"]
        self.actions = db["actions"]
        self.findings = db["findings"]


@pytest.fixture
async def graph():
    g = _TestGraph()
    await g.developers.drop()
    await g.modules.drop()
    await g.tasks.drop()
    await g.contributions.drop()
    await g.actions.drop()
    await g.findings.drop()
    await g.setup_indexes()
    yield g
    g.close()


# ---------------------------------------------------------------------------
# Developer separation: internal vs external
# ---------------------------------------------------------------------------

class TestDeveloperSeparation:
    async def test_internal_dev_appears_in_active_list(self, graph):
        await graph.upsert_developer(
            DeveloperNode(username="alice", name="Alice Adams", active=True, external=False)
        )
        devs = await graph.list_developers(active_only=True)
        assert len(devs) == 1
        assert devs[0]["username"] == "alice"

    async def test_external_dev_excluded_from_active_list(self, graph):
        await graph.upsert_developer(
            DeveloperNode(username="upstream-bob", name="Bob", active=False, external=True)
        )
        devs = await graph.list_developers(active_only=True)
        assert len(devs) == 0

    async def test_external_dev_appears_in_external_list(self, graph):
        await graph.upsert_developer(
            DeveloperNode(username="upstream-bob", name="Bob", active=False, external=True)
        )
        external = await graph.list_upstream_authors()
        assert len(external) == 1
        assert external[0]["username"] == "upstream-bob"

    async def test_mixed_devs_separated_correctly(self, graph):
        await graph.upsert_developer(
            DeveloperNode(username="alice", name="Alice", active=True, external=False)
        )
        await graph.upsert_developer(
            DeveloperNode(username="upstream-carol", name="Carol", active=False, external=True)
        )
        await graph.upsert_developer(
            DeveloperNode(username="upstream-dave", name="Dave", active=False, external=True)
        )

        active = await graph.list_developers(active_only=True)
        external = await graph.list_upstream_authors()

        assert len(active) == 1
        assert active[0]["username"] == "alice"
        assert len(external) == 2
        assert {e["username"] for e in external} == {"upstream-carol", "upstream-dave"}

    async def test_upsert_developer_idempotent(self, graph):
        dev = DeveloperNode(username="alice", name="Alice", external=False)
        await graph.upsert_developer(dev)
        await graph.upsert_developer(dev)
        devs = await graph.list_developers()
        assert len(devs) == 1


# ---------------------------------------------------------------------------
# Snapshot structure
# ---------------------------------------------------------------------------

class TestSnapshot:
    async def test_snapshot_has_expected_keys(self, graph):
        snap = await graph.snapshot()
        assert "upstream_authors" in snap
        assert "developers" in snap
        assert "concentrated_modules" in snap
        assert "open_tasks" in snap
        assert "recent_findings" in snap

    async def test_snapshot_upstream_authors_populated(self, graph):
        await graph.upsert_developer(
            DeveloperNode(username="upstream-eve", name="Eve", active=False, external=True)
        )
        snap = await graph.snapshot()
        assert len(snap["upstream_authors"]) == 1
        assert snap["upstream_authors"][0]["username"] == "upstream-eve"

    async def test_snapshot_external_not_in_developers(self, graph):
        await graph.upsert_developer(
            DeveloperNode(username="alice", name="Alice", active=True, external=False)
        )
        await graph.upsert_developer(
            DeveloperNode(username="upstream-bob", name="Bob", active=False, external=True)
        )
        snap = await graph.snapshot()
        dev_usernames = {d["username"] for d in snap["developers"]}
        ext_usernames = {e["username"] for e in snap["upstream_authors"]}

        assert "alice" in dev_usernames
        assert "upstream-bob" not in dev_usernames
        assert "upstream-bob" in ext_usernames
        assert "alice" not in ext_usernames


# ---------------------------------------------------------------------------
# Contributions and expertise scores
# ---------------------------------------------------------------------------

class TestContributions:
    async def test_codeowners_contribution_has_full_score(self, graph):
        await graph.upsert_contribution(ContributionEdge(
            developer_username="declared-owner",
            module_path="src/auth",
            expertise_score=1.0,
            external=False,
            developer_identity="declared-owner",
        ))
        contributors = await graph.get_module_contributors("src/auth")
        assert len(contributors) == 1
        assert contributors[0]["expertise_score"] == 1.0

    async def test_mr_approver_has_partial_score(self, graph):
        await graph.upsert_contribution(ContributionEdge(
            developer_username="reviewer",
            module_path="feature-branch",
            expertise_score=0.6,
            external=False,
        ))
        contributors = await graph.get_module_contributors("feature-branch")
        assert contributors[0]["expertise_score"] == 0.6

    async def test_external_contribution_flagged(self, graph):
        await graph.upsert_contribution(ContributionEdge(
            developer_username="upstream-author",
            module_path="src/legacy",
            expertise_score=0.0,
            external=True,
            developer_identity="author@upstream.org",
        ))
        contributors = await graph.get_module_contributors("src/legacy")
        assert len(contributors) == 1
        assert contributors[0]["external"] is True

    async def test_contributors_sorted_by_expertise_desc(self, graph):
        for username, score in [("alice", 0.8), ("bob", 0.3), ("carol", 0.95)]:
            await graph.upsert_contribution(ContributionEdge(
                developer_username=username,
                module_path="src/core",
                expertise_score=score,
            ))
        contributors = await graph.get_module_contributors("src/core")
        scores = [c["expertise_score"] for c in contributors]
        assert scores == sorted(scores, reverse=True)

    async def test_upsert_contribution_overwrites_score(self, graph):
        edge = ContributionEdge(
            developer_username="alice", module_path="src/auth", expertise_score=0.3
        )
        await graph.upsert_contribution(edge)
        edge.expertise_score = 0.9
        await graph.upsert_contribution(edge)
        contributors = await graph.get_module_contributors("src/auth")
        assert len(contributors) == 1
        assert contributors[0]["expertise_score"] == 0.9


# ---------------------------------------------------------------------------
# Module concentration (measurement only - no scoring)
# ---------------------------------------------------------------------------

class TestModuleConcentration:
    async def test_concentrated_module_appears_in_list(self, graph):
        await graph.upsert_module(ModuleNode(
            path="src/legacy",
            bus_factor=1,
            owners=[],
        ))
        concentrated = await graph.list_concentrated_modules(max_bus_factor=1)
        assert any(m["path"] == "src/legacy" for m in concentrated)

    async def test_distributed_module_excluded_from_concentrated_list(self, graph):
        await graph.upsert_module(ModuleNode(
            path="src/stable",
            bus_factor=4,
            owners=["alice", "bob"],
        ))
        concentrated = await graph.list_concentrated_modules(max_bus_factor=1)
        assert not any(m["path"] == "src/stable" for m in concentrated)

    async def test_codeowners_module_has_declared_owners(self, graph):
        await graph.upsert_module(ModuleNode(
            path="src/auth",
            owners=["alice", "bob"],
        ))
        module = await graph.get_module("src/auth")
        assert module is not None
        assert "alice" in module["owners"]
