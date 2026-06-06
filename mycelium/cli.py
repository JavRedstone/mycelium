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
Mycelium CLI - interact with the running Continuity Engine from the terminal.

Usage (from the mycelium/ directory with .venv active):
    python -m cli <command> [options]
    python cli.py <command> [options]

Examples:
    python -m cli init
    python -m cli run --watch
    python -m cli status
    python -m cli onboard marco.torres
    python -m cli inspect module scripts
    python -m cli inspect developer priya.sharma
    python -m cli demo seed team
    python -m cli demo clear
    python -m cli replay
    python -m cli replay --run-id <uuid>
"""
from __future__ import annotations

import json
import sys
import time
from typing import Optional

import click
import httpx
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_URL = "http://localhost:8000"


def _client(url: str) -> httpx.Client:
    return httpx.Client(base_url=url, timeout=30)


def _get(url: str, path: str) -> dict:
    try:
        r = httpx.get(f"{url}{path}", timeout=20)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        console.print(f"[bold red]Cannot connect to Mycelium at {url}[/bold red]")
        console.print("Is the server running? Start it with: [cyan]uvicorn main:app --reload[/cyan]")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP {e.response.status_code}:[/red] {e.response.text[:200]}")
        sys.exit(1)


def _post(url: str, path: str, json_body: dict | None = None) -> dict:
    try:
        r = httpx.post(f"{url}{path}", json=json_body, timeout=60)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        console.print(f"[bold red]Cannot connect to Mycelium at {url}[/bold red]")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP {e.response.status_code}:[/red] {e.response.text[:200]}")
        sys.exit(1)


def _delete(url: str, path: str) -> dict:
    try:
        r = httpx.delete(f"{url}{path}", timeout=20)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        console.print(f"[bold red]Cannot connect to Mycelium at {url}[/bold red]")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP {e.response.status_code}:[/red] {e.response.text[:200]}")
        sys.exit(1)


def _time_ago(ts: float | str | None) -> str:
    if ts is None:
        return "-"
    try:
        if isinstance(ts, str):
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            ms = (datetime.now(timezone.utc) - dt).total_seconds() * 1000
        else:
            ms = (time.time() - ts) * 1000
        seconds = ms / 1000
        if seconds < 60:
            return f"{int(seconds)}s ago"
        if seconds < 3600:
            return f"{int(seconds / 60)}m ago"
        if seconds < 86400:
            return f"{int(seconds / 3600)}h ago"
        days = int(seconds / 86400)
        if days < 30:
            return f"{days}d ago"
        months = round(days / 30)
        return f"{months}mo ago"
    except Exception:
        return str(ts)[:10]


def _event_line(event: dict) -> Text:
    """Format a single activity event as a Rich Text object."""
    t = event.get("type", "")
    stage = event.get("stage_id", "")
    ts = Text()

    if t == "run_start":
        ts.append("▶ Run started", style="bold green")
        ts.append(f"  {event.get('run_id', '')[:8]}", style="dim")
    elif t == "run_end":
        status = event.get("status", "")
        color = "green" if status == "success" else "red" if status == "failed" else "yellow"
        ts.append(f"■ Run {status}", style=f"bold {color}")
    elif t == "stage_start":
        ts.append(f"  ┌ {event.get('label', stage)}", style="bold blue")
    elif t == "stage_end":
        dur = event.get("duration_ms", 0)
        status = event.get("status", "")
        color = "green" if status == "success" else "red"
        ts.append(f"  └ {event.get('label', stage)} ", style=color)
        ts.append(f"({dur}ms)", style="dim")
    elif t == "agent_text":
        ts.append(f"    {event.get('text', '')}", style="white")
    elif t == "tool_call":
        ts.append(f"    → tool:", style="cyan")
        ts.append(f" {event.get('tool', '')}", style="bold cyan")
    elif t == "tool_response":
        result = str(event.get("result", ""))[:80]
        ts.append(f"    ← {result}", style="dim")
    elif t == "subagent_spawn":
        kind = event.get("kind", "")
        subject = event.get("subject", "")
        ts.append(f"    ⟳ {kind} investigator:", style="magenta")
        ts.append(f" {subject}", style="bold")
    elif t == "subagent_result":
        subject = event.get("subject", "")
        ts.append(f"    ✓ {subject}", style="green")
        summary = str(event.get("summary", ""))[:100]
        if summary:
            ts.append(f" - {summary}", style="dim")
    elif t == "finding":
        concern = event.get("concern_type", "")
        subject = event.get("subject", "")
        ts.append(f"    ⚑ {concern}", style="bold yellow")
        ts.append(f" [{subject}]", style="yellow")
    elif t == "action_planned":
        kind = event.get("kind", "")
        title = event.get("title", "")
        ts.append(f"    ✦ {kind}:", style="bold green")
        ts.append(f" {title}", style="green")
    else:
        raw = json.dumps({k: v for k, v in event.items() if k not in ("ts",)})
        ts.append(f"    {raw[:120]}", style="dim")
    return ts


# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------

@click.group()
@click.option("--url", default=DEFAULT_URL, envvar="MYCELIUM_URL", help="Mycelium server URL", show_default=True)
@click.pass_context
def cli(ctx: click.Context, url: str) -> None:
    """Mycelium - Engineering Continuity Engine CLI"""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url.rstrip("/")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Check server connectivity and print runtime configuration."""
    url = ctx.obj["url"]

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as p:
        p.add_task("Connecting to Mycelium…")
        health = _get(url, "/health")
        config = _get(url, "/config")

    console.print(Panel.fit(
        f"[bold green]✓ Connected[/bold green]  {url}",
        border_style="green",
    ))

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("Key", style="dim")
    t.add_column("Value")
    for k, v in config.items():
        t.add_row(k, str(v))
    console.print(t)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--watch", is_flag=True, help="Stream activity events while the pipeline runs")
@click.pass_context
def run(ctx: click.Context, watch: bool) -> None:
    """Trigger a pipeline run. Use --watch to stream live activity."""
    url = ctx.obj["url"]

    if not watch:
        _post(url, "/pipeline/run")
        console.print("[bold green]✓ Pipeline run triggered.[/bold green] Use [cyan]--watch[/cyan] to stream events.")
        return

    # Trigger run first
    try:
        httpx.post(f"{url}/pipeline/run", timeout=10)
    except Exception:
        pass  # server might return immediately; connect to stream regardless

    console.print("[dim]Connecting to activity stream…[/dim]")
    console.print()

    with httpx.stream("GET", f"{url}/pipeline/activity/stream", timeout=None) as stream:
        for line in stream.iter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            console.print(_event_line(event))
            if event.get("type") == "run_end":
                status = event.get("status", "")
                console.print()
                if status == "success":
                    console.print("[bold green]✓ Run completed successfully.[/bold green]")
                elif status == "failed":
                    console.print("[bold red]✗ Run failed.[/bold red]")
                else:
                    console.print(f"[yellow]Run ended: {status}[/yellow]")
                break


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current knowledge graph and pipeline state."""
    url = ctx.obj["url"]

    snap = _get(url, "/snapshot")
    history = _get(url, "/pipeline/history")
    demo_status = _get(url, "/graph/demo")

    # --- Graph summary ---
    devs = snap.get("developers", [])
    mods = snap.get("concentrated_modules", [])
    findings = snap.get("recent_findings", [])

    console.print()
    console.print("[bold]Knowledge Graph[/bold]", style="blue")
    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    summary.add_column("", style="dim")
    summary.add_column("")
    summary.add_row("Developers", str(len(devs)))
    summary.add_row("Concentrated modules", str(len(mods)))
    summary.add_row("Recent findings", str(len(findings)))
    summary.add_row("Demo data present", "yes" if demo_status.get("has_demo") else "no")
    console.print(summary)

    # --- Concentrated modules ---
    if mods:
        console.print("[bold]High-attention modules[/bold]", style="yellow")
        mt = Table(box=box.SIMPLE, padding=(0, 2))
        mt.add_column("Module", style="bold")
        mt.add_column("Bus factor")
        mt.add_column("Owners")
        for m in mods[:10]:
            owners = ", ".join(m.get("owners", [])) or "-"
            bf = str(m.get("bus_factor", "?"))
            color = "red" if m.get("bus_factor", 1) <= 1 else "yellow"
            mt.add_row(m.get("path", "?") + "/", Text(bf, style=color), owners)
        console.print(mt)

    # --- Pipeline history ---
    runs = history if isinstance(history, list) else history.get("runs", [])
    if runs:
        console.print("[bold]Recent pipeline runs[/bold]", style="blue")
        rt = Table(box=box.SIMPLE, padding=(0, 2))
        rt.add_column("Run ID", style="dim")
        rt.add_column("Started")
        rt.add_column("Status")
        for r in runs[:5]:
            status_val = r.get("status", "?")
            color = "green" if status_val == "success" else "red" if status_val == "failed" else "yellow"
            rt.add_row(
                r.get("run_id", "")[:8] + "…",
                _time_ago(r.get("started_at")),
                Text(status_val, style=color),
            )
        console.print(rt)
    else:
        console.print("[dim]No pipeline runs yet. Use [cyan]mycelium run[/cyan] to start one.[/dim]")


# ---------------------------------------------------------------------------
# onboard / offboard
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("username")
@click.pass_context
def onboard(ctx: click.Context, username: str) -> None:
    """Generate an onboarding pack for USERNAME (creates a GitLab issue)."""
    url = ctx.obj["url"]
    with Progress(SpinnerColumn(), TextColumn(f"Generating onboarding pack for {username}…"), transient=True) as p:
        p.add_task("")
        result = _post(url, f"/onboard/{username}")
    if result.get("iid"):
        console.print(f"[bold green]✓ Onboarding issue created:[/bold green] {result.get('web_url', f'#{result[\"iid\"]}')}")
    else:
        console.print_json(json.dumps(result))


@cli.command()
@click.argument("username")
@click.pass_context
def offboard(ctx: click.Context, username: str) -> None:
    """Generate an offboarding/handoff artifact for USERNAME (creates a GitLab issue)."""
    url = ctx.obj["url"]
    with Progress(SpinnerColumn(), TextColumn(f"Generating offboarding artifact for {username}…"), transient=True) as p:
        p.add_task("")
        result = _post(url, f"/offboard/{username}")
    if result.get("iid"):
        console.print(f"[bold green]✓ Offboarding issue created:[/bold green] {result.get('web_url', f'#{result[\"iid\"]}')}")
    else:
        console.print_json(json.dumps(result))


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------

@cli.group()
def inspect() -> None:
    """Inspect knowledge graph entities."""


@inspect.command("module")
@click.argument("path")
@click.pass_context
def inspect_module(ctx: click.Context, path: str) -> None:
    """Show ownership and contributor breakdown for a module directory."""
    url = ctx.obj["url"]
    data = _get(url, "/graph")
    modules = data.get("modules", [])
    mod = next((m for m in modules if m.get("path") == path or m.get("path") == path.rstrip("/")), None)

    if mod is None:
        console.print(f"[red]Module '{path}' not found in knowledge graph.[/red]")
        available = [m.get("path") for m in modules]
        if available:
            console.print(f"Available: {', '.join(available)}")
        sys.exit(1)

    console.print()
    console.print(Panel.fit(
        f"[bold]{mod['path']}/[/bold]  bus factor: [{'red' if mod.get('bus_factor', 1) <= 1 else 'green'}]{mod.get('bus_factor', '?')}[/]  language: {mod.get('language', '?')}",
        border_style="blue",
    ))

    contribs = mod.get("contributors", [])
    internal = [c for c in contribs if not c.get("external")]
    external = [c for c in contribs if c.get("external")]

    if internal:
        console.print("[bold]Team contributors[/bold]")
        t = Table(box=box.SIMPLE, padding=(0, 2))
        t.add_column("Username")
        t.add_column("Expertise", justify="right")
        t.add_column("Commits", justify="right")
        t.add_column("Lines", justify="right")
        t.add_column("Last contribution")
        for c in sorted(internal, key=lambda x: -x.get("expertise_score", 0)):
            score = c.get("expertise_score", 0)
            color = "red" if score > 0.8 and mod.get("bus_factor", 1) <= 1 else "white"
            t.add_row(
                c.get("developer_username", "?"),
                Text(f"{score:.0%}", style=color),
                str(c.get("commit_count", 0)),
                str(c.get("lines_changed", 0)),
                _time_ago(c.get("last_contribution_at")),
            )
        console.print(t)

    if external:
        console.print("[dim]Upstream authors (unreachable)[/dim]")
        for c in external[:5]:
            console.print(f"  [dim]{c.get('developer_username')}  {c.get('commit_count')} commits[/dim]")

    owners = mod.get("owners", [])
    if owners:
        console.print(f"\nCODEOWNERS: {', '.join(owners)}")
    else:
        console.print("\n[yellow]No CODEOWNERS entry for this module.[/yellow]")


@inspect.command("developer")
@click.argument("username")
@click.pass_context
def inspect_developer(ctx: click.Context, username: str) -> None:
    """Show expertise profile and module ownership for a developer."""
    url = ctx.obj["url"]
    data = _get(url, "/developers")
    devs = data.get("developers", [])
    dev = next((d for d in devs if d.get("username") == username), None)

    if dev is None:
        console.print(f"[red]Developer '{username}' not found.[/red]")
        sys.exit(1)

    console.print()
    name = dev.get("name", username)
    active = dev.get("active", False)
    demo = dev.get("demo", False)
    console.print(Panel.fit(
        f"[bold]{name}[/bold]  @{username}"
        + ("  [purple][demo][/purple]" if demo else "")
        + ("  [green][active][/green]" if active else "  [red][inactive][/red]"),
        border_style="blue",
    ))

    last_seen = dev.get("last_seen")
    if last_seen:
        console.print(f"Last seen: {_time_ago(last_seen)}")

    expertise = dev.get("expertise", {})
    if expertise:
        console.print("\n[bold]Module expertise[/bold]")
        t = Table(box=box.SIMPLE, padding=(0, 2))
        t.add_column("Module")
        t.add_column("Score", justify="right")
        t.add_column("Bar")
        for mod_path, score in sorted(expertise.items(), key=lambda x: -x[1]):
            bar_len = int(score * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            color = "red" if score > 0.8 else "yellow" if score > 0.5 else "dim"
            t.add_row(mod_path + "/", Text(f"{score:.0%}", style=color), Text(bar, style=color))
        console.print(t)
    else:
        console.print("[dim]No expertise data yet.[/dim]")


# ---------------------------------------------------------------------------
# demo
# ---------------------------------------------------------------------------

@cli.group()
def demo() -> None:
    """Manage demo/seed data."""


@demo.command("seed")
@click.argument("scenario", default="team", type=click.Choice(["team", "new_joiner", "fading", "sole_owner"]))
@click.pass_context
def demo_seed(ctx: click.Context, scenario: str) -> None:
    """Seed demo data. SCENARIO: team | new_joiner | fading | sole_owner"""
    url = ctx.obj["url"]
    with Progress(SpinnerColumn(), TextColumn(f"Seeding scenario: {scenario}…"), transient=True) as p:
        p.add_task("")
        result = _post(url, f"/demo/seed/{scenario}")
    console.print(f"[bold green]✓ Seeded:[/bold green] {result.get('seeded', scenario)}")
    console.print("[dim]Demo entries are marked with purple chips in the UI.[/dim]")


@demo.command("clear")
@click.pass_context
def demo_clear(ctx: click.Context) -> None:
    """Remove all demo-flagged entries from the knowledge graph."""
    url = ctx.obj["url"]
    result = _delete(url, "/graph/demo")
    devs = result.get("deleted_developers", 0)
    mods = result.get("deleted_modules", 0)
    contribs = result.get("deleted_contributions", 0)
    console.print(f"[bold green]✓ Cleared:[/bold green] {devs} developers, {mods} modules, {contribs} contributions")


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--run-id", default=None, help="Specific run ID to replay (default: latest)")
@click.option("--speed", default=1.0, help="Playback speed multiplier (e.g. 2.0 = 2× faster)", show_default=True)
@click.pass_context
def replay(ctx: click.Context, run_id: Optional[str], speed: float) -> None:
    """Replay stored activity events from a past pipeline run."""
    url = ctx.obj["url"]

    if run_id is None:
        history = _get(url, "/pipeline/history")
        runs = history if isinstance(history, list) else history.get("runs", [])
        if not runs:
            console.print("[red]No pipeline runs found.[/red]")
            sys.exit(1)
        run_id = runs[0].get("run_id")
        console.print(f"[dim]Replaying latest run: {run_id[:8]}…[/dim]")

    data = _get(url, f"/pipeline/{run_id}/events")
    events = data.get("events", [])

    if not events:
        console.print(f"[yellow]No stored events for run {run_id[:8]}. (Events are captured from runs started after this CLI was deployed.)[/yellow]")
        sys.exit(0)

    console.print(f"[bold]Replaying {len(events)} events[/bold]  run [dim]{run_id[:8]}[/dim]")
    console.print()

    prev_ts: float | None = None
    for event in events:
        ts = event.get("ts")
        if prev_ts is not None and ts is not None and speed > 0:
            gap = (ts - prev_ts) / speed
            if 0 < gap < 5:  # cap at 5s to avoid long waits
                time.sleep(gap)
        prev_ts = ts
        console.print(_event_line(event))

    console.print()
    console.print("[dim]- end of replay -[/dim]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli(obj={})
