"""
Data check suite for Mycelium UI pages.

Hits every backend API endpoint used by the frontend, prints a structured
summary of what data is present, what is missing, and what each page/graph
will render given the current state.

Usage (run from the mycelium/ directory):
    python -m scripts.check_data
    python -m scripts.check_data --url http://localhost:8000
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx

# ── ANSI helpers ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
WHITE  = "\033[97m"
BLUE   = "\033[34m"
MAGENTA= "\033[35m"

def ok(s):    return f"{GREEN}✓{RESET} {s}"
def warn(s):  return f"{YELLOW}⚠{RESET}  {s}"
def err(s):   return f"{RED}✗{RESET} {s}"
def info(s):  return f"{CYAN}·{RESET} {s}"
def hdr(s):   return f"\n{BOLD}{WHITE}{s}{RESET}"
def dim(s):   return f"{DIM}{s}{RESET}"
def page_hdr(label, emoji=""):
    pad = 54 - len(label)
    bar = "─" * 54
    return f"\n{BOLD}{BLUE}┌{bar}┐{RESET}\n{BOLD}{BLUE}│{RESET}  {emoji}  {BOLD}{WHITE}{label}{RESET}{' ' * pad}{BOLD}{BLUE}│{RESET}\n{BOLD}{BLUE}└{bar}┘{RESET}"

def count_label(n: int, noun: str = "record") -> str:
    if n == 0:
        return f"{RED}0 {noun}s{RESET}"
    if n < 3:
        return f"{YELLOW}{n} {noun}{'s' if n != 1 else ''}{RESET}"
    return f"{GREEN}{n} {noun}{'s' if n != 1 else ''}{RESET}"

def fmt_date(s) -> str:
    if not s:
        return dim("-")
    try:
        # Handle Unix float timestamps (e.g. from pipeline runs)
        if isinstance(s, (int, float)):
            from datetime import timezone
            dt = datetime.fromtimestamp(float(s), tz=timezone.utc)
            s = dt.isoformat()
        else:
            s = str(s)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        delta = datetime.now(dt.tzinfo) - dt
        days = delta.days
        if days == 0:    label = "today"
        elif days == 1:  label = "yesterday"
        elif days < 30:  label = f"{days}d ago"
        elif days < 365: label = f"{days // 30}mo ago"
        else:            label = f"{days // 365}yr ago"
        return f"{s[:10]} ({label})"
    except Exception:
        return str(s)[:19]

# ── HTTP helpers ──────────────────────────────────────────────────────────────

async def get(client: httpx.AsyncClient, path: str) -> tuple[int, object]:
    try:
        r = await client.get(path, timeout=8)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text
    except httpx.ConnectError:
        return 0, "connection refused"
    except Exception as e:
        return 0, str(e)

# ── Section printers ──────────────────────────────────────────────────────────

def print_kv(key: str, value: str, indent: int = 4):
    print(f"{' ' * indent}{DIM}{key:<28}{RESET}{value}")


async def check_health(client):
    print(page_hdr("Backend health", "🔌"))
    status, data = await get(client, "/health")
    if status == 200:
        print(f"    {ok('Backend reachable')}  {dim('GET /health → 200')}")
    else:
        print(f"    {err(f'Backend unreachable (status={status})')}")
        print(f"\n    {RED}Cannot continue - start the backend first.{RESET}\n")
        sys.exit(1)


async def check_config(client):
    print(page_hdr("Configuration page", "⚙️"))
    status, data = await get(client, "/config")
    if status != 200 or not isinstance(data, dict):
        print(f"    {err(f'GET /config failed ({status})')}")
        return
    print(f"    {ok('GET /config')}")
    for k, v in data.items():
        print_kv(k, str(v))


async def check_repo(client):
    print(page_hdr("Repository page", "📁"))

    # /project
    status, data = await get(client, "/project")
    if status == 200 and isinstance(data, dict):
        print(f"    {ok('GET /project')}")
        print_kv("name",        data.get("name", "-"))
        print_kv("namespace",   data.get("namespace_name", "-"))
        print_kv("default_branch", data.get("default_branch", "-"))
        print_kv("is_fork",     str(data.get("is_fork", "-")))
        print_kv("created_at",  fmt_date(data.get("created_at")))
    else:
        print(f"    {warn(f'GET /project → {status} (GitLab may be unreachable)')}")

    # /graph (modules + contributors)
    status, gdata = await get(client, "/graph")
    if status != 200 or not isinstance(gdata, dict):
        print(f"    {err(f'GET /graph failed ({status})')}")
        return
    modules = gdata.get("modules", [])
    devs    = gdata.get("developers", [])
    print(f"    {ok('GET /graph')}")
    print(f"    {info(count_label(len(modules), 'module'))} · {count_label(len(devs), 'developer')}")
    for m in sorted(modules, key=lambda x: x.get("bus_factor", 0))[:8]:
        nc = len(m.get("contributors", []))
        bf = m.get("bus_factor", 0)
        bf_color = RED if bf <= 1 else (YELLOW if bf == 2 else GREEN)
        print(f"      {DIM}·{RESET} {m['path']:<20} bus={bf_color}{bf}{RESET}  {nc} contributor{'s' if nc != 1 else ''}")

    # /graph/demo
    status, ddata = await get(client, "/graph/demo")
    if status == 200 and isinstance(ddata, dict):
        has_demo = ddata.get("has_demo", False)
        tag = f"{MAGENTA}demo data present{RESET}" if has_demo else dim("no demo data")
        print(f"    {info(tag)}")


async def check_history(client):
    print(page_hdr("Repo History page", "📈"))

    # Check demo_mode from config (affects whether demo data reaches agents)
    _, cfg = await get(client, "/config")
    demo_mode = bool(cfg.get("demo_mode")) if isinstance(cfg, dict) else False
    if demo_mode:
        print(f"    {info(f'{MAGENTA}DEMO_MODE=true{RESET} - demo data visible to pipeline agents')}")
    else:
        print(f"    {dim('DEMO_MODE=false - demo data excluded from pipeline agents')}")

    # /developers
    status, data = await get(client, "/developers")
    devs = (data.get("developers", []) if isinstance(data, dict) else []) if status == 200 else []
    internal  = [d for d in devs if not d.get("external")]
    upstream  = [d for d in devs if d.get("external")]
    print(f"    {ok('GET /developers') if status == 200 else err(f'GET /developers → {status}')}")
    print(f"    {info(count_label(len(internal), 'internal dev'))}  ·  {count_label(len(upstream), 'upstream author')}")
    if internal:
        for d in sorted(internal, key=lambda x: x.get("last_seen") or "", reverse=True)[:5]:
            demo_tag = f" {MAGENTA}[demo]{RESET}" if d.get("demo") else ""
            print(f"      {DIM}·{RESET} {d.get('name','?'):<22} last_seen={fmt_date(d.get('last_seen'))}{demo_tag}")
    if upstream:
        print(f"    {DIM}  upstream:{RESET}")
        for d in upstream[:3]:
            demo_tag = f" {MAGENTA}[demo]{RESET}" if d.get("demo") else ""
            print(f"      {DIM}·{RESET} {d.get('name','?'):<22} last_seen={fmt_date(d.get('last_seen'))}{demo_tag}")

    # /settings/fork-date
    status, fdata = await get(client, "/settings/fork-date")
    if status == 200 and isinstance(fdata, dict):
        eff = fdata.get("effective")
        override = fdata.get("override")
        project_created = fdata.get("project_created_at")
        src = f"{MAGENTA}MongoDB override{RESET}" if override else (f"{CYAN}GitLab project.created_at{RESET}" if project_created else f"{RED}not set{RESET}")
        print(f"    {ok('GET /settings/fork-date')}")
        print_kv("effective",        fmt_date(eff) if eff else f"{RED}MISSING - fork line won't render{RESET}")
        print_kv("source",           src)
        if not eff:
            print(f"    {warn('No fork date → reference line will not appear on chart')}")
    else:
        print(f"    {err(f'GET /settings/fork-date → {status}')}")

    # /graph/contribution-history (fetched first so we can use it in Y-axis count below)
    hist_status, hdata = await get(client, "/graph/contribution-history")
    records = hdata if isinstance(hdata, list) else []

    # /graph (modules + contributors for Y axis)
    status, gdata = await get(client, "/graph")
    modules = (gdata.get("modules", []) if isinstance(gdata, dict) else []) if status == 200 else []
    SYNTHETIC = {"repository"}
    contributing = set()
    for m in modules:
        if m.get("path") in SYNTHETIC:
            continue
        for c in m.get("contributors", []):
            contributing.add(c.get("developer_username"))
    for r in records:  # also count history contributors
        contributing.add(r.get("developer_username"))
    devs_with_contribs = [d for d in devs if d.get("username") in contributing]
    print(f"    {ok('GET /graph') if status == 200 else err(f'GET /graph → {status}')}")
    n = len(devs_with_contribs)
    print(f"    {info(f'{GREEN}{n}{RESET} dev on Y axis')} after excluding synthetic 'repository' module")
    if len(devs_with_contribs) == 0:
        print(f"    {warn('No contributors matched - chart Y axis will be empty')}")

    print(f"    {ok('GET /graph/contribution-history') if hist_status == 200 else err(f'GET /graph/contribution-history → {hist_status}')}")
    if records:
        usernames  = {r.get("developer_username") for r in records}
        months     = sorted({r.get("year_month") for r in records if r.get("year_month")})
        demo_count = sum(1 for r in records if r.get("demo"))
        real_count = len(records) - demo_count
        print(f"    {info(count_label(len(records), 'monthly record'))} across {count_label(len(usernames), 'contributor')} · {len(months)} distinct months")
        if months:
            print_kv("date range",  f"{months[0]}  →  {months[-1]}")
        print_kv("demo records",  f"{MAGENTA}{demo_count}{RESET}" if demo_count else "0")
        print_kv("real records",  f"{GREEN}{real_count}{RESET}" if real_count else dim("0 (run pipeline to populate)"))
        if demo_count and not demo_mode:
            print(f"    {warn('Demo data present but DEMO_MODE=false - agents will NOT see these records')}")
        if demo_count and not real_count:
            print(f"    {warn('Only demo data - timeline shows seeded data, not real commits')}")
        elif not records:
            print(f"    {warn('No monthly history → chart will fall back to last-contribution dots')}")
    else:
        print(f"    {warn('Empty - chart falls back to per-module last-contribution dots (less informative)')}")
        print(f"    {dim('    Seed demo data or run the pipeline to populate.')}")


async def check_pipeline(client):
    print(page_hdr("Pipeline page", "▶️"))

    status, curr = await get(client, "/pipeline/current")
    run = (curr.get("run") if isinstance(curr, dict) else None) if status == 200 else None
    if run:
        state = run.get("status", "?")
        color = GREEN if state == "completed" else (YELLOW if state == "running" else RED)
        print(f"    {ok('GET /pipeline/current')}  →  {color}{state}{RESET}")
        print_kv("run_id",     run.get("run_id", "-")[:16])
        print_kv("started_at", fmt_date(run.get("started_at")))
        print_kv("stages",     str(len(run.get("stages", []))))
    else:
        print(f"    {info('GET /pipeline/current → no active/recent run')}")

    status, hist = await get(client, "/pipeline/history")
    runs = (hist.get("runs", []) if isinstance(hist, dict) else []) if status == 200 else []
    print(f"    {ok('GET /pipeline/history') if status == 200 else err(f'/pipeline/history → {status}')}")
    print(f"    {info(count_label(len(runs), 'historical run'))}")
    for r in runs[:3]:
        state = r.get("status", "?")
        color = GREEN if state == "completed" else (YELLOW if state == "running" else RED)
        print(f"      {DIM}·{RESET} {fmt_date(r.get('started_at'))}  {color}{state}{RESET}")


async def check_knowledge_graph(client):
    print(page_hdr("Knowledge Graph page", "🕸️"))

    status, data = await get(client, "/graph")
    if status != 200 or not isinstance(data, dict):
        print(f"    {err(f'GET /graph → {status}')}")
        return
    devs   = data.get("developers", [])
    up     = data.get("upstream_authors", [])
    mods   = data.get("modules", [])
    conc   = data.get("concentrated_modules", [])
    print(f"    {ok('GET /graph')}")
    print(f"    {info(count_label(len(devs), 'internal dev'))} · {count_label(len(up), 'upstream author')} · {count_label(len(mods), 'module')}")
    if conc:
        print(f"    {warn(f'{len(conc)} concentrated module(s) (bus_factor ≤ 1)')}")
        for m in conc[:3]:
            print(f"      {DIM}·{RESET} {m.get('path')}  bus={RED}{m.get('bus_factor', '?')}{RESET}")


async def check_activity_logs(client):
    print(page_hdr("Agent Activity + Logs", "💬"))

    status, data = await get(client, "/pipeline/activity")
    events = (data.get("events", []) if isinstance(data, dict) else []) if status == 200 else []
    print(f"    {ok('GET /pipeline/activity') if status == 200 else err(f'/pipeline/activity → {status}')}")
    print(f"    {info(count_label(len(events), 'buffered event'))}")
    if events:
        types = {}
        for e in events:
            t = e.get("type", "?")
            types[t] = types.get(t, 0) + 1
        for t, n in sorted(types.items()):
            print(f"      {DIM}·{RESET} {t:<30} {n}")

    # SSE streams (just check they exist, don't consume)
    print(f"    {info(dim('SSE streams: /pipeline/stream · /pipeline/activity/stream · /logs/stream'))}")


async def check_insights(client):
    print(page_hdr("Insights - Actions / Investigations / Timeline / Analytics", "🔍"))

    # /actions
    status, data = await get(client, "/actions?limit=500")
    actions = data if isinstance(data, list) else []
    print(f"    {ok('GET /actions') if status == 200 else err(f'/actions → {status}')}")
    print(f"    {info(count_label(len(actions), 'action'))}", end="")
    if actions:
        tools = {}
        for a in actions:
            t = a.get("tool", "?")
            tools[t] = tools.get(t, 0) + 1
        top = sorted(tools.items(), key=lambda x: -x[1])[:3]
        print(f"  {dim('top tools: ' + ', '.join(f'{t}×{n}' for t, n in top))}", end="")
    print()

    # /findings
    status, data = await get(client, "/findings?limit=500")
    findings = data if isinstance(data, list) else []
    print(f"    {ok('GET /findings') if status == 200 else err(f'/findings → {status}')}")
    print(f"    {info(count_label(len(findings), 'finding'))}")
    if findings:
        types = {}
        for f in findings:
            t = f.get("concern_type", "?")
            types[t] = types.get(t, 0) + 1
        for t, n in sorted(types.items(), key=lambda x: -x[1])[:5]:
            print(f"      {DIM}·{RESET} {t:<36} {n}")

    # /snapshot (used by analytics)
    status, data = await get(client, "/snapshot")
    if status == 200 and isinstance(data, dict):
        print(f"    {ok('GET /snapshot')}")
        print_kv("developers",          str(len(data.get("developers", []))))
        print_kv("concentrated_modules",str(len(data.get("concentrated_modules", []))))
        print_kv("recent_findings",     str(len(data.get("recent_findings", []))))
    else:
        print(f"    {warn(f'GET /snapshot → {status}')}")


async def summary(client):
    print(page_hdr("Summary - page render readiness", "📋"))
    print()

    checks = [
        ("Configuration",    "/config"),
        ("Repository",       "/project"),
        ("Knowledge Graph",  "/graph"),
        ("Pipeline",         "/pipeline/history"),
        ("Agent Activity",   "/pipeline/activity"),
        ("Actions",          "/actions"),
        ("Findings",         "/findings"),
        ("Repo History",     "/graph/contribution-history"),
        ("Fork date",        "/settings/fork-date"),
    ]

    for label, path in checks:
        status, data = await get(client, path)
        if status == 0:
            badge = f"{RED}OFFLINE{RESET}"
        elif status != 200:
            badge = f"{YELLOW}HTTP {status}{RESET}"
        else:
            # Check for empty-ness
            empty = False
            if isinstance(data, list) and len(data) == 0:
                empty = True
            elif isinstance(data, dict):
                # check common list keys
                for key in ("developers", "modules", "runs", "events", "actions"):
                    if key in data and len(data[key]) == 0:
                        empty = True
                        break
            badge = f"{YELLOW}EMPTY{RESET}" if empty else f"{GREEN}OK{RESET}"
        print(f"    {badge:<30}  {DIM}{path}{RESET}  {dim(label)}")

    print()


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    args = sys.argv[1:]
    base_url = "http://localhost:8000"
    for i, a in enumerate(args):
        if a in ("--url", "-u") and i + 1 < len(args):
            base_url = args[i + 1]
        elif a.startswith("http"):
            base_url = a

    print(f"\n{BOLD}{CYAN}Mycelium data check suite{RESET}  {DIM}→ {base_url}{RESET}")

    async with httpx.AsyncClient(base_url=base_url) as client:
        await check_health(client)
        await check_config(client)
        await check_repo(client)
        await check_history(client)
        await check_pipeline(client)
        await check_knowledge_graph(client)
        await check_activity_logs(client)
        await check_insights(client)
        await summary(client)


if __name__ == "__main__":
    asyncio.run(main())
