"""
Unit tests — no external connections required (no GitLab, no MongoDB, no Gemini).
Run with: pytest tests/test_unit.py -v
"""
from datetime import datetime, timezone

from graph.models import DeveloperNode, ContributionEdge, ModuleNode
from risk.forecasting import compute_bus_factor, compute_doc_drift, compute_continuity_risk
from agent.analyst_agent import _try_parse_json


# ---------------------------------------------------------------------------
# Helpers mirroring production logic — tested in isolation
# ---------------------------------------------------------------------------

def _parse_codeowners(content: str) -> dict[str, list[str]]:
    """Mirrors GitLabClient.get_codeowners() parsing logic."""
    result: dict[str, list[str]] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern = parts[0]
        owners = [p.lstrip("@") for p in parts[1:] if p.startswith("@")]
        if owners:
            result[pattern] = owners
    return result


def _classify_contributors(commit_authors: list[dict], member_usernames: set[str]) -> list[dict]:
    """Mirrors GitLabClient.get_commit_contributors() classification logic."""
    seen: dict[str, dict] = {}
    for commit in commit_authors:
        email = (commit.get("author_email") or "").lower()
        name = commit.get("author_name") or email
        key = email or name
        if not key or key in seen:
            continue
        is_member = any(name.lower() == u.lower() for u in member_usernames)
        seen[key] = {"name": name, "email": email, "external": not is_member}
    return list(seen.values())


# ---------------------------------------------------------------------------
# DeveloperNode model
# ---------------------------------------------------------------------------

class TestDeveloperNode:
    def test_external_flag_defaults_false(self):
        dev = DeveloperNode(username="alice", name="Alice")
        assert dev.external is False

    def test_external_flag_set_true(self):
        dev = DeveloperNode(username="upstream-bob", name="Bob", external=True, active=False)
        assert dev.external is True
        assert dev.active is False

    def test_internal_active_dev(self):
        dev = DeveloperNode(username="carol", name="Carol", active=True, external=False)
        assert dev.active is True
        assert dev.external is False

    def test_expertise_defaults_empty(self):
        dev = DeveloperNode(username="dave", name="Dave")
        assert dev.expertise == {}


# ---------------------------------------------------------------------------
# ContributionEdge model
# ---------------------------------------------------------------------------

class TestContributionEdge:
    def test_external_edge(self):
        edge = ContributionEdge(
            developer_username="upstream-alice",
            module_path="src/core",
            external=True,
            developer_identity="alice@upstream.org",
        )
        assert edge.external is True
        assert edge.expertise_score == 0.0

    def test_codeowners_edge_full_score(self):
        edge = ContributionEdge(
            developer_username="declared-owner",
            module_path="src/auth",
            expertise_score=1.0,
            external=False,
        )
        assert edge.expertise_score == 1.0

    def test_mr_approver_edge_score(self):
        edge = ContributionEdge(
            developer_username="reviewer",
            module_path="feature-branch",
            expertise_score=0.6,
            external=False,
        )
        assert edge.expertise_score == 0.6


# ---------------------------------------------------------------------------
# Bus factor
# ---------------------------------------------------------------------------

class TestBusFactor:
    def test_empty_returns_zero(self):
        assert compute_bus_factor([]) == 0

    def test_zero_scores_returns_zero(self):
        assert compute_bus_factor([{"expertise_score": 0.0}, {"expertise_score": 0.0}]) == 0

    def test_single_contributor(self):
        assert compute_bus_factor([{"expertise_score": 1.0}]) == 1

    def test_one_dominant_contributor(self):
        contribs = [{"expertise_score": 0.9}, {"expertise_score": 0.05}, {"expertise_score": 0.05}]
        assert compute_bus_factor(contribs) == 1

    def test_two_equal_contributors(self):
        contribs = [{"expertise_score": 0.5}, {"expertise_score": 0.5}]
        assert compute_bus_factor(contribs) == 2

    def test_three_contributors_needed_for_80_pct(self):
        contribs = [{"expertise_score": 0.4}, {"expertise_score": 0.3}, {"expertise_score": 0.3}]
        assert compute_bus_factor(contribs) == 3  # 0.4+0.3=0.7 < 0.8, 0.4+0.3+0.3=1.0 >= 0.8

    def test_many_even_contributors(self):
        contribs = [{"expertise_score": 0.2}] * 5
        result = compute_bus_factor(contribs)
        assert result >= 4


# ---------------------------------------------------------------------------
# Doc drift
# ---------------------------------------------------------------------------

class TestDocDrift:
    def test_no_commits_returns_zero(self):
        assert compute_doc_drift(None, 0.0) == 0.0

    def test_recent_commit_no_docs_high_drift(self):
        recent = datetime.now(timezone.utc)
        drift = compute_doc_drift(recent, 0.0)
        assert drift > 0.8

    def test_recent_commit_full_docs_low_drift(self):
        recent = datetime.now(timezone.utc)
        drift = compute_doc_drift(recent, 1.0)
        assert drift == 0.0

    def test_old_commit_low_drift_regardless_of_docs(self):
        from datetime import timedelta
        old = datetime.now(timezone.utc) - timedelta(days=200)
        drift = compute_doc_drift(old, 0.0)
        assert drift == 0.0


# ---------------------------------------------------------------------------
# Continuity risk score
# ---------------------------------------------------------------------------

class TestContinuityRisk:
    def test_no_contributors_no_owners_max_risk(self):
        module = {"owners": [], "doc_coverage": 0.0, "last_commit_at": None}
        score = compute_continuity_risk([], module)
        assert score >= 0.6

    def test_many_contributors_with_docs_low_risk(self):
        contribs = [{"expertise_score": 0.25}] * 4
        module = {
            "owners": ["alice", "bob", "carol", "dave"],
            "doc_coverage": 1.0,
            "last_commit_at": None,
        }
        score = compute_continuity_risk(contribs, module)
        assert score < 0.4

    def test_single_owner_high_risk(self):
        contribs = [{"expertise_score": 1.0}]
        module = {"owners": ["alice"], "doc_coverage": 0.0, "last_commit_at": None}
        score = compute_continuity_risk(contribs, module)
        assert score >= 0.4

    def test_score_bounded_zero_to_one(self):
        contribs = [{"expertise_score": 1.0}]
        module = {"owners": [], "doc_coverage": 0.0, "last_commit_at": datetime.now(timezone.utc)}
        score = compute_continuity_risk(contribs, module)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# CODEOWNERS parsing
# ---------------------------------------------------------------------------

class TestCodeownersParser:
    def test_basic_ownership(self):
        content = "*.py @alice @bob\nsrc/auth/ @carol"
        result = _parse_codeowners(content)
        assert result["*.py"] == ["alice", "bob"]
        assert result["src/auth/"] == ["carol"]

    def test_comments_and_blanks_ignored(self):
        content = "# This is a comment\n\n*.js @dev\n# another comment"
        result = _parse_codeowners(content)
        assert len(result) == 1
        assert result["*.js"] == ["dev"]

    def test_lines_without_owner_skipped(self):
        content = "*.md\nsrc/ @owner"
        result = _parse_codeowners(content)
        assert "*.md" not in result
        assert result["src/"] == ["owner"]

    def test_empty_file(self):
        assert _parse_codeowners("") == {}

    def test_only_comments(self):
        content = "# comment 1\n# comment 2"
        assert _parse_codeowners(content) == {}

    def test_multiple_owners_on_one_line(self):
        content = "src/critical/ @alice @bob @carol"
        result = _parse_codeowners(content)
        assert result["src/critical/"] == ["alice", "bob", "carol"]

    def test_at_sign_stripped(self):
        content = "src/ @alice"
        result = _parse_codeowners(content)
        assert "alice" in result["src/"]
        assert "@alice" not in result["src/"]


# ---------------------------------------------------------------------------
# External contributor classification
# ---------------------------------------------------------------------------

class TestExternalContributorClassification:
    def test_member_is_not_external(self):
        commits = [{"author_name": "Alice", "author_email": "alice@team.com"}]
        members = {"Alice"}
        result = _classify_contributors(commits, members)
        assert len(result) == 1
        assert result[0]["external"] is False

    def test_non_member_is_external(self):
        commits = [{"author_name": "Upstream Bob", "author_email": "bob@upstream.org"}]
        members = {"Alice", "Carol"}
        result = _classify_contributors(commits, members)
        assert len(result) == 1
        assert result[0]["external"] is True

    def test_mixed_contributors(self):
        commits = [
            {"author_name": "Alice", "author_email": "alice@team.com"},
            {"author_name": "Upstream Bob", "author_email": "bob@upstream.org"},
        ]
        members = {"Alice"}
        result = _classify_contributors(commits, members)
        assert len(result) == 2
        internal = [r for r in result if not r["external"]]
        external = [r for r in result if r["external"]]
        assert len(internal) == 1
        assert len(external) == 1

    def test_duplicate_commits_same_author_deduplicated(self):
        commits = [
            {"author_name": "Alice", "author_email": "alice@team.com"},
            {"author_name": "Alice", "author_email": "alice@team.com"},
        ]
        members = {"Alice"}
        result = _classify_contributors(commits, members)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# JSON parsing (Gemini output robustness)
# ---------------------------------------------------------------------------

class TestTryParseJson:
    def test_clean_json(self):
        assert _try_parse_json('{"key": "value"}') == {"key": "value"}

    def test_json_with_markdown_fences(self):
        text = '```json\n{"key": "value"}\n```'
        assert _try_parse_json(text) == {"key": "value"}

    def test_json_with_plain_fences(self):
        text = '```\n{"key": "value"}\n```'
        assert _try_parse_json(text) == {"key": "value"}

    def test_json_embedded_in_prose(self):
        text = 'Here is the result: {"key": "value"} end.'
        assert _try_parse_json(text) == {"key": "value"}

    def test_invalid_returns_none(self):
        assert _try_parse_json("not json at all") is None

    def test_empty_string_returns_none(self):
        assert _try_parse_json("") is None

    def test_nested_json(self):
        text = '{"risk_assessments": [{"module": "src/auth", "score": 0.8}]}'
        result = _try_parse_json(text)
        assert result is not None
        assert result["risk_assessments"][0]["score"] == 0.8
