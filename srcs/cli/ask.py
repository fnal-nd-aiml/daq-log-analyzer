"""
File: ask.py
Purpose: CLI ask command implementation.
Category: Utility
Author: artdaq team
Depends: client, logs, question, rich
Exports: display_response, run_ask, QUESTION_TYPE_COLORS, DEFAULT_API_URL
Complexity: Medium | Lines: 138
"""

import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from srcs.api.client import AgentClient
from srcs.models.logs import Log
from srcs.models.question import PanelResponse, QuestionType
QUESTION_TYPE_COLORS = {QuestionType.HOW_TO: 'green', QuestionType.WHY: 'blue', QuestionType.WHAT_IS: 'cyan', QuestionType.TROUBLESHOOT: 'yellow', QuestionType.COMPARE: 'magenta', QuestionType.BEST_PRACTICE: 'white'}
DEFAULT_API_URL = 'http://localhost:8000'

def _get_api_url(api_url: str | None=None) -> str:
    return api_url or os.environ.get('ARTDAQ_API_URL', DEFAULT_API_URL)

def display_response(console: Console, response: PanelResponse, verbose: bool=False) -> None:
    if response.confidence >= 0.7:
        color = 'green'
        confidence_text = 'High confidence'
    elif response.confidence >= 0.5:
        color = 'yellow'
        confidence_text = 'Moderate confidence'
    else:
        color = 'red'
        confidence_text = 'Low confidence'
    answer_text = Text()
    answer_text.append(response.answer)
    console.print(Panel(answer_text, title=f'[bold {color}]Answer ({confidence_text}: {response.confidence:.0%})[/bold {color}]', border_style=color))
    if response.key_points:
        console.print('\n[bold]Key Points:[/bold]')
        for point in response.key_points:
            console.print(f'  [cyan]•[/cyan] {point}')
    if response.caveats:
        console.print('\n[bold yellow]Caveats:[/bold yellow]')
        for caveat in response.caveats:
            console.print(f'  [yellow]⚠[/yellow] {caveat}')
    if verbose:
        if response.contributions_summary:
            console.print('''
[bold]Contributions by Persona:[/bold]''')
            table = Table(show_header=True, header_style='bold')
            table.add_column('Persona', style='cyan')
            table.add_column('Summary')
            for persona, summary in response.contributions_summary.items():
                table.add_row(persona, summary[:100] + '...' if len(summary) > 100 else summary)
            console.print(table)
        if response.dissenting_views:
            console.print('''
[bold red]Dissenting Views:[/bold red]''')
            for view in response.dissenting_views:
                console.print(f'  [red]•[/red] {view}')
        if response.sources:
            console.print('\n[bold]Sources:[/bold]')
            for source in response.sources[:5]:
                console.print(f'  [dim]•[/dim] {source}')
        if response.citations:
            console.print('\n[bold]Citations:[/bold]')
            for citation in response.citations[:5]:
                cit_type = citation.get('type', 'unknown')
                reference = citation.get('reference', '')
                console.print(f'  [dim][{cit_type}][/dim] {reference}')

async def run_ask(question: str, log_file: Path | None=None, verbose: bool=False, config_file: Path | None=None, api_url: str | None=None) -> None:
    console = Console()
    url = _get_api_url(api_url)
    console.print(f'\n[bold]Question:[/bold] {question}\n')
    related_logs: list[Log] = []
    if log_file and log_file.exists():
        console.print(f'[dim]Reading logs from {log_file}...[/dim]')
        related_logs = _parse_log_file(log_file)
        if related_logs:
            console.print(f'[dim]Found {len(related_logs)} log entries[/dim]\n')
    with Progress(SpinnerColumn(), TextColumn('[progress.description]{task.description}'), console=console, transient=not verbose) as progress:
        task = progress.add_task('Consulting the panel of experts...', total=None)
        try:
            async with AgentClient(url) as client:
                session = await client.create_session()
                sid = session['session_id']
                try:
                    if related_logs:
                        log_content = '\n'.join((log.raw_line for log in related_logs if log.raw_line))
                        if log_content:
                            await client.parse_logs(sid, log_content)
                    result = await client.ask_experts(sid, question)
                finally:
                    try:
                        await client.delete_session(sid)
                    except Exception:
                        pass
        except Exception as e:
            console.print(f'[red]Error: {e}[/red]')
            return
        progress.update(task, description='Done!', completed=True)
    response_data = result.get('result', result)
    response = PanelResponse(question_id=response_data.get('question_id', '?'), answer=response_data.get('answer', 'No answer received'), confidence=response_data.get('confidence', 0.0), key_points=response_data.get('key_points', []), caveats=response_data.get('caveats', []), contributions_summary=response_data.get('contributions_summary', {}), dissenting_views=response_data.get('dissenting_views', []), sources=response_data.get('sources', []), citations=response_data.get('citations', []))
    console.print()
    display_response(console, response, verbose)
    console.print(f'\n[dim]Question ID: {response.question_id}[/dim]')

def _parse_log_file(log_file: Path, max_lines: int=100) -> list[Log]:
    logs: list[Log] = []
    try:
        with open(log_file, 'r') as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                log = _parse_artdaq_log_line(line)
                if log:
                    logs.append(log)
    except Exception:
        pass
    return logs

def _parse_artdaq_log_line(line: str) -> Log | None:
    import re
    from datetime import datetime
    pattern = '^(\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}\\.\\d+)\\s+(\\w+)\\s+\\[([^\\]]+)\\]\\s*(.*)'
    match = re.match(pattern, line)
    if match:
        timestamp_str, level, component_func, message = match.groups()
        try:
            timestamp = datetime.strptime(timestamp_str[:23], '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            timestamp = datetime.now()
        if ':' in component_func:
            component, function = component_func.split(':', 1)
        else:
            component = component_func
            function = None
        return Log(timestamp=timestamp, level=level, component=component, function=function, message=message, raw_line=line)
    if 'ERROR' in line or 'WARNING' in line or 'INFO' in line:
        level = 'ERROR' if 'ERROR' in line else 'WARNING' if 'WARNING' in line else 'INFO'
        return Log(timestamp=datetime.now(), level=level, component='unknown', message=line, raw_line=line)
    return None