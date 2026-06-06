# Copyright 2026 Javier Huang
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Unit tests - no external connections required (no GitLab, no MongoDB, no Gemini).
Run with: pytest tests/test_unit.py -v
"""
from datetime import datetime, timezone

from graph.models import DeveloperNode, ContributionEdge, ModuleNode, Finding
from risk.forecasting import compute_bus_factor
from agent.json_utils import try_parse_json as _try_parse_json


# ---------------------------------------------------------------------------
# Helpers mirroring production logic - tested in isolation
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
# Finding model - qualitative output, no scores
# ---------------------------------------------------------------------------

class TestFindingModel:
    def test_minimal_finding(self):
        f = Finding(
            subject="src/auth",
            concern_type="knowledge_concentration",
            narrative="Single internal committer with no documentation.",
        )
        assert f.subject == "src/auth"
        assert f.concern_type == "knowledge_concentration"
        assert f.evidence == []
        assert f.recommended_actions == []
        assert f.id  # uuid auto-generated

    def test_full_finding(self):
        f = Finding(
            run_id="abc-123",
            subject="members/alice",
            concern_type="sole_contributor",
            narrative="Alice is the sole contributor to src/auth.",
            evidence=["investigator/member/alice", "graph/contributors/alice"],
            recommended_actions=["Pair another engineer on src/auth"],
        )
        assert f.run_id == "abc-123"
        assert len(f.evidence) == 2
        assert len(f.recommended_actions) == 1

    def test_module_node_no_score_field(self):
        m = ModuleNode(path="src/auth")
        # No continuity_risk_score, no doc_coverage - measurements only.
        assert not hasattr(m, "continuity_risk_score")
        assert not hasattr(m, "doc_coverage")
        assert m.bus_factor == 0


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
        text = '{"findings": [{"subject": "src/auth", "concern_type": "knowledge_concentration"}]}'
        result = _try_parse_json(text)
        assert result is not None
        assert result["findings"][0]["concern_type"] == "knowledge_concentration"
