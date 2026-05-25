"""
Mycelium Data Inspector
=======================
Shows exactly what the agent sees: GitLab project state + knowledge graph.
No agent logic runs -- this is a pure read-only diagnostic.

Usage:
    python checks/show.py              # full report
    python checks/show.py --gitlab     # GitLab only
    python checks/show.py --graph      # MongoDB graph only
    python checks/show.py --commits N  # show last N commits (default 20)
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

# Python automatically adds the script's own directory (checks/) to sys.path.
# Remove it so that checks/gitlab/ doesn't shadow the python-gitlab package.
_script_dir = os.path.dirname(os.path.abspath(__file__))
while _script_dir in sys.path:
    sys.path.remove(_script_dir)

from connectors.gitlab_client import GitLabClient
from graph.knowledge_graph import KnowledgeGraph


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

W = 72

def hdr(title: str, ch: str = "=") -> None:
    print(f"\n{ch * W}")
    print(f"  {title}")
    print(f"{ch * W}")


def sub(title: str) -> None:
    print(f"\n  -- {title} {'-' * max(0, W - len(title) - 6)}")


def row(label: str, value: str, indent: int = 4, flag: str = "") -> None:
    pad = " " * indent
    suffix = f"  {flag}" if flag else ""
    print(f"{pad}{label:<28}{value}{suffix}")


def note(msg: str, indent: int = 4) -> None:
    print(f"{' ' * indent}{msg}")


def blank() -> None:
    print()


# ---------------------------------------------------------------------------
# GitLab section
# ---------------------------------------------------------------------------

def inspect_gitlab(client: GitLabClient, commit_limit: int) -> None:
    hdr("GITLAB PROJECT STATE", ch="=")

    # --- Project info ---
    project = client._project
    sub("Project")
    row("Name:", project.name)
    row("ID:", str(project.id))
    row("Default branch:", getattr(project, "default_branch", "main"))
    row("Visibility:", getattr(project, "visibility", "unknown"))
    if getattr(project, "forked_from_project", None):
        fp = project.forked_from_project
        row("Forked from:", fp.get("path_with_namespace", "unknown"), flag="[fork]")

    # --- Members ---
    members = client.get_members()
    sub(f"Project Members  ({len(members)} total)")
    if not members:
        note("(none)")
    else:
        ACCESS = {10: "Guest", 20: "Reporter", 30: "Developer", 40: "Maintainer", 50: "Owner"}
        for m in members:
            level = ACCESS.get(m.get("access_level", 0), str(m.get("access_level")))
            row(m["username"], f"{m['name']}  [{level}]")

    # --- Commits ---
    commits = client.get_recent_commits()
    member_names_lower = {m["name"].lower() for m in members}
    member_usernames_lower = {m["username"].lower() for m in members}
    default_branch = client._default_branch

    sub(f"Recent Commits on '{default_branch}'  (showing last {min(commit_limit, len(commits))} of {len(commits)} total)")
    if not commits:
        note("(no commits found)")
    else:
        for c in commits[:commit_limit]:
            email = (c.get("author_email") or "").lower()
            name = c.get("author_name") or ""
            sha = c.get("id", "")[:8]
            date = (c.get("created_at") or "")[:10]
            msg = (c.get("message") or "").split("\n")[0][:45]

            is_member = (
                name.lower() in member_names_lower
                or name.lower() in member_usernames_lower
            )
            flag = "" if is_member else "[EXTERNAL]"
            author_str = f"{name} <{email}>"
            print(f"    {sha}  {author_str:<38}  {date}  {msg}  {flag}")

    # --- External contributors ---
    contributors = client.get_commit_contributors()
    external = [c for c in contributors if c["external"]]
    internal = [c for c in contributors if not c["external"]]

    sub(f"Contributor Summary  ({len(internal)} internal, {len(external)} external/upstream)")
    if external:
        note("External authors -- in commit history but NOT current members:")
        for e in external:
            row(e["name"], e.get("email", ""), flag="[upstream/fork author]")
        blank()
        note("!  Modules primarily authored by these contributors are 'dark knowledge'")
        note("   zones -- implementation context not held by any current team member.")
    else:
        note("All commit authors are current project members.")

    # --- CODEOWNERS ---
    codeowners = client.get_codeowners()
    sub(f"CODEOWNERS  ({len(codeowners)} entries)")
    if not codeowners:
        note("No CODEOWNERS file found (checked: CODEOWNERS, .gitlab/CODEOWNERS, docs/CODEOWNERS)")
        note("!  Without declared ownership, all module ownership is inferred from commits.")
    else:
        for pattern, owners in codeowners.items():
            row(pattern, "->  " + ", ".join(owners))

    # --- Pipelines ---
    pipelines = client.get_pipeline_status()
    branch = client._default_branch
    sub(f"Pipeline Status  (last {len(pipelines)} runs on {branch})")
    if not pipelines:
        note("(no pipeline data -- CI/CD may not be configured)")
    else:
        STATUS_ICON = {"success": "OK", "failed": "FAIL", "running": "...", "pending": "..."}
        for p in pipelines:
            icon = STATUS_ICON.get(p.get("status", ""), "?")
            date = (p.get("created_at") or "")[:10]
            url = p.get("web_url") or ""
            status = p.get("status", "unknown")
            print(f"    {icon}  #{p['id']:<8}  {status:<10}  {date}  {url}")

        failing = [p for p in pipelines if p.get("status") == "failed"]
        if failing:
            blank()
            note(f"!  {len(failing)} failing pipeline(s) -- compounding risk in low-bus-factor modules.")

    # --- MR Approvers ---
    mr_approvers = client.get_mr_approvers()
    sub(f"MR Approvers  ({len(mr_approvers)} merged MRs with approval data)")
    if not mr_approvers:
        note("(no approval data -- MR approvals may not be enabled, or no merged MRs yet)")
    else:
        for record in mr_approvers[:15]:
            approvers_str = ", ".join(record.get("approved_by", []))
            branch = record.get("source_branch", "?")
            iid = record.get("mr_iid", "?")
            title = (record.get("title") or "")[:35]
            row(f"!{iid}  {branch[:20]}", f"approved by: {approvers_str}  -- {title}")

    # --- Open Issues ---
    issues = client.get_open_issues()
    sub(f"Open Issues  ({len(issues)} total)")
    if not issues:
        note("(none)")
    else:
        for i in issues[:10]:
            assignee = i.get("assignee") or "unassigned"
            title = (i.get("title") or "")[:50]
            labels = ", ".join(i.get("labels") or []) or "--"
            row(f"#{i['iid']}", f"{title}  [{assignee}]  labels: {labels}")
        if len(issues) > 10:
            note(f"  ... and {len(issues) - 10} more")

    # --- Open MRs ---
    mrs = client.get_open_merge_requests()
    sub(f"Open Merge Requests  ({len(mrs)} total)")
    if not mrs:
        note("(none)")
    else:
        for mr in mrs[:10]:
            author = mr.get("author", "?")
            assignee = mr.get("assignee") or "unassigned"
            title = (mr.get("title") or "")[:50]
            row(f"!{mr['iid']}", f"{title}  [by {author}, assigned {assignee}]")
        if len(mrs) > 10:
            note(f"  ... and {len(mrs) - 10} more")


# ---------------------------------------------------------------------------
# Knowledge graph section
# ---------------------------------------------------------------------------

async def inspect_graph(graph: KnowledgeGraph) -> None:
    hdr("MONGODB KNOWLEDGE GRAPH STATE", ch="=")

    snap = await graph.snapshot()
    developers = snap.get("developers", [])
    external_contributors = snap.get("upstream_authors", [])
    concentrated = snap.get("concentrated_modules", [])
    open_tasks = snap.get("open_tasks", [])
    recent_findings = snap.get("recent_findings", [])

    all_modules = await graph.modules.find({}, {"_id": 0}).to_list(None)

    # --- Internal developers ---
    sub(f"Internal Developers  ({len(developers)} tracked)")
    if not developers:
        note("(none yet -- run the pipeline to populate)")
    else:
        for d in developers:
            expertise = d.get("expertise") or {}
            exp_str = "  ".join(f"{k}: {v:.2f}" for k, v in list(expertise.items())[:4])
            row(d["username"], d.get("name", ""))
            if exp_str:
                note(f"expertise: {exp_str}", indent=8)

    # --- External contributors ---
    sub(f"External / Upstream Contributors  ({len(external_contributors)} tracked)")
    if not external_contributors:
        note("(none yet -- run the pipeline to populate)")
        note("These would be authors from the original/upstream repository.")
    else:
        for d in external_contributors:
            identity = d.get("developer_identity") or d.get("name") or ""
            row(d["username"], identity, flag="[upstream]")

    # --- All modules (measurements only - no scoring) ---
    sub(f"Modules  ({len(all_modules)} tracked) - observational measurements only")
    if not all_modules:
        note("(none yet -- run the pipeline to populate)")
    else:
        for m in all_modules:
            owners = ", ".join(m.get("owners") or []) or "unowned"
            bus = m.get("bus_factor", 0)
            row(m["path"], f"bus_factor={bus}  owners: {owners}")

    # --- Structurally concentrated modules (bus_factor <= 1) ---
    sub(f"Concentrated Modules  (bus_factor <= 1, {len(concentrated)} found)")
    if not concentrated:
        note("(none)")
    else:
        for m in concentrated:
            bus = m.get("bus_factor", 0)
            owners = ", ".join(m.get("owners") or []) or "unowned"
            row(m["path"], f"bus_factor={bus}  owners: {owners}", flag="!")

    # --- Per-module contributions ---
    sub("Contributions (expertise edges)")
    if not all_modules:
        note("(no modules tracked yet)")
    else:
        for m in all_modules:
            contributors = await graph.get_module_contributors(m["path"])
            if not contributors:
                continue
            note(f"  {m['path']}:", indent=4)
            for c in contributors[:5]:
                ext_flag = " [external]" if c.get("external") else ""
                row(
                    c["developer_username"],
                    f"expertise={c['expertise_score']:.2f}  commits={c.get('commit_count', 0)}{ext_flag}",
                    indent=8,
                )

    # --- Findings (qualitative, replaces risk scores) ---
    sub(f"Recent Findings  ({len(recent_findings)} from analyst)")
    if not recent_findings:
        note("(none yet -- run the pipeline to produce findings)")
    else:
        for f in recent_findings[:15]:
            concern = f.get("concern_type", "?")
            subject = f.get("subject", "?")
            narrative = (f.get("narrative") or "").strip()
            row(f"[{concern}]", subject)
            if narrative:
                note(narrative[:160] + ("..." if len(narrative) > 160 else ""), indent=8)

    # --- Open tasks ---
    sub(f"Open Tasks  ({len(open_tasks)} tracked)")
    if not open_tasks:
        note("(none)")
    else:
        for t in open_tasks[:10]:
            assignee = t.get("assignee") or "unassigned"
            row(f"{t['kind']} #{t.get('gitlab_iid', '?')}", f"{t['title'][:50]}  [{assignee}]")


# ---------------------------------------------------------------------------
# Bus-factor drill-downs
# ---------------------------------------------------------------------------

def _bus_factor_breakdown(contributors: list[dict]) -> list[dict]:
    """Return contributors annotated with their share and cumulative share,
    plus a flag marking which ones *together* form the bus factor threshold.
    Mirrors compute_bus_factor logic exactly so numbers match.
    """
    internal = [c for c in contributors if not c.get("external", False)]
    external = [c for c in contributors if c.get("external", False)]
    all_sorted = sorted(internal, key=lambda c: c["expertise_score"], reverse=True)

    total = sum(c["expertise_score"] for c in all_sorted)
    threshold_reached = False
    cumulative = 0.0
    result = []
    for c in all_sorted:
        score = c["expertise_score"]
        share_pct = (score / total * 100) if total > 0 else 0
        cumulative += score
        cum_pct = (cumulative / total * 100) if total > 0 else 0
        in_bus = not threshold_reached
        if cum_pct >= 80:
            threshold_reached = True
        result.append({**c, "_share_pct": share_pct, "_cum_pct": cum_pct, "_in_bus": in_bus})
    for c in external:
        result.append({**c, "_share_pct": 0.0, "_cum_pct": 0.0, "_in_bus": False})
    return result


async def inspect_developer(graph: KnowledgeGraph, username: str) -> None:
    """Drill-down: show all modules a developer contributes to with bus-factor breakdown."""
    hdr(f"DEVELOPER DRILL-DOWN: {username}", ch="=")

    dev = await graph.get_developer(username)
    if dev is None:
        note(f"Developer '{username}' not found in knowledge graph.", indent=2)
        note("Tip: run the pipeline first, or check username spelling.", indent=2)
        return

    note(f"Name:  {dev.get('name') or dev.get('developer_identity') or '-'}", indent=2)
    ext_flag = "  [upstream/external]" if dev.get("external") else ""
    demo_flag = "  [demo]" if dev.get("demo") else ""
    note(f"Type:  {'external' if dev.get('external') else 'internal'}{ext_flag}{demo_flag}", indent=2)

    modules = await graph.get_developer_modules(username)
    if not modules:
        blank()
        note("No module contributions recorded for this developer.", indent=2)
        return

    blank()
    note(f"Contributes to {len(modules)} module(s):", indent=2)
    blank()

    for contrib in modules:
        path = contrib["module_path"]
        dev_score = contrib["expertise_score"]
        dev_commits = contrib.get("commit_count", 0)

        # Get all contributors to this module for bus-factor context
        all_contribs = await graph.get_module_contributors(path)
        breakdown = _bus_factor_breakdown(all_contribs)

        total_internal = sum(
            c["expertise_score"] for c in all_contribs if not c.get("external", False)
        )
        bus_factor = sum(1 for c in breakdown if c.get("_in_bus", False))

        dev_share = (dev_score / total_internal * 100) if total_internal > 0 else 0

        # Find this developer's rank among internal contributors
        internal_sorted = sorted(
            [c for c in all_contribs if not c.get("external", False)],
            key=lambda c: c["expertise_score"],
            reverse=True,
        )
        rank = next(
            (i + 1 for i, c in enumerate(internal_sorted) if c["developer_username"] == username),
            None,
        )
        rank_str = f"  rank #{rank} of {len(internal_sorted)} internal" if rank else ""

        bus_note = "  [IN 80% THRESHOLD]" if any(
            c["developer_username"] == username and c.get("_in_bus")
            for c in breakdown
        ) else ""

        sub(f"{path}")
        row("expertise_score:", f"{dev_score:.3f}  ({dev_share:.1f}% of module total){rank_str}")
        row("commits:", str(dev_commits))
        row("bus_factor:", f"{bus_factor}  (contributors covering ≥80% of expertise){bus_note}")

        # Show full breakdown for this module
        note("  All contributors (sorted by expertise):", indent=4)
        bar_width = 20
        for c in breakdown:
            u = c["developer_username"]
            sc = c["expertise_score"]
            sh = c.get("_share_pct", 0)
            cm = c.get("_cum_pct", 0)
            in_bus = c.get("_in_bus", False)
            ext = " [ext]" if c.get("external") else ""
            is_you = " [you]" if u == username else ""
            threshold_marker = " |80%|" if not c.get("external") and abs(cm - 100) < 0.01 and in_bus else ""
            bar = "█" * int(sh / 100 * bar_width) + "░" * (bar_width - int(sh / 100 * bar_width))
            bus_marker = "*" if in_bus else " "
            row(
                f"  {bus_marker} {u}{ext}",
                f"[{bar}] {sh:5.1f}%  cum={cm:5.1f}%  score={sc:.3f}{threshold_marker}{is_you}",
                indent=8,
            )
        blank()

    note("Legend: * = counts toward bus-factor (covering first 80% of expertise)", indent=2)
    note("bus_factor = how many * contributors this module depends on.", indent=2)


async def inspect_busfactor(graph: KnowledgeGraph) -> None:
    """Overview: all modules ranked by bus-factor with per-contributor breakdown."""
    hdr("BUS FACTOR OVERVIEW - ALL MODULES", ch="=")
    note("bus_factor = min contributors whose combined expertise covers 80% of commits.", indent=2)
    note("Lower = more concentrated. * marks contributors in the threshold.", indent=2)

    all_modules = await graph.modules.find({}, {"_id": 0}).sort("bus_factor", 1).to_list(None)
    if not all_modules:
        note("No modules tracked yet - run the pipeline first.", indent=2)
        return

    blank()
    bar_width = 18
    for m in all_modules:
        path = m["path"]
        bus = m.get("bus_factor", 0)

        all_contribs = await graph.get_module_contributors(path)
        breakdown = _bus_factor_breakdown(all_contribs)

        concentration = "!" if bus <= 1 else " "
        sub(f"{concentration} {path}  (bus_factor={bus})")

        if not breakdown:
            note("(no contribution data)", indent=6)
            continue

        for c in breakdown:
            u = c["developer_username"]
            sh = c.get("_share_pct", 0)
            cm = c.get("_cum_pct", 0)
            sc = c["expertise_score"]
            in_bus = c.get("_in_bus", False)
            ext = " [ext]" if c.get("external") else ""
            bar = "█" * int(sh / 100 * bar_width) + "░" * (bar_width - int(sh / 100 * bar_width))
            bus_marker = "*" if in_bus else " "
            row(
                f"  {bus_marker} {u}{ext}",
                f"[{bar}] {sh:5.1f}%  cum={cm:5.1f}%  score={sc:.3f}",
                indent=6,
            )

    blank()
    note("Legend: * = counts toward 80% threshold  ! = concentrated (bus_factor ≤ 1)", indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def rescore_graph(graph: KnowledgeGraph) -> None:
    """Recompute MEASUREMENTS (bus_factor) from current graph data.

    Per PROJECT_IDEA: there are no scalar risk scores. This function refreshes
    bus_factor counts (a measurement) - qualitative findings are produced only
    by running the full pipeline (investigators + analyst).
    """
    from graph.models import ModuleNode
    from risk.forecasting import compute_bus_factor

    hdr("RECOMPUTING BUS_FACTOR MEASUREMENTS FROM GRAPH DATA", ch="=")
    note("bus_factor is a count of internal committers covering 80% of commits.", indent=2)
    note("No scoring or aggregation here - run the full pipeline to refresh findings.", indent=2)

    all_modules = await graph.modules.find({}, {"_id": 0}).to_list(None)
    if not all_modules:
        note("No modules tracked yet -- run the pipeline first.", indent=2)
        return

    module_fields = set(ModuleNode.model_fields.keys())

    results = []
    for module in all_modules:
        path = module["path"]
        all_contribs = await graph.get_module_contributors(path)

        internal_committers = [
            c for c in all_contribs
            if not c.get("external", False) and c.get("commit_count", 0) > 0
        ]
        external_committers = [c for c in all_contribs if c.get("external", False)]
        bus_factor = compute_bus_factor(internal_committers)

        try:
            module_data = {k: v for k, v in module.items() if k in module_fields}
            module_data["bus_factor"] = bus_factor
            await graph.upsert_module(ModuleNode(**module_data))
        except Exception as exc:
            note(f"[ERROR] Failed to persist {path}: {exc}", indent=4)

        results.append({
            "path": path,
            "bus": bus_factor,
            "internal": len(internal_committers),
            "external": len(external_committers),
        })

    sub(f"Results ({len(results)} modules) - sorted by concentration (lowest bus_factor first)")
    for r in sorted(results, key=lambda x: x["bus"]):
        ext_str = f"  dark_knowledge: {r['external']} upstream authors" if r["external"] > 0 else ""
        row(
            r["path"],
            f"bus={r['bus']}  internal={r['internal']}  external={r['external']}{ext_str}",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mycelium data inspector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python checks/show.py                        # full report\n"
            "  python checks/show.py --gitlab               # GitLab only\n"
            "  python checks/show.py --graph                # MongoDB graph only\n"
            "  python checks/show.py --busfactor            # bus-factor breakdown for all modules\n"
            "  python checks/show.py --dev jsmith           # drill-down for a specific developer\n"
            "  python checks/show.py --rescore              # recompute bus_factor from graph data\n"
            "  python checks/show.py --commits 50           # show last 50 commits\n"
        ),
    )
    parser.add_argument("--gitlab", action="store_true", help="Show GitLab data only")
    parser.add_argument("--graph", action="store_true", help="Show knowledge graph only")
    parser.add_argument("--rescore", action="store_true", help="Recompute bus_factor measurements from current graph data")
    parser.add_argument("--busfactor", action="store_true", help="Show bus-factor breakdown for every module")
    parser.add_argument("--dev", metavar="USERNAME", help="Drill-down: show bus-factor impact for a specific developer")
    parser.add_argument("--commits", type=int, default=20, help="Number of commits to display (default 20)")
    args = parser.parse_args()

    explicit = args.gitlab or args.graph or args.rescore or args.busfactor or bool(args.dev)
    show_gitlab = args.gitlab or not explicit
    show_graph = args.graph or not explicit
    show_rescore = args.rescore
    show_busfactor = args.busfactor
    dev_username = args.dev

    hdr("MYCELIUM DATA INSPECTOR", ch="=")
    note("Read-only diagnostic. No agent logic runs.", indent=2)

    if show_gitlab:
        try:
            client = GitLabClient()
            inspect_gitlab(client, commit_limit=args.commits)
        except Exception as exc:
            note(f"[ERROR] GitLab connection failed: {exc}", indent=2)

    needs_graph = show_graph or show_rescore or show_busfactor or bool(dev_username)
    if needs_graph:
        try:
            graph = KnowledgeGraph()
            if show_graph:
                asyncio.run(inspect_graph(graph))
            if show_rescore:
                asyncio.run(rescore_graph(graph))
            if show_busfactor:
                asyncio.run(inspect_busfactor(graph))
            if dev_username:
                asyncio.run(inspect_developer(graph, dev_username))
            graph.close()
        except Exception as exc:
            note(f"[ERROR] MongoDB connection failed: {exc}", indent=2)

    blank()
    print("=" * W)
    note("Done.", indent=2)
    blank()


if __name__ == "__main__":
    main()
