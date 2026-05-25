"""graph/service.py - single, filtered access point for all graph read queries.

Every data-quality rule lives here:
  - Bot / namespace-path username exclusion
  - Synthetic "repository" module exclusion
  - Demo data toggling (DEMO_MODE setting + DB flag)

All FastAPI routes and agents should call GraphService, not KnowledgeGraph directly.
"""
from __future__ import annotations

from graph.knowledge_graph import KnowledgeGraph
from config.settings import settings

# ---------------------------------------------------------------------------
# Filter predicates - one definition, shared across the entire backend
# ---------------------------------------------------------------------------

_BOT_USERNAME_SEGMENTS = frozenset({"maintainers", "gitlab-org", "gitlab_org", "noreply"})


def is_real_module(path: str) -> bool:
    """True for genuine local top-level directory paths.

    Excludes:
      - ``"repository"`` - synthetic catch-all written by the pipeline to track
        whole-repo contributors with ``expertise_score = 0.0``.
      - Anything containing ``"/"`` - GitLab namespace paths that crept in from
        upstream fork history (e.g. ``"gitlab-org/maintainers/gitlab-pages"``).
    """
    return path != "repository" and "/" not in path


def is_real_user(username: str) -> bool:
    """True for real GitLab user slugs; False for bots and namespace paths.

    Rejects:
      - Names still containing ``"/"`` (pre-fix pipeline runs stored namespace
        paths literally instead of sanitising them).
      - Names whose slug contains known bot/service-account segments that survive
        the ``"/" → "_"`` sanitisation step in the pipeline.
    """
    if "/" in username:
        return False
    u = username.lower()
    return not any(seg in u for seg in _BOT_USERNAME_SEGMENTS)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class GraphService:
    """Filtered, consistent view of the knowledge graph.

    Every read method applies:
      • ``is_real_user``   - drops bots and namespace-path usernames
      • ``is_real_module`` - drops "repository" and namespace-style paths
      • demo exclusion     - excluded unless ``DEMO_MODE=true`` AND demo data exists

    The API layer should never do its own filtering on top of this.
    """

    def __init__(self, graph: KnowledgeGraph) -> None:
        self._g = graph

    # ── private helpers ────────────────────────────────────────────────────────

    async def _demo_active(self) -> bool:
        return settings.demo_mode and await self._g.has_demo_data()

    def _clean_contributors(self, contributors: list[dict]) -> list[dict]:
        return [c for c in contributors if is_real_user(c.get("developer_username", ""))]

    async def _module_with_clean_contributors(self, module: dict) -> dict:
        raw = await self._g.get_module_contributors(module["path"])
        return {**module, "contributors": self._clean_contributors(raw)}

    # ── graph snapshot ────────────────────────────────────────────────────────

    async def full_graph(self) -> dict:
        """Full graph state for the ``/graph`` endpoint.

        Returns modules (with filtered contributors), internal developers,
        upstream authors, concentrated modules, and recent findings.
        """
        demo = await self._demo_active()

        # Modules
        mod_q: dict = {} if demo else {"demo": {"$ne": True}}
        raw_modules = await self._g.modules.find(mod_q, {"_id": 0}).to_list(None)
        real_modules = [m for m in raw_modules if is_real_module(m.get("path", ""))]
        modules = [await self._module_with_clean_contributors(m) for m in real_modules]

        # Internal developers (active, non-external)
        devs = await self._g.list_developers(exclude_demo=not demo)
        devs = [d for d in devs if is_real_user(d.get("username", ""))]

        # Upstream / external authors
        upstream_q: dict = {"external": True}
        if not demo:
            upstream_q["demo"] = {"$ne": True}
        upstream = await self._g.developers.find(upstream_q, {"_id": 0}).to_list(None)
        upstream = [a for a in upstream if is_real_user(a.get("username", ""))]

        # Concentrated modules (bus_factor ≤ 1)
        conc_q: dict = {"bus_factor": {"$lte": 1}}
        if not demo:
            conc_q["demo"] = {"$ne": True}
        concentrated = await self._g.modules.find(conc_q, {"_id": 0}).to_list(None)
        concentrated = [m for m in concentrated if is_real_module(m.get("path", ""))]

        findings = await self._g.list_findings(limit=50)

        return {
            "developers": devs,
            "upstream_authors": upstream,
            "modules": modules,
            "concentrated_modules": concentrated,
            "recent_findings": findings,
            "demo_data_present": demo,
        }

    # ── contribution history ──────────────────────────────────────────────────

    async def contribution_history(
        self,
        module_path: str | None = None,
        developer_username: str | None = None,
    ) -> list[dict]:
        """Monthly commit-count buckets for the Repo History chart.

        Bots and synthetic module paths are excluded. Demo records are only
        included when demo mode is active and demo data is present.
        """
        demo = await self._demo_active()

        query: dict = {}
        if module_path:
            query["module_path"] = module_path
        if developer_username:
            query["developer_username"] = developer_username
        if not demo:
            query["demo"] = {"$ne": True}

        records = await self._g.contribution_history.find(
            query, {"_id": 0}
        ).sort("year_month", 1).to_list(None)

        return [
            r for r in records
            if is_real_user(r.get("developer_username", ""))
            and is_real_module(r.get("module_path", ""))
        ]

    # ── per-developer data ────────────────────────────────────────────────────

    async def module_contributors(self, module_path: str) -> list[dict]:
        """Contributors for a module, bots excluded."""
        raw = await self._g.get_module_contributors(module_path)
        return self._clean_contributors(raw)

    async def developer_modules(self, username: str) -> list[dict]:
        """Module contributions for a developer, synthetic paths excluded."""
        contribs = await self._g.get_developer_modules(username)
        return [c for c in contribs if is_real_module(c.get("module_path", ""))]

    # ── all developers (for /developers endpoint) ──────────────────────────────

    async def all_developers(self) -> list[dict]:
        """Every developer record (internal + external), bots excluded."""
        all_devs = await self._g.developers.find({}, {"_id": 0}).to_list(None)
        return [d for d in all_devs if is_real_user(d.get("username", ""))]
