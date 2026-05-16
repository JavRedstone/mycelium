from datetime import datetime, timezone
from graph.models import ModuleNode, ContributionEdge


def compute_bus_factor(contributions: list[dict]) -> int:
    """Number of contributors whose combined expertise covers >= 80% of a module."""
    if not contributions:
        return 0
    scores = sorted([c["expertise_score"] for c in contributions], reverse=True)
    total = sum(scores)
    if total == 0:
        return 0
    cumulative = 0.0
    for i, s in enumerate(scores):
        cumulative += s
        if cumulative / total >= 0.8:
            return i + 1
    return len(scores)


def compute_doc_drift(last_commit_at: datetime | None, doc_coverage: float) -> float:
    """Returns a drift score 0-1: high when docs are sparse and commits are recent."""
    if last_commit_at is None:
        return 0.0
    now = datetime.now(timezone.utc)
    last_commit_at = last_commit_at.replace(tzinfo=timezone.utc) if last_commit_at.tzinfo is None else last_commit_at
    days_since_commit = (now - last_commit_at).days
    recency_score = max(0.0, 1.0 - days_since_commit / 90)
    return recency_score * (1.0 - doc_coverage)


def compute_continuity_risk(
    contributions: list[dict],
    module: dict,
) -> float:
    """
    Composite risk score 0-1.
    Weights:
        40% bus factor risk (1 / bus_factor, capped)
        40% doc drift
        20% ownership gap (no owners)
    """
    bus_factor = compute_bus_factor(contributions)
    bus_risk = 1.0 if bus_factor == 0 else min(1.0, 1.0 / bus_factor)

    last_commit_raw = module.get("last_commit_at")
    last_commit = datetime.fromisoformat(str(last_commit_raw)) if last_commit_raw else None
    doc_coverage = module.get("doc_coverage", 0.0)
    drift = compute_doc_drift(last_commit, doc_coverage)

    owners = module.get("owners", [])
    ownership_gap = 1.0 if not owners else 0.0

    score = 0.4 * bus_risk + 0.4 * drift + 0.2 * ownership_gap
    return round(min(1.0, score), 4)


def score_all_modules(modules: list[dict], contributions_by_module: dict[str, list[dict]]) -> list[dict]:
    """Return modules with updated continuity_risk_score, sorted by risk descending."""
    results = []
    for module in modules:
        path = module["path"]
        contribs = contributions_by_module.get(path, [])
        risk = compute_continuity_risk(contribs, module)
        results.append({**module, "continuity_risk_score": risk})
    return sorted(results, key=lambda m: m["continuity_risk_score"], reverse=True)
