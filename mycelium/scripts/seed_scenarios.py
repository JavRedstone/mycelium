"""
Seed synthetic developer/module data for pipeline demo and testing.

All seeded entries are flagged demo=True so they are clearly identifiable
in the UI and can be bulk-deleted via the API or the --clear flag.

Demo scenario (realistic team on a gitlab-pages fork):
  - alex.chen       Senior engineer, owns internal/ and shared/. Active.
  - priya.sharma    Senior, owns scripts/ exclusively. Inactive 6 months — RISK.
  - marco.torres    New joiner, 2 weeks in. No commits yet.
  - lisa.park       Mid-level, distributed contributions across test/ and shared/.

Concern types triggered:
  sole_contributor      scripts/ — priya is the only person who touched it, now inactive
  fading_contributor    priya — high expertise, last seen 6 months ago
  recent_joiner_exposure  marco — just joined, no commits, not paired with anyone
  knowledge_concentration  app/ — JavRedstone is sole internal committer

Usage (run from the mycelium/ directory):
    python -m scripts.seed_scenarios team        # full demo team + modules
    python -m scripts.seed_scenarios new_joiner  # marco only
    python -m scripts.seed_scenarios fading      # priya only
    python -m scripts.seed_scenarios sole_owner  # scripts/ sole-owner scenario
    python -m scripts.seed_scenarios all         # alias for team
    python -m scripts.seed_scenarios --clear     # delete all demo entries
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import settings

_CLIENT = None
_DB = None


def db():
    global _CLIENT, _DB
    if _DB is None:
        _CLIENT = AsyncIOMotorClient(settings.mongodb_uri)
        _DB = _CLIENT[settings.mongodb_db]
    return _DB


async def _upsert(collection: str, filter_: dict, doc: dict):
    await db()[collection].update_one(filter_, {"$set": doc}, upsert=True)


async def _delete_by_usernames(usernames: list[str]):
    if not usernames:
        return
    await db()["developers"].delete_many({"username": {"$in": usernames}, "demo": True})
    await db()["contributions"].delete_many({"developer_username": {"$in": usernames}, "demo": True})


async def _delete_by_modules(paths: list[str]):
    if not paths:
        return
    await db()["modules"].delete_many({"path": {"$in": paths}, "demo": True})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.utcnow()


async def _seed_developer(
    username: str,
    name: str,
    gitlab_id: int,
    expertise: dict[str, float],
    last_seen: datetime,
    active: bool = True,
):
    await _upsert("developers", {"username": username}, {
        "username": username,
        "name": name,
        "gitlab_id": gitlab_id,
        "active": active,
        "external": False,
        "expertise": expertise,
        "last_seen": last_seen,
        "updated_at": _now(),
        "demo": True,
    })


async def _seed_contribution(
    username: str,
    module_path: str,
    commit_count: int,
    lines_changed: int,
    expertise_score: float,
    last_contribution_at: datetime,
    external: bool = False,
):
    await _upsert(
        "contributions",
        {"developer_username": username, "module_path": module_path},
        {
            "developer_username": username,
            "module_path": module_path,
            "commit_count": commit_count,
            "lines_changed": lines_changed,
            "expertise_score": expertise_score,
            "last_contribution_at": last_contribution_at,
            "external": external,
            "updated_at": _now(),
            "demo": True,
        },
    )


async def _set_fork_date(date: datetime | None) -> None:
    """Write the demo fork date into the settings collection (read by /settings/fork-date)."""
    if date is None:
        await db()["settings"].update_one(
            {"_id": "config"}, {"$unset": {"fork_date_override": ""}}, upsert=True
        )
    else:
        await db()["settings"].update_one(
            {"_id": "config"}, {"$set": {"fork_date_override": date.isoformat()}}, upsert=True
        )


async def _seed_upstream_author(
    username: str,
    name: str,
    gitlab_id: int,
    last_seen: datetime,
):
    """Seed an external/upstream contributor (pre-fork author from the original repo)."""
    await _upsert("developers", {"username": username}, {
        "username": username,
        "name": name,
        "gitlab_id": gitlab_id,
        "active": False,
        "external": True,
        "expertise": {},
        "last_seen": last_seen,
        "updated_at": _now(),
        "demo": True,
    })


async def _seed_module(
    path: str,
    bus_factor: int,
    owners: list[str],
    language: str = "Go",
):
    await _upsert("modules", {"path": path}, {
        "path": path,
        "language": language,
        "bus_factor": bus_factor,
        "owners": owners,
        "last_commit_at": _now() - timedelta(days=3),
        "updated_at": _now(),
        "demo": True,
    })


# ---------------------------------------------------------------------------
# Full demo team scenario
# ---------------------------------------------------------------------------

async def scenario_full_team():
    """
    Seeds a realistic 4-person engineering team on the gitlab-pages fork.

    Module ownership matrix:
      internal/  bus=2  alex(0.82), javier-implied, lisa(0.31)
      scripts/   bus=1  priya(0.97) — SOLE HOLDER, now inactive!
      shared/    bus=3  alex(0.74), lisa(0.68), priya(0.41)
      test/      bus=3  lisa(0.71), alex(0.58), marco(0.04)
      app/       bus=1  alex(0.89) — high concentration

    Concern signals:
      - priya: sole scripts/ owner, 6mo inactive → fading_contributor + offboarding_artifact
      - marco: joined 2 weeks ago, 1 test/ commit → recent_joiner_exposure → onboarding_pack
      - scripts/: bus_factor=1, owner inactive → knowledge_concentration → create_issue
    """
    usernames = ["alex.chen", "priya.sharma", "marco.torres", "lisa.park"]
    upstream_usernames = ["tim.arch", "remi.pages", "sofia.mueller"]
    module_paths = ["internal", "scripts", "shared", "test", "app"]

    await _delete_by_usernames(usernames + upstream_usernames)
    await _delete_by_modules(module_paths)

    six_months_ago   = _now() - timedelta(days=183)
    two_weeks_ago    = _now() - timedelta(days=14)
    three_days_ago   = _now() - timedelta(days=3)
    yesterday        = _now() - timedelta(days=1)
    twelve_months    = _now() - timedelta(days=366)
    fourteen_months  = _now() - timedelta(days=427)
    sixteen_months   = _now() - timedelta(days=488)

    # ── Developers ──────────────────────────────────────────────────────────

    await _seed_developer(
        username="alex.chen",
        name="Alex Chen",
        gitlab_id=9011,
        expertise={"internal": 0.82, "app": 0.89, "shared": 0.74, "test": 0.58},
        last_seen=yesterday,
    )
    await _seed_developer(
        username="priya.sharma",
        name="Priya Sharma",
        gitlab_id=9012,
        expertise={"scripts": 0.97, "shared": 0.41, "internal": 0.29},
        last_seen=six_months_ago,  # ← the risk: gone dark
    )
    await _seed_developer(
        username="marco.torres",
        name="Marco Torres",
        gitlab_id=9013,
        expertise={},              # ← no established expertise yet
        last_seen=two_weeks_ago,   # ← just joined
    )
    await _seed_developer(
        username="lisa.park",
        name="Lisa Park",
        gitlab_id=9014,
        expertise={"test": 0.71, "shared": 0.68, "internal": 0.31},
        last_seen=three_days_ago,
    )

    # ── Contributions ────────────────────────────────────────────────────────

    # internal/ — Alex is primary, Lisa is backup, Priya touched it historically
    await _seed_contribution("alex.chen",    "internal", commit_count=187, lines_changed=4210, expertise_score=0.82, last_contribution_at=yesterday)
    await _seed_contribution("lisa.park",    "internal", commit_count=54,  lines_changed=890,  expertise_score=0.31, last_contribution_at=three_days_ago)
    await _seed_contribution("priya.sharma", "internal", commit_count=38,  lines_changed=640,  expertise_score=0.29, last_contribution_at=six_months_ago)

    # scripts/ — Priya is the ONLY person who has ever touched this
    await _seed_contribution("priya.sharma", "scripts", commit_count=142, lines_changed=3870, expertise_score=0.97, last_contribution_at=six_months_ago)

    # shared/ — distributed ownership
    await _seed_contribution("alex.chen",    "shared", commit_count=103, lines_changed=2150, expertise_score=0.74, last_contribution_at=yesterday)
    await _seed_contribution("lisa.park",    "shared", commit_count=98,  lines_changed=1980, expertise_score=0.68, last_contribution_at=three_days_ago)
    await _seed_contribution("priya.sharma", "shared", commit_count=47,  lines_changed=870,  expertise_score=0.41, last_contribution_at=six_months_ago)

    # test/ — Lisa leads, Alex solid backup, Marco has 1 commit (his first PR)
    await _seed_contribution("lisa.park",    "test", commit_count=119, lines_changed=3410, expertise_score=0.71, last_contribution_at=three_days_ago)
    await _seed_contribution("alex.chen",    "test", commit_count=88,  lines_changed=2240, expertise_score=0.58, last_contribution_at=yesterday)
    await _seed_contribution("marco.torres", "test", commit_count=1,   lines_changed=18,   expertise_score=0.04, last_contribution_at=two_weeks_ago)

    # app/ — Alex is sole internal committer (most upstream-authored module)
    await _seed_contribution("alex.chen",    "app",  commit_count=74,  lines_changed=1620, expertise_score=0.89, last_contribution_at=yesterday)

    # ── Fork date override ────────────────────────────────────────────────────
    # Stored in MongoDB so the Repo History chart splits upstream vs internal.
    # GitLab's project.created_at is the fallback for non-demo repos.
    await _set_fork_date(twelve_months)

    # ── Upstream authors (pre-fork) ───────────────────────────────────────────
    # These represent the original gitlab-pages maintainers whose work this fork
    # is built on. Set fork date override to ~12 months ago in Configuration to
    # see them split cleanly from the internal team on the Repo History chart.

    await _seed_upstream_author("tim.arch",     "Tim Arch",     5001, last_seen=twelve_months)
    await _seed_upstream_author("remi.pages",   "Remi Pages",   5002, last_seen=fourteen_months)
    await _seed_upstream_author("sofia.mueller","Sofia Mueller", 5003, last_seen=sixteen_months)

    # Tim Arch — primary upstream author of app/ and internal/ (explains why Alex
    # inherited a well-structured codebase but has no backup)
    await _seed_contribution("tim.arch", "app",      commit_count=318, lines_changed=9140, expertise_score=0.95, last_contribution_at=twelve_months,   external=True)
    await _seed_contribution("tim.arch", "internal", commit_count=244, lines_changed=5920, expertise_score=0.88, last_contribution_at=twelve_months,   external=True)
    await _seed_contribution("tim.arch", "shared",   commit_count=191, lines_changed=3510, expertise_score=0.72, last_contribution_at=fourteen_months, external=True)

    # Remi Pages — wrote the original scripts/ tooling that Priya inherited
    await _seed_contribution("remi.pages", "scripts", commit_count=201, lines_changed=4380, expertise_score=0.83, last_contribution_at=fourteen_months, external=True)
    await _seed_contribution("remi.pages", "shared",  commit_count=114, lines_changed=2410, expertise_score=0.62, last_contribution_at=sixteen_months,  external=True)

    # Sofia Mueller — early test/ framework author, no longer active
    await _seed_contribution("sofia.mueller", "test",   commit_count=287, lines_changed=6780, expertise_score=0.91, last_contribution_at=sixteen_months, external=True)
    await _seed_contribution("sofia.mueller", "shared", commit_count=88,  lines_changed=1640, expertise_score=0.54, last_contribution_at=sixteen_months, external=True)

    # ── Modules ──────────────────────────────────────────────────────────────

    await _seed_module("internal", bus_factor=2, owners=["alex.chen"])
    await _seed_module("scripts",  bus_factor=1, owners=["priya.sharma"])  # sole holder, inactive
    await _seed_module("shared",   bus_factor=3, owners=["alex.chen", "lisa.park"])
    await _seed_module("test",     bus_factor=3, owners=[])                # no CODEOWNERS entry
    await _seed_module("app",      bus_factor=1, owners=["alex.chen"])

    print("[seed] full team seeded:")
    print("  internal:   alex.chen, priya.sharma, marco.torres, lisa.park")
    print("  upstream:   tim.arch, remi.pages, sofia.mueller (external=True, pre-fork authors)")
    print("  modules:    internal, scripts, shared, test, app")
    print("  concerns:   scripts/ sole-holder inactive, marco new-joiner, app/ concentrated")
    print("  tip:        set fork date override to ~12 months ago in /config to split the chart")


# ---------------------------------------------------------------------------
# Individual scenario shims (kept for targeted testing)
# ---------------------------------------------------------------------------

async def scenario_new_joiner():
    """Marco Torres — joined 2 weeks ago, 1 test commit. → generate_onboarding_pack"""
    await _delete_by_usernames(["marco.torres"])
    await _seed_developer(
        username="marco.torres", name="Marco Torres", gitlab_id=9013,
        expertise={}, last_seen=_now() - timedelta(days=14),
    )
    await _seed_contribution(
        "marco.torres", "test",
        commit_count=1, lines_changed=18, expertise_score=0.04,
        last_contribution_at=_now() - timedelta(days=14),
    )
    print("[seed] new_joiner: marco.torres (1 commit in test/)")


async def scenario_fading_contributor():
    """Priya Sharma — sole scripts/ owner, 6 months inactive. → generate_offboarding_artifact"""
    await _delete_by_usernames(["priya.sharma"])
    await _delete_by_modules(["scripts"])
    six_months_ago = _now() - timedelta(days=183)
    await _seed_developer(
        username="priya.sharma", name="Priya Sharma", gitlab_id=9012,
        expertise={"scripts": 0.97, "shared": 0.41},
        last_seen=six_months_ago,
    )
    for module_path, count, lines, score in [
        ("scripts", 142, 3870, 0.97),
        ("shared",   47,  870, 0.41),
    ]:
        await _seed_contribution("priya.sharma", module_path, count, lines, score, six_months_ago)
    await _seed_module("scripts", bus_factor=1, owners=["priya.sharma"])
    print("[seed] fading: priya.sharma (scripts/ sole holder, inactive 6mo)")


async def scenario_sole_owner():
    """Alex Chen — sole owner of app/ with no backup. → create_issue (Knowledge Transfer)"""
    await _delete_by_usernames(["alex.chen"])
    await _delete_by_modules(["app"])
    yesterday = _now() - timedelta(days=1)
    await _seed_developer(
        username="alex.chen", name="Alex Chen", gitlab_id=9011,
        expertise={"internal": 0.82, "app": 0.89, "shared": 0.74},
        last_seen=yesterday,
    )
    await _seed_contribution("alex.chen", "app",  74,  1620, 0.89, yesterday)
    await _seed_contribution("alex.chen", "internal", 187, 4210, 0.82, yesterday)
    await _seed_module("app",      bus_factor=1, owners=["alex.chen"])
    await _seed_module("internal", bus_factor=1, owners=["alex.chen"])
    print("[seed] sole_owner: alex.chen (sole holder of app/ and internal/)")


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------

async def clear_all():
    filter_ = {"demo": True}
    results = {}
    for col in ("developers", "modules", "contributions"):
        r = await db()[col].delete_many(filter_)
        results[col] = r.deleted_count
    await _set_fork_date(None)
    print(f"[seed] cleared: {results}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    args = sys.argv[1:]
    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        return

    if "--clear" in args or "clear" in args:
        await clear_all()
        return

    ran_any = False
    if "team" in args or "all" in args:
        await scenario_full_team(); ran_any = True
    else:
        if "new_joiner" in args:
            await scenario_new_joiner(); ran_any = True
        if "fading" in args:
            await scenario_fading_contributor(); ran_any = True
        if "sole_owner" in args:
            await scenario_sole_owner(); ran_any = True

    if not ran_any:
        print(f"Unknown scenario(s): {args}")
        print("Valid: team | all | new_joiner | fading | sole_owner | --clear")


if __name__ == "__main__":
    asyncio.run(main())
