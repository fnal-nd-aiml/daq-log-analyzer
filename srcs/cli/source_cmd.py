"""
File: source_cmd.py
Purpose: Sync-source command implementation.
Category: Utility
Author: artdaq team
Depends: client, rich
Exports: run_sync_source, DEFAULT_API_URL
Complexity: Low | Lines: 101
"""

import asyncio
import os
from rich.console import Console
from rich.table import Table
from srcs.api.client import AgentClient

console = Console()
DEFAULT_API_URL = "http://localhost:8000"


def _get_api_url(api_url: str | None = None) -> str:
    return api_url or os.environ.get("ARTDAQ_API_URL", DEFAULT_API_URL)


def run_sync_source(
    config_path: object = None, verbose: bool = False, status_only: bool = False, api_url: str | None = None
) -> None:
    url = _get_api_url(api_url)
    if status_only:
        asyncio.run(_show_status(url))
    else:
        asyncio.run(_run_sync(url, verbose))


async def _show_status(api_url: str) -> None:
    try:
        async with AgentClient(api_url) as client:
            data = await client.get_source_status()
    except Exception as e:
        console.print(f"[red]Failed to get source status: {e}[/red]")
        return
    console.print("[bold]Repository Status[/bold]")
    console.print()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Repository")
    table.add_column("Status")
    table.add_column("Branch")
    table.add_column("Commit")
    table.add_column("Date")
    for repo in data.get("repositories", []):
        name = repo.get("name", "?")
        status = repo.get("status", "unknown")
        branch = repo.get("branch") or "-"
        commit = repo.get("commit") or "-"
        commit_date = repo.get("commit_date") or "-"
        is_dirty = repo.get("is_dirty", False)
        if status == "cloned":
            dirty_marker = " [yellow]*[/yellow]" if is_dirty else ""
            status_display = f"[green]cloned[/green]{dirty_marker}"
            date_display = commit_date[:10] if len(commit_date) >= 10 else commit_date
        elif status == "not_cloned":
            status_display = "[dim]not cloned[/dim]"
            date_display = "-"
        else:
            status_display = f"[yellow]{status}[/yellow]"
            date_display = "-"
        table.add_row(name, status_display, branch, commit, date_display)
    console.print(table)
    console.print()
    repos_path = data.get("repos_path", "")
    if repos_path:
        console.print(f"[dim]Repos path: {repos_path}[/dim]")


async def _run_sync(api_url: str, verbose: bool) -> None:
    console.print("[bold]Syncing source repositories...[/bold]")
    console.print()
    try:
        async with AgentClient(api_url) as client:
            data = await client.sync_source_repos()
    except Exception as e:
        console.print(f"[red]Failed to sync repositories: {e}[/red]")
        return
    success_count = data.get("success_count", 0)
    failure_count = data.get("failure_count", 0)
    for result in data.get("results", []):
        repo_name = result.get("repo_name", "?")
        success = result.get("success", False)
        action = result.get("action", "unknown")
        message = result.get("message", "")
        if success:
            if action == "cloned":
                icon = "[green]✓[/green]"
                action_display = "[green]cloned[/green]"
            elif action == "updated":
                icon = "[green]✓[/green]"
                action_display = "[blue]updated[/blue]"
            else:
                icon = "[dim]○[/dim]"
                action_display = f"[dim]{action}[/dim]"
            console.print(f"  {icon} {repo_name} ({action_display})")
            if verbose and result.get("path"):
                console.print(f"      [dim]path: {result['path']}[/dim]")
        else:
            console.print(f"  [red]✗[/red] {repo_name}")
            console.print(f"      [red]{message}[/red]")
    console.print()
    if failure_count == 0:
        console.print(f"[green]Successfully synced {success_count} repositories[/green]")
    else:
        console.print(f"[yellow]Synced {success_count} repositories, {failure_count} failed[/yellow]")
