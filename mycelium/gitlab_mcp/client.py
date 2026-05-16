import logging

import gitlab
from config.settings import settings

logger = logging.getLogger(__name__)

# Directories that hold third-party code or tooling — not knowledge areas we model
_SKIP_DIRS = {"vendor", "node_modules", "Godeps", "third_party"}


class GitLabClient:
    """
    Thin wrapper around python-gitlab.

    Tools mirror the official GitLab MCP server interface so the agent layer
    can swap to the real MCP binary without changing tool names or signatures.
    """

    def __init__(self):
        self._gl = gitlab.Gitlab(
            url=settings.gitlab_url,
            private_token=settings.gitlab_token,
        )
        self._project = self._gl.projects.get(settings.gitlab_project_id)
        self._default_branch: str = getattr(self._project, "default_branch", None) or "main"
        # Per-run cache — avoids repeated member API calls within a single snapshot()
        self._cached_member_usernames: set[str] | None = None

    def _member_usernames(self) -> set[str]:
        if self._cached_member_usernames is None:
            self._cached_member_usernames = {m["username"].lower() for m in self.get_members()}
        return self._cached_member_usernames

    def invalidate_cache(self) -> None:
        """Reset per-run caches. Call at the start of each pipeline run."""
        self._cached_member_usernames = None

    # --- Observation ---

    def get_members(self) -> list[dict]:
        return [
            {"id": m.id, "username": m.username, "name": m.name, "access_level": m.access_level}
            for m in self._project.members.list(all=True)
        ]

    def get_recent_commits(self, since: str | None = None, ref: str | None = None) -> list[dict]:
        ref = ref or self._default_branch
        kwargs: dict = {"ref_name": ref, "all": True}
        if since:
            kwargs["since"] = since
        return [
            {
                "id": c.id,
                "author_name": c.author_name,
                "author_email": c.author_email,
                "message": c.message,
                "created_at": c.created_at,
                "stats": getattr(c, "stats", {}),
            }
            for c in self._project.commits.list(**kwargs)
        ]

    def get_open_issues(self) -> list[dict]:
        return [
            {
                "id": i.id,
                "iid": i.iid,
                "title": i.title,
                "assignee": i.assignee["username"] if i.assignee else None,
                "labels": i.labels,
                "created_at": i.created_at,
            }
            for i in self._project.issues.list(state="opened", all=True)
        ]

    def get_open_merge_requests(self) -> list[dict]:
        return [
            {
                "id": mr.id,
                "iid": mr.iid,
                "title": mr.title,
                "author": mr.author["username"],
                "assignee": mr.assignee["username"] if mr.assignee else None,
                "source_branch": mr.source_branch,
                "created_at": mr.created_at,
            }
            for mr in self._project.mergerequests.list(state="opened", all=True)
        ]

    def get_repository_tree(self, path: str = "", recursive: bool = False) -> list[dict]:
        return [
            {"id": item["id"], "name": item["name"], "path": item["path"], "type": item["type"]}
            for item in self._project.repository_tree(path=path, recursive=recursive, all=True)
        ]

    def get_commit_contributors(self, ref: str | None = None) -> list[dict]:
        ref = ref or self._default_branch
        """
        Extract unique contributors from commit history.

        For forked repositories, the upstream project's contributors do not
        appear in project members but ARE visible in commit logs. This method
        compares commit authors against the member list and tags non-members
        as external contributors.
        """
        member_usernames = {m["username"] for m in self.get_members()}
        member_emails: set[str] = set()
        try:
            for m in self._project.members.list(all=True):
                user = self._gl.users.get(m.id)
                if getattr(user, "public_email", None):
                    member_emails.add(user.public_email.lower())
        except Exception:
            pass  # email lookup is best-effort

        seen: dict[str, dict] = {}
        for commit in self.get_recent_commits(ref=ref):
            email = (commit.get("author_email") or "").lower()
            name = commit.get("author_name") or email
            key = email or name
            if not key or key in seen:
                continue
            is_member = (
                email in member_emails
                or any(name.lower() == u.lower() for u in member_usernames)
            )
            seen[key] = {
                "name": name,
                "email": email,
                "external": not is_member,
                "contribution_type": "commit",
            }
        return list(seen.values())

    def get_top_level_dirs(self) -> list[str]:
        """
        Top-level directories in the default branch, filtered to meaningful code areas.
        These become the module vocabulary for per-area knowledge attribution.
        Capped at 20 to bound API call volume in get_directory_contributors().
        """
        try:
            items = self._project.repository_tree(
                ref=self._default_branch,
                per_page=100,
                get_all=False,
            )
            all_names = [item["path"] for item in items]
            logger.info("[gitlab] get_top_level_dirs: %d root items: %s", len(all_names), all_names[:30])
            dirs = [
                item["path"] for item in items
                if item["type"] == "tree"
                and not item["path"].startswith(".")
                and item["path"] not in _SKIP_DIRS
            ]
            logger.info("[gitlab] get_top_level_dirs: %d usable dirs: %s", len(dirs), dirs)
            return dirs[:20]
        except Exception as exc:
            logger.warning("[gitlab] get_top_level_dirs failed: %s", exc)
            return []

    def get_directory_contributors(self, path: str, max_commits: int = 300) -> list[dict]:
        """
        Who committed to this directory?

        Uses GitLab's path-filtered commit list to attribute knowledge per code
        area. This is the foundation of per-module expertise mapping — not just
        who contributed globally, but WHO KNOWS WHAT PART of the repo.

        Fetches at most ceil(max_commits/100) pages so large forks don't trigger
        hundreds of API calls. Stops on the last page (< 100 results) or when
        max_commits is reached.
        """
        member_usernames = self._member_usernames()
        try:
            seen: dict[str, dict] = {}
            total_collected = 0
            per_page = 100
            pages_needed = (max_commits + per_page - 1) // per_page  # ceil

            for page_num in range(1, pages_needed + 1):
                batch = self._project.commits.list(
                    ref_name=self._default_branch,
                    path=path,
                    per_page=per_page,
                    page=page_num,
                )
                if not batch:
                    break
                for commit in batch:
                    if total_collected >= max_commits:
                        break
                    email = (getattr(commit, "author_email", "") or "").lower()
                    name = getattr(commit, "author_name", "") or email
                    key = email or name
                    if not key:
                        continue
                    if key in seen:
                        seen[key]["commit_count"] += 1
                    else:
                        is_member = any(name.lower() == u for u in member_usernames)
                        seen[key] = {
                            "name": name,
                            "email": email,
                            "commit_count": 1,
                            "external": not is_member,
                        }
                    total_collected += 1
                if len(batch) < per_page:
                    break  # last page, no need to fetch more

            logger.info(
                "[gitlab] get_directory_contributors(%s): %d commits, %d unique authors",
                path, total_collected, len(seen),
            )
            return list(seen.values())
        except Exception as exc:
            logger.warning("[gitlab] get_directory_contributors(%s) failed: %s", path, exc)
            return []

    def get_codeowners(self) -> dict[str, list[str]]:
        """
        Fetch and parse the CODEOWNERS file (checked in standard locations).
        Returns path_pattern -> [owner_username, ...]. Empty dict if file absent.
        Declared owners are ground-truth: stronger signal than inferred commit history.
        """
        for path in ("CODEOWNERS", ".gitlab/CODEOWNERS", "docs/CODEOWNERS"):
            try:
                raw = self._project.files.raw(file_path=path, ref=self._default_branch)
                content = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                break
            except Exception:
                continue
        else:
            return {}

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

    def get_pipeline_status(self, ref: str | None = None, limit: int = 10) -> list[dict]:
        ref = ref or self._default_branch
        """Recent CI/CD pipeline runs. Failing pipelines amplify continuity risk."""
        try:
            pipelines = self._project.pipelines.list(
                ref=ref, per_page=limit, order_by="id", sort="desc", get_all=False
            )
            return [
                {
                    "id": p.id,
                    "status": p.status,
                    "ref": getattr(p, "ref", ref),
                    "created_at": getattr(p, "created_at", None),
                    "web_url": getattr(p, "web_url", None),
                }
                for p in pipelines
            ]
        except Exception:
            return []

    def get_mr_approvers(self, limit: int = 20) -> list[dict]:
        """
        Who approved recently merged MRs — approvers have reviewed the code and
        hold implicit knowledge of those modules, even without commits.
        """
        try:
            mrs = self._project.mergerequests.list(
                state="merged", order_by="updated_at", sort="desc",
                per_page=limit, get_all=False
            )
            results = []
            for mr in mrs:
                try:
                    approvals = mr.approvals.get()
                    approved_by = [
                        a["user"]["username"]
                        for a in getattr(approvals, "approved_by", [])
                    ]
                    if approved_by:
                        results.append({
                            "mr_iid": mr.iid,
                            "title": mr.title,
                            "source_branch": mr.source_branch,
                            "approved_by": approved_by,
                            "merged_at": getattr(mr, "merged_at", None),
                        })
                except Exception:
                    continue
            return results
        except Exception:
            return []

    # --- Actions ---

    def create_issue(self, title: str, description: str, labels: list[str] | None = None, assignee_username: str | None = None) -> dict:
        payload: dict = {"title": title, "description": description}
        if labels:
            payload["labels"] = ",".join(labels)
        if assignee_username:
            users = self._gl.users.list(username=assignee_username)
            if users:
                payload["assignee_id"] = users[0].id
        issue = self._project.issues.create(payload)
        return {"iid": issue.iid, "id": issue.id, "web_url": issue.web_url}

    def assign_issue(self, issue_iid: int, assignee_username: str) -> dict:
        issue = self._project.issues.get(issue_iid)
        users = self._gl.users.list(username=assignee_username)
        if users:
            issue.assignee_id = users[0].id
            issue.save()
        return {"iid": issue.iid, "assignee": assignee_username}

    def comment_on_issue(self, issue_iid: int, body: str) -> dict:
        issue = self._project.issues.get(issue_iid)
        note = issue.notes.create({"body": body})
        return {"note_id": note.id}

    def comment_on_mr(self, mr_iid: int, body: str) -> dict:
        mr = self._project.mergerequests.get(mr_iid)
        note = mr.notes.create({"body": body})
        return {"note_id": note.id}

    def get_module_contributor_map(self) -> dict[str, list[dict]]:
        """
        Per-directory upstream author mapping — who knows what part of the codebase.

        Called as a dedicated pipeline stage (map_modules) so the expense of one
        API call per directory is isolated and visible, not buried inside snapshot().
        Returns {directory_path: [contributor, ...]} for every top-level code area.
        """
        result: dict[str, list[dict]] = {}
        dirs = self.get_top_level_dirs()
        logger.info("[gitlab] map_modules: %d top-level directories found: %s", len(dirs), dirs)
        for path in dirs:
            contribs = self.get_directory_contributors(path)
            if contribs:
                result[path] = contribs
                logger.info("[gitlab] %s: %d contributor(s)", path, len(contribs))
            else:
                logger.info("[gitlab] %s: no contributors found", path)
        return result

    def snapshot(self) -> dict:
        self.invalidate_cache()  # fresh member data each run
        contributors = self.get_commit_contributors()
        upstream_authors = [c for c in contributors if c["external"]]
        return {
            "members": self.get_members(),
            "open_issues": self.get_open_issues(),
            "open_merge_requests": self.get_open_merge_requests(),
            "commit_contributors": contributors,
            "upstream_authors": upstream_authors,       # replaces "external_contributors"
            "codeowners": self.get_codeowners(),
            "pipeline_status": self.get_pipeline_status(),
            "mr_approvers": self.get_mr_approvers(),
        }
