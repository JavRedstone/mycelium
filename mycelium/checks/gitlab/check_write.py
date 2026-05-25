"""
GitLab write operations check.

Tests the full write path that the act agent uses:
  1. create_issue   - opens a labelled issue via GitLabClient
  2. add_comment    - posts a note on that issue
  3. assign_issue   - re-assigns it (to the token owner if resolvable)
  4. close          - immediately closes the test issue (cleanup)

All operations go through the same GitLabClient code the pipeline uses,
not through the MCP layer - so this validates the underlying write tooling.
Run check_mcp/check_mcp_mycelium.py to validate that the MCP server exposes
these tools correctly.

Usage:
    python checks/gitlab/check_write.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv()

import gitlab
from config.settings import settings
from connectors.gitlab_client import GitLabClient

_TEST_LABEL = "mycelium-test"
_TEST_TITLE = "[MYCELIUM-TEST] Write connectivity check"


def main() -> int:
    ok = True

    # -----------------------------------------------------------------------
    # Shared resources
    # -----------------------------------------------------------------------
    try:
        client = GitLabClient()
        gl = gitlab.Gitlab(url=settings.gitlab_url, private_token=settings.gitlab_token)
        gl.auth()
        project = gl.projects.get(settings.gitlab_project_id)
        me = gl.user.username if gl.user else None
    except Exception as exc:
        print(f"[FAIL] GitLab setup - {exc}")
        return 1

    issue_iid: int | None = None

    # -----------------------------------------------------------------------
    # 1. create_issue
    # -----------------------------------------------------------------------
    try:
        result = client.create_issue(
            title=_TEST_TITLE,
            description=(
                "This issue was created automatically by `checks/gitlab/check_write.py`.\n"
                "It will be closed immediately - safe to ignore."
            ),
            labels=[_TEST_LABEL],
        )
        issue_iid = result.get("iid")
        web_url = result.get("web_url", "")
        print(f"[OK] create_issue  - #{issue_iid}  {web_url}")
    except Exception as exc:
        print(f"[FAIL] create_issue - {exc}")
        ok = False

    if issue_iid is None:
        print("[SKIP] Remaining write checks skipped (no issue created)")
        return 1

    # -----------------------------------------------------------------------
    # 2. add_comment
    # -----------------------------------------------------------------------
    try:
        note = client.comment_on_issue(
            issue_iid=issue_iid,
            body="Automated comment from Mycelium connectivity check.",
        )
        print(f"[OK] add_comment   - note_id={note.get('note_id')}")
    except Exception as exc:
        print(f"[FAIL] add_comment - {exc}")
        ok = False

    # -----------------------------------------------------------------------
    # 3. assign_issue  (assign to the token owner if we know their username)
    # -----------------------------------------------------------------------
    if me:
        try:
            assign_result = client.assign_issue(issue_iid=issue_iid, assignee_username=me)
            print(f"[OK] assign_issue  - assigned to {assign_result.get('assignee')}")
        except Exception as exc:
            print(f"[FAIL] assign_issue - {exc}")
            ok = False
    else:
        print("[SKIP] assign_issue  - could not resolve token owner username")

    # -----------------------------------------------------------------------
    # 4. Close the test issue (cleanup)
    # -----------------------------------------------------------------------
    try:
        issue = project.issues.get(issue_iid)
        issue.state_event = "close"
        issue.save()
        print(f"[OK] close_issue   - #{issue_iid} closed (cleanup)")
    except Exception as exc:
        print(f"[WARN] close_issue - #{issue_iid} could not be closed automatically: {exc}")
        print(f"       Please close it manually: {web_url}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
