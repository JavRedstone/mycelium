import logging

import gitlab
from config.settings import settings

logger = logging.getLogger(__name__)

_SKIP_DIRS = {"vendor", "node_modules", "Godeps", "third_party"}

# GitLab namespace paths appear as commit author *names* for bots and automated
# maintenance operations in forked repos (e.g. "gitlab-org/maintainers/gitlab-pages").
# Real human names never contain "/".  Email-only no-reply addresses are also bots.
def _is_bot_author(name: str, email: str) -> bool:
    """Return True for automated / service-account commit authors to exclude from tracking."""
    if "/" in name:
        return True
    # GitLab bot no-reply address patterns: "GitLab Bot <noreply@gitlab.com>"
    if email and "noreply" in email.lower() and "gitlab" in email.lower():
        return True
    return False


class GitLabClient:
    """Thin REST wrapper around python-gitlab for the Mycelium observation layer."""

    def __init__(self):
        self._gl = gitlab.Gitlab(
            url=settings.gitlab_url,
            private_token=settings.gitlab_token,
        )
        # _project_obj is fetched lazily on first access via the _project property
        # so that GitLabClient() construction never makes a network call at import time.
        self._project_obj = None
        self._default_branch: str = "main"  # updated on first _project access
        # Per-run caches - reset by invalidate_cache() at the start of each pipeline run
        self._cached_member_usernames: set[str] | None = None
        self._cached_member_names: set[str] | None = None
        self._cached_member_emails: set[str] | None = None

    @property
    def _project(self):
        """Fetch and cache the GitLab project object on first access."""
        if self._project_obj is None:
            self._project_obj = self._gl.projects.get(settings.gitlab_project_id)
            self._default_branch = getattr(self._project_obj, "default_branch", None) or "main"
        return self._project_obj

    # ---------------------------------------------------------------------------
    # Member caches - built once per run for O(1) membership lookups
    # ---------------------------------------------------------------------------

    def _refresh_member_cache(self) -> None:
        members = self.get_members()
        self._cached_member_usernames = {m["username"].lower() for m in members if m.get("username")}
        self._cached_member_names = {m["name"].lower() for m in members if m.get("name")}
        # Fetch public emails - best-effort, often empty on GitLab.com
        emails: set[str] = set()
        try:
            for m in self._project.members.list(all=True):
                user = self._gl.users.get(m.id)
                if getattr(user, "public_email", None):
                    emails.add(user.public_email.lower())
        except Exception:
            pass
        self._cached_member_emails = emails

    def _member_usernames(self) -> set[str]:
        if self._cached_member_usernames is None:
            self._refresh_member_cache()
        return self._cached_member_usernames

    def _member_names(self) -> set[str]:
        if self._cached_member_names is None:
            self._refresh_member_cache()
        return self._cached_member_names

    def _member_emails(self) -> set[str]:
        if self._cached_member_emails is None:
            self._refresh_member_cache()
        return self._cached_member_emails

    def invalidate_cache(self) -> None:
        """Reset per-run caches. Call at the start of each pipeline run."""
        self._cached_member_usernames = None
        self._cached_member_names = None
        self._cached_member_emails = None

    def _is_member(self, name: str, email: str) -> bool:
        """Check if a commit author is a current project member.

        Matches on display name, username, or email - all lowercased.
        Name matching is the most reliable on GitLab.com where public_email
        is usually hidden.
        """
        name_l = name.lower()
        email_l = email.lower()
        return (
            name_l in self._member_names()
            or name_l in self._member_usernames()
            or (bool(email_l) and email_l in self._member_emails())
        )

    # ---------------------------------------------------------------------------
    # Observation
    # ---------------------------------------------------------------------------

    def get_members(self) -> list[dict]:
        from config.settings import settings
        bot = settings.gitlab_bot_username.lower()
        return [
            {"id": m.id, "username": m.username, "name": m.name, "access_level": m.access_level}
            for m in self._project.members.list(all=True)
            if m.username.lower() != bot
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

    def get_repository_contributors(self) -> list[dict]:
        """All contributors from git history with accurate commit counts.

        Uses GitLab's /repository/contributors endpoint directly via http_list
        so we control pagination (per_page=100) and avoid getattr on plain dicts.
        The endpoint returns commit counts across the full reachable git history.
        """
        try:
            results = []
            for item in self._gl.http_list(
                f"/projects/{self._project.id}/repository/contributors",
                query_data={"order_by": "commits", "sort": "desc"},
                per_page=100,
                iterator=True,
            ):
                results.append({
                    "name": item.get("name", "") or "",
                    "email": (item.get("email", "") or "").lower(),
                    "commit_count": item.get("commits", 0),
                    "additions": item.get("additions", 0),
                    "deletions": item.get("deletions", 0),
                })
            logger.info("[gitlab] get_repository_contributors: %d contributors", len(results))
            return results
        except Exception as exc:
            logger.warning("[gitlab] get_repository_contributors failed: %s", exc)
            return []

    def get_commit_contributors(self, ref: str | None = None) -> list[dict]:
        """Contributors with actual commit counts, classified as internal/external.

        Uses the /repository/contributors API for accurate commit counts.
        Falls back to counting from the commit list if that endpoint fails.
        """
        contributors = self.get_repository_contributors()

        if not contributors:
            # Fallback: enumerate commits and count per author
            seen: dict[str, dict] = {}
            for commit in self.get_recent_commits(ref=ref):
                email = (commit.get("author_email") or "").lower()
                name = commit.get("author_name") or email
                key = email or name
                if not key:
                    continue
                if key in seen:
                    seen[key]["commit_count"] += 1
                else:
                    seen[key] = {
                        "name": name,
                        "email": email,
                        "commit_count": 1,
                        "external": not self._is_member(name, email),
                        "contribution_type": "commit",
                    }
            return list(seen.values())

        return [
            {
                "name": c["name"],
                "email": c["email"],
                "commit_count": c["commit_count"],
                "external": not self._is_member(c["name"], c["email"]),
                "contribution_type": "commit",
            }
            for c in contributors
            if not _is_bot_author(c["name"], c["email"])
        ]

    def get_open_issues(self) -> list[dict]:
        from config.settings import settings
        bot = settings.gitlab_bot_username.lower()
        result = []
        for i in self._project.issues.list(state="opened", all=True):
            # python-gitlab returns author as a dict: {"id": ..., "username": ...}
            author_obj = getattr(i, "author", None) or {}
            author_username = (author_obj.get("username") if isinstance(author_obj, dict) else getattr(author_obj, "username", None)) or ""
            assignee_obj = getattr(i, "assignee", None)
            assignee_username = (assignee_obj.get("username") if isinstance(assignee_obj, dict) else getattr(assignee_obj, "username", None)) if assignee_obj else None
            result.append({
                "id": i.id,
                "iid": i.iid,
                "title": i.title,
                "author": author_username or None,
                "bot_authored": author_username.lower() == bot,
                "assignee": assignee_username,
                "labels": i.labels,
                "created_at": i.created_at,
            })
        return result

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

    def get_top_level_dirs(self) -> list[str]:
        """Top-level directories on the default branch, capped at 20 to bound API volume."""
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

    def get_directory_contributors(self, dir_path: str, max_commits: int = 500) -> list[dict]:
        """Who committed to this directory, with per-author commit counts.

        Counts are accumulated across up to max_commits commits so the top
        contributor in each directory scores 1.0 relative expertise.

        Uses http_list directly instead of commits.list(path=...) because
        python-gitlab's ListMixin intercepts the 'path' kwarg as a URL path
        override rather than passing it as a query parameter, which causes 404.
        """
        return self.get_directory_contributors_with_history(dir_path, max_commits)

    def get_directory_contributors_with_history(self, dir_path: str, max_commits: int = 500) -> list[dict]:
        """Like get_directory_contributors but also captures monthly_counts per author.

        Returns list of {name, email, commit_count, external, monthly_counts: {"YYYY-MM": N}}.
        monthly_counts enables timeline visualization without a second API pass.
        """
        try:
            seen: dict[str, dict] = {}
            total_collected = 0

            commits_api_path = f"/projects/{self._project.id}/repository/commits"
            commit_iter = self._gl.http_list(
                commits_api_path,
                query_data={"ref_name": self._default_branch, "path": dir_path},
                iterator=True,
            )

            for commit in commit_iter:
                if total_collected >= max_commits:
                    break
                email = (commit.get("author_email") or "").lower()
                name = commit.get("author_name") or email
                # Skip bots and GitLab namespace paths (e.g. "gitlab-org/maintainers/...").
                # These are automated actors from upstream fork history, not real contributors.
                if _is_bot_author(name, email):
                    continue
                key = email or name
                if not key:
                    continue
                created_at = commit.get("created_at") or ""
                year_month = created_at[:7] if len(created_at) >= 7 else ""
                if key not in seen:
                    seen[key] = {
                        "name": name,
                        "email": email,
                        "commit_count": 0,
                        "external": not self._is_member(name, email),
                        "monthly_counts": {},
                        "first_commit_at": created_at,
                        "last_commit_at": created_at,
                    }
                seen[key]["commit_count"] += 1
                if year_month:
                    mc = seen[key]["monthly_counts"]
                    mc[year_month] = mc.get(year_month, 0) + 1
                if created_at:
                    if not seen[key]["first_commit_at"] or created_at < seen[key]["first_commit_at"]:
                        seen[key]["first_commit_at"] = created_at
                    if not seen[key]["last_commit_at"] or created_at > seen[key]["last_commit_at"]:
                        seen[key]["last_commit_at"] = created_at
                total_collected += 1

            logger.info(
                "[gitlab] get_directory_contributors_with_history(%s): %d commits, %d unique authors",
                dir_path, total_collected, len(seen),
            )
            return list(seen.values())
        except Exception as exc:
            logger.warning("[gitlab] get_directory_contributors_with_history(%s) failed: %s", dir_path, exc)
            return []

    def get_codeowners(self) -> dict[str, list[str]]:
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
        """Approvers of recently merged MRs - implicit knowledge holders."""
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

    def get_module_contributor_map(self) -> dict[str, list[dict]]:
        """Per-directory contributor map - who knows what part of the codebase."""
        result: dict[str, list[dict]] = {}
        dirs = self.get_top_level_dirs()
        logger.info("[gitlab] map_modules: %d top-level directories: %s", len(dirs), dirs)
        for path in dirs:
            contribs = self.get_directory_contributors(path)
            if contribs:
                result[path] = contribs
                logger.info("[gitlab] %s: %d contributor(s)", path, len(contribs))
            else:
                logger.info("[gitlab] %s: no contributors found", path)
        return result

    # ---------------------------------------------------------------------------
    # Investigator helpers - file content + member temporal data
    # ---------------------------------------------------------------------------

    def get_directory_tree(self, dir_path: str, recursive: bool = False) -> list[dict]:
        """List files and subdirectories under dir_path on the default branch.

        Returns a list of {"path", "name", "type"} entries. Hidden dot-paths
        and known noise dirs are filtered out. Used by module investigators
        to decide what to read.
        """
        try:
            items = self._project.repository_tree(
                path=dir_path,
                ref=self._default_branch,
                recursive=recursive,
                per_page=100,
                get_all=True,
            )
            results = []
            for item in items:
                p = item["path"]
                name = item["name"]
                if name.startswith("."):
                    continue
                if any(part in _SKIP_DIRS for part in p.split("/")):
                    continue
                results.append({"path": p, "name": name, "type": item["type"]})
            return results
        except Exception as exc:
            logger.warning("[gitlab] get_directory_tree(%s) failed: %s", dir_path, exc)
            return []

    def get_file_content(self, file_path: str, max_bytes: int = 8192) -> str | None:
        """Fetch raw text content of a file from the default branch.

        Returns None if the file is missing, binary, or oversized.
        Truncates to max_bytes for LLM context budget reasons.
        """
        try:
            raw = self._project.files.raw(file_path=file_path, ref=self._default_branch)
            if isinstance(raw, bytes):
                # Reject obvious binaries - null byte in first chunk is a strong signal.
                if b"\x00" in raw[:512]:
                    return None
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    return None
            else:
                text = raw
            if len(text) > max_bytes:
                return text[:max_bytes] + f"\n\n... [truncated, full size {len(text)} bytes]"
            return text
        except Exception as exc:
            logger.debug("[gitlab] get_file_content(%s) skipped: %s", file_path, exc)
            return None

    def get_member_activity_dates(self) -> dict[str, dict]:
        """First and last commit timestamps per author (by name and by email).

        Used to derive 'recently joined' and 'recently inactive' member labels
        from commit history alone - no GitLab member.created_at fetch needed.

        Returns {key: {"first_commit": iso, "last_commit": iso, "commit_count": N}}
        keyed by lowercased name AND lowercased email so the caller can match
        either way.
        """
        try:
            commits = self.get_recent_commits()
        except Exception as exc:
            logger.warning("[gitlab] get_member_activity_dates: commit fetch failed: %s", exc)
            return {}

        by_key: dict[str, dict] = {}
        for c in commits:
            ts = c.get("created_at") or ""
            email = (c.get("author_email") or "").lower()
            name = (c.get("author_name") or "").lower()
            for key in (email, name):
                if not key:
                    continue
                entry = by_key.setdefault(key, {
                    "first_commit": ts,
                    "last_commit": ts,
                    "commit_count": 0,
                })
                entry["commit_count"] += 1
                # ISO 8601 timestamps sort lexicographically.
                if ts and (not entry["first_commit"] or ts < entry["first_commit"]):
                    entry["first_commit"] = ts
                if ts and (not entry["last_commit"] or ts > entry["last_commit"]):
                    entry["last_commit"] = ts
        return by_key

    def get_upstream_commits_since_fork(self, max_commits: int = 25) -> list[dict]:
        """Return upstream commits the fork hasn't merged yet (most recent first).

        For the drift investigator. Returns commit metadata including id, title,
        author, and file change summary (not full diffs - too expensive).
        Returns [] if not a fork or upstream is unreachable.
        """
        upstream_info = getattr(self._project, "forked_from_project", None)
        if not upstream_info:
            return []
        upstream_id = (
            upstream_info.get("id") if isinstance(upstream_info, dict)
            else getattr(upstream_info, "id", None)
        )
        if not upstream_id:
            return []
        try:
            upstream = self._gl.projects.get(upstream_id)
            upstream_branch_name = getattr(upstream, "default_branch", None) or "main"
            upstream_branch = upstream.branches.get(upstream_branch_name)
            upstream_sha = upstream_branch.commit["id"]

            our_branch = self._project.branches.get(self._default_branch)
            our_sha = our_branch.commit["id"]

            commits = []

            # Strategy 1: compare on the upstream project side - our SHA is in
            # upstream's history for clean forks, so this usually succeeds.
            try:
                comparison = upstream.repository_compare(from_=our_sha, to=upstream_sha)
                commits = comparison.get("commits", []) or []
            except Exception:
                pass

            # Strategy 2: compare on our fork - only works when upstream SHA has
            # been fetched into our object store.
            if not commits:
                try:
                    comparison = self._project.repository_compare(
                        from_=self._default_branch, to=upstream_sha
                    )
                    commits = comparison.get("commits", []) or []
                except Exception:
                    logger.debug(
                        "[gitlab] get_upstream_commits_since_fork: compare API "
                        "unreachable across projects - returning empty list"
                    )
                    return []

            results = []
            for c in commits[:max_commits]:
                results.append({
                    "id": (c.get("id") or "")[:12],
                    "title": (c.get("title") or "").strip(),
                    "message": (c.get("message") or "").strip()[:500],
                    "author_name": c.get("author_name", ""),
                    "created_at": c.get("created_at", ""),
                })
            return results
        except Exception as exc:
            logger.debug("[gitlab] get_upstream_commits_since_fork: %s", exc)
            return []

    def get_fork_divergence(self) -> dict | None:
        """Return how many commits this fork is behind its upstream, if applicable.

        Tries two comparison strategies before giving up:
        1. Compare on the upstream project (from our SHA to upstream HEAD) - works
           when our fork's HEAD exists in the upstream's git history (clean fork).
        2. Compare on our fork project (from our branch to upstream SHA) - works
           when the upstream SHA has been fetched into our fork.

        If neither compare works, returns the upstream relationship info with
        commits_behind=None rather than None, so downstream stages still know
        this is a fork. Returns None only if the upstream project is inaccessible.
        """
        upstream_info = getattr(self._project, "forked_from_project", None)
        if not upstream_info:
            return None
        upstream_id = (
            upstream_info.get("id") if isinstance(upstream_info, dict)
            else getattr(upstream_info, "id", None)
        )
        if not upstream_id:
            return None
        try:
            upstream = self._gl.projects.get(upstream_id)
            upstream_branch_name = getattr(upstream, "default_branch", None) or "main"
            upstream_name = (
                upstream_info.get("path_with_namespace") if isinstance(upstream_info, dict)
                else getattr(upstream_info, "path_with_namespace", str(upstream_id))
            )

            upstream_branch = upstream.branches.get(upstream_branch_name)
            upstream_sha = upstream_branch.commit["id"]

            our_branch = self._project.branches.get(self._default_branch)
            our_sha = our_branch.commit["id"]

            commits_behind: int | None = None

            # Strategy 1: compare on the upstream project side.
            # Our fork's HEAD is in upstream's history if we haven't diverged far.
            try:
                comparison = upstream.repository_compare(from_=our_sha, to=upstream_sha)
                commits_behind = len(comparison.get("commits", []))
            except Exception:
                pass

            # Strategy 2: compare on our fork side (original approach).
            # Fails when the upstream SHA isn't reachable from our fork's refs.
            if commits_behind is None:
                try:
                    comparison = self._project.repository_compare(
                        from_=self._default_branch, to=upstream_sha
                    )
                    commits_behind = len(comparison.get("commits", []))
                except Exception:
                    logger.debug(
                        "[gitlab] get_fork_divergence: compare API unreachable across "
                        "projects - returning upstream info without commit count"
                    )

            return {
                "commits_behind": commits_behind,
                "upstream_project": upstream_name,
                "upstream_branch": upstream_branch_name,
            }
        except Exception as exc:
            logger.debug("[gitlab] get_fork_divergence: %s", exc)
            return None

    def snapshot(self) -> dict:
        self.invalidate_cache()
        contributors = self.get_commit_contributors()
        upstream_authors = [c for c in contributors if c["external"]]
        is_fork = bool(getattr(self._project, "forked_from_project", None))
        total = len(contributors)
        upstream_ratio = round(len(upstream_authors) / total, 2) if total > 0 else 0.0
        fork_divergence = self.get_fork_divergence() if is_fork else None
        return {
            "project_id": self._project.id,
            "project_path": getattr(self._project, "path_with_namespace", str(settings.gitlab_project_id)),
            "members": self.get_members(),
            "open_issues": self.get_open_issues(),
            "open_merge_requests": self.get_open_merge_requests(),
            "commit_contributors": contributors,
            "upstream_authors": upstream_authors,
            "codeowners": self.get_codeowners(),
            "pipeline_status": self.get_pipeline_status(),
            "mr_approvers": self.get_mr_approvers(),
            "is_fork": is_fork,
            "upstream_author_ratio": upstream_ratio,
            "fork_divergence": fork_divergence,
        }

    def get_project_info(self) -> dict:
        """Return display metadata about the configured GitLab project."""
        p = self._project
        ns = getattr(p, "namespace", {}) or {}
        return {
            "id":                   p.id,
            "name":                 getattr(p, "name", ""),
            "path":                 getattr(p, "path", ""),
            "path_with_namespace":  getattr(p, "path_with_namespace", ""),
            "namespace_name":       ns.get("name", "") if isinstance(ns, dict) else getattr(ns, "name", ""),
            "namespace_path":       ns.get("path", "") if isinstance(ns, dict) else getattr(ns, "path", ""),
            "web_url":              getattr(p, "web_url", ""),
            "default_branch":       self._default_branch,
            "description":          getattr(p, "description", None),
            "star_count":           getattr(p, "star_count", 0),
            "forks_count":          getattr(p, "forks_count", 0),
            "is_fork":              bool(getattr(p, "forked_from_project", None)),
            "created_at":           getattr(p, "created_at", None),
        }

    # ---------------------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------------------

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

    def close_issue(self, issue_iid: int) -> dict:
        issue = self._project.issues.get(issue_iid)
        issue.state_event = "close"
        issue.save()
        return {"iid": issue_iid, "state": "closed"}

    def edit_issue(self, issue_iid: int, description: str, title: str | None = None) -> dict:
        issue = self._project.issues.get(issue_iid)
        issue.description = description
        if title is not None:
            issue.title = title
        issue.save()
        return {"iid": issue_iid}

    # ------------------------------------------------------------------
    # Bot-issue cleanup
    # ------------------------------------------------------------------

    def list_bot_issues(self) -> list[dict]:
        """Return all open issues that were created by the Mycelium bot.

        An issue is considered bot-created if:
          (a) its author matches settings.gitlab_bot_username, OR
          (b) it carries the "mycelium" label (applied by the MCP tools).
        """
        from config.settings import settings
        bot = settings.gitlab_bot_username.lower()
        result = []
        for i in self._project.issues.list(state="opened", all=True):
            author_obj = getattr(i, "author", None) or {}
            author_username = (
                author_obj.get("username")
                if isinstance(author_obj, dict)
                else getattr(author_obj, "username", None)
            ) or ""
            labels: list[str] = list(getattr(i, "labels", []) or [])
            is_bot_authored = author_username.lower() == bot
            has_mycelium_label = "mycelium" in labels
            if is_bot_authored or has_mycelium_label:
                assignee_obj = getattr(i, "assignee", None) or {}
                assignee_name = (
                    assignee_obj.get("name") or assignee_obj.get("username")
                    if isinstance(assignee_obj, dict)
                    else getattr(assignee_obj, "name", None) or getattr(assignee_obj, "username", None)
                ) or None
                description: str = getattr(i, "description", "") or ""
                result.append({
                    "iid": i.iid,
                    "title": i.title,
                    "created_at": i.created_at,
                    "updated_at": getattr(i, "updated_at", None),
                    "labels": labels,
                    "web_url": getattr(i, "web_url", None),
                    "bot_authored": is_bot_authored,
                    "assignee": assignee_name,
                    "description_preview": description[:200] if description else None,
                })
        return result

    def close_bot_issues(self) -> dict:
        """Close every open bot-created issue, leaving an explanatory comment first.

        Returns a summary: {"closed": N, "errors": N, "total": N}.
        """
        issues = self.list_bot_issues()
        closed = 0
        errors = 0
        for iss in issues:
            iid = iss["iid"]
            try:
                self.comment_on_issue(
                    issue_iid=iid,
                    body=(
                        "Closed by Mycelium Continuity Engine (automated cleanup).\n\n"
                        "This issue was created automatically and has been closed via the "
                        "Mycelium configuration panel. Re-run the pipeline to generate "
                        "fresh findings and actions."
                    ),
                )
                self.close_issue(issue_iid=iid)
                closed += 1
            except Exception as exc:
                errors += 1
        return {"closed": closed, "errors": errors, "total": len(issues)}

    def close_stale_bot_issue(
        self,
        issue_iid: int,
        superseded_by: dict | None = None,
    ) -> None:
        """Close a single bot issue that is stale or superseded by a newer one.

        Leaves an explanatory comment before closing so the audit trail is preserved.

        Args:
            issue_iid: IID of the issue to close.
            superseded_by: Optional dict with ``iid`` and ``web_url`` of the new
                           issue that replaces this one.
        """
        if superseded_by:
            new_iid = superseded_by.get("iid", "")
            new_url = superseded_by.get("web_url", "")
            body = (
                f"This issue has been superseded by #{new_iid}.\n\n"
                f"A new pipeline run produced updated findings for this subject. "
                f"Please refer to {new_url} for current information."
            )
        else:
            body = (
                "This issue is no longer an active concern based on the latest analysis.\n\n"
                "The most recent pipeline run did not identify this subject as requiring "
                "attention. It has been closed automatically. Re-run the pipeline at any "
                "time to refresh findings."
            )
        self.comment_on_issue(issue_iid=issue_iid, body=body)
        self.close_issue(issue_iid=issue_iid)

    def seed_stale_demo_issues(self) -> list[dict]:
        """Create sample 'outdated' bot issues for demo purposes.

        These issues are intentionally stale - they describe findings from a
        hypothetical prior run. The next pipeline run will detect that their
        subjects are no longer present (or are superseded) and close them
        automatically, demonstrating the stale-issue cleanup flow.

        Returns a list of created issue dicts (iid, title, web_url).
        """
        stale_templates = [
            {
                "title": "Knowledge concentration: priya.sharma owns scripts/ exclusively",
                "description": (
                    "## Knowledge Concentration — `scripts/`\n\n"
                    "**Subject:** priya.sharma\n\n"
                    "priya.sharma is the sole internal author of the `scripts/` directory, "
                    "accounting for 100% of commits over the past year. No other team member "
                    "has modified these files. The module contains deployment automation and "
                    "release tooling that is exercised on every production push.\n\n"
                    "**Risk:** If priya.sharma is unavailable, no one else can safely modify "
                    "or debug this module. There is no documented handoff path and no secondary "
                    "reviewer on any of the recent MRs touching this directory.\n\n"
                    "**Recommended actions**\n"
                    "- Identify a second contributor to shadow the next change to `scripts/`\n"
                    "- Add inline documentation to the least-documented entry points\n"
                    "- Designate a CODEOWNERS entry so MRs require a second reviewer\n"
                ),
                "labels": ["mycelium", "continuity-risk"],
            },
            {
                "title": "Recent joiner exposure: marco.torres has no onboarding pair",
                "description": (
                    "## Recent Joiner — Knowledge Transfer Gap\n\n"
                    "**Subject:** marco.torres\n\n"
                    "marco.torres joined the project within the last 30 days. Commit history "
                    "shows activity limited to a single branch; no MRs have been approved by "
                    "a module owner in the areas marco is working in (`api/`, `auth/`). "
                    "There is no CODEOWNERS entry or designated reviewer pairing in place.\n\n"
                    "**Risk:** Without a knowledge-transfer pairing, marco may develop "
                    "incorrect assumptions about module boundaries and review conventions, "
                    "increasing the likelihood of knowledge silos forming early.\n\n"
                    "**Recommended actions**\n"
                    "- Pair marco.torres with the primary owner of `api/` for the next two MRs\n"
                    "- Generate an onboarding pack covering ownership map and key contacts\n"
                    "- Schedule a walkthrough of the auth module before the next sprint\n"
                ),
                "labels": ["mycelium", "onboarding"],
            },
        ]
        created = []
        for t in stale_templates:
            try:
                result = self.create_issue(
                    title=t["title"],
                    description=t["description"],
                    labels=t["labels"],
                )
                created.append(result)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "[gitlab] Failed to seed demo issue '%s': %s", t["title"], exc
                )
        return created
