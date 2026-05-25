# checks/gitlab/

GitLab connectivity checks - read access and write operations.

Run from the project root (`mycelium/mycelium/`):

---

## check_gitlab.py - read access

```
python checks/gitlab/check_gitlab.py
```

Verifies that the GitLab token can reach the configured project and read:
- Project metadata (name, ID, default branch)
- Project members and their access levels
- Recent commits on the default branch
- CODEOWNERS file (checked in three locations)
- Open issues and merge requests
- Pipeline / CI status

Nothing is written to GitLab.

**Requires:** `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`

---

## check_write.py - write operations

```
python checks/gitlab/check_write.py
```

Tests the full write path that the act agent uses in production:

1. **create_issue** - opens a labelled test issue
2. **add_comment** - posts a note on the issue
3. **assign_issue** - assigns the issue to the token owner
4. **close** - immediately closes the test issue (cleanup)

All four steps go through `GitLabClient` (the same code the pipeline uses),
not through the MCP layer. To check the MCP layer instead, run
`checks/mcp/check_mcp_mycelium.py`.

The test issue is tagged `mycelium-test` and closed automatically. If the
close step fails, the script prints the URL so you can close it manually.

**Requires:** `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`
Token must have at least **Developer** access (to create and close issues).
