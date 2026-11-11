"""
File: feedback.py
Purpose: Feedback command implementation.
Category: Utility
Author: artdaq team
Depends: client, rich
Exports: submit_feedback, list_recent_investigations, DEFAULT_API_URL
Complexity: Low | Lines: 56
"""

import logging
import os
from rich.console import Console
from srcs.api.client import AgentClient
logger = logging.getLogger(__name__)
console = Console()
DEFAULT_API_URL = 'http://localhost:8000'

def _get_api_url(api_url: str | None=None) -> str:
    return api_url or os.environ.get('ARTDAQ_API_URL', DEFAULT_API_URL)

async def submit_feedback(investigation_id: str, correct: bool | None, actual_cause: str | None, api_url: str | None=None) -> None:
    if correct is None:
        console.print('[red]Please specify --correct or --incorrect[/red]')
        return
    url = _get_api_url(api_url)
    try:
        async with AgentClient(url) as client:
            result = await client.submit_feedback(investigation_id, correct, actual_cause=actual_cause, feedback_source='cli')
        if correct:
            console.print('[green]Feedback recorded: Diagnosis was correct[/green]')
        else:
            console.print('[yellow]Feedback recorded: Diagnosis was incorrect[/yellow]')
            if actual_cause:
                console.print(f'[yellow]Actual cause: {actual_cause}[/yellow]')
        patterns_updated = result.get('patterns_updated', 0)
        patterns_created = result.get('patterns_created', 0)
        if patterns_updated:
            console.print(f'[dim]Patterns updated: {patterns_updated}[/dim]')
        if patterns_created:
            console.print(f'[dim]New patterns created: {patterns_created}[/dim]')
    except Exception as e:
        console.print(f'[red]Failed to submit feedback: {e}[/red]')

async def list_recent_investigations(limit: int=10, api_url: str | None=None) -> None:
    url = _get_api_url(api_url)
    try:
        async with AgentClient(url) as client:
            data = await client.list_investigations(limit=limit)
    except Exception as e:
        console.print(f'[red]Failed to retrieve investigations: {e}[/red]')
        return
    investigations = data.get('investigations', [])
    if not investigations:
        console.print('[dim]No investigations found[/dim]')
        return
    console.print(f'[bold]Recent Investigations ({len(investigations)}):[/bold]')
    for inv in investigations:
        outcome = inv.get('outcome', 'N/A')
        outcome_color = {'CONFIDENT': 'green', 'PROBABLE': 'yellow', 'UNCERTAIN': 'orange1', 'INSUFFICIENT': 'red', 'CONTRADICTORY': 'red'}.get(outcome, 'white')
        inv_id = inv.get('investigation_id', '?')
        root_cause = inv.get('root_cause', '')
        display_text = root_cause[:50] + '...' if root_cause and len(root_cause) > 50 else root_cause or 'N/A'
        console.print(f'  [{outcome_color}]{outcome:12}[/{outcome_color}] {inv_id} - {display_text}')
    console.print()
    console.print("[dim]Use 'artdaq-agent feedback <ID> --correct/--incorrect' to provide feedback[/dim]")