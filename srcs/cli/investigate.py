"""
File: investigate.py
Purpose: Investigate command implementation.
Category: Utility
Author: artdaq team
Depends: client, models, callbacks, investigation, log_parser, ...
Exports: run_investigation, DEFAULT_API_URL
Complexity: Medium | Lines: 329
"""

import logging
import os
import sys
from pathlib import Path
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from srcs.api.client import AgentClient
from srcs.models import InvestigationResult, Log
from srcs.models.callbacks import DataRetrievalEvent, LLMEvent, PhaseEvent
from srcs.models.log_parser import create_log_from_message, extract_error_and_context, parse_log_content, parse_log_file
from srcs.output import ConsoleRenderer, MarkdownFormatter
from .display import display_result
from .llm_display import LLMLoggingDisplay
from .verbose_display import VerboseDisplay

logger = logging.getLogger(__name__)
console = Console()
DEFAULT_API_URL = "http://localhost:8000"


def _get_api_url(api_url: str | None = None) -> str:
    return api_url or os.environ.get("ARTDAQ_API_URL", DEFAULT_API_URL)


def _load_output_defaults() -> dict:
    try:
        with open("config.yaml") as f:
            config = yaml.safe_load(f) or {}
        output_cfg = config.get("output", {})
        return {
            "verbose": output_cfg.get("verbose", False),
            "llm_logging": output_cfg.get("llm_logging", False),
            "full_output": output_cfg.get("full_output", False),
        }
    except Exception:
        return {"verbose": False, "llm_logging": False, "full_output": False}


async def run_investigation(
    log_file: Path | None,
    error_line: int | None,
    context_lines: int,
    config_file: Path | None,
    verbose: bool | None,
    message: str | None = None,
    llm_log: bool | None = None,
    llm_all: bool | None = None,
    content: str | None = None,
    additional_files: list[Path] | None = None,
    api_url: str | None = None,
) -> None:
    output_defaults = _load_output_defaults()
    effective_verbose = verbose if verbose is not None else output_defaults["verbose"]
    effective_llm_log = llm_log if llm_log is not None else output_defaults["llm_logging"]
    effective_llm_all = llm_all if llm_all is not None else output_defaults["full_output"]
    url = _get_api_url(api_url)
    if message is not None:
        error = create_log_from_message(message)
        context: list[Log] = []
        log_content = message
    elif content is not None:
        with console.status("[bold blue]Parsing log content..."):
            try:
                logs = parse_log_content(content)
            except Exception as e:
                console.print(f"[red]Failed to parse log content: {e}[/red]")
                return
            if not logs:
                console.print("[red]No parseable log entries found in content[/red]")
                return
            error, context = extract_error_and_context(logs, error_line, context_lines)
        log_content = content
    else:
        assert log_file is not None
        with console.status("[bold blue]Parsing logs..."):
            try:
                logs = parse_log_file(log_file)
            except Exception as e:
                console.print(f"[red]Failed to parse log file: {e}[/red]")
                return
            if not logs:
                console.print("[red]No logs found in file[/red]")
                return
            error, context = extract_error_and_context(logs, error_line, context_lines)
        log_content = log_file.read_text(encoding="utf-8", errors="replace")
    console.print(
        Panel(
            f"[bold]Error:[/bold] {error.message[:200]}{('...' if len(error.message) > 200 else '')}\n[bold]Component:[/bold] {error.component}\n[bold]Function:[/bold] {error.function or 'N/A'}\n[bold]Time:[/bold] {error.timestamp}",
            title="Investigating Error",
        )
    )
    console.print(f"[dim]Context: {len(context)} log entries[/dim]")
    files_data = None
    if additional_files:
        files_list = []
        if log_file is not None:
            try:
                primary_content = log_file.read_text(encoding="utf-8", errors="replace")
                files_list.append({"filename": log_file.name, "content": primary_content, "error_line": error_line})
            except Exception as e:
                console.print(f"[yellow]Warning: Could not read primary file: {e}[/yellow]")
        for af in additional_files:
            if not af.exists():
                console.print(f"[yellow]Warning: File not found: {af}[/yellow]")
                continue
            try:
                af_content = af.read_text(encoding="utf-8", errors="replace")
                files_list.append({"filename": af.name, "content": af_content})
            except Exception as e:
                console.print(f"[yellow]Warning: Could not read {af}: {e}[/yellow]")
        if len(files_list) > 1:
            files_data = files_list
            console.print(
                f"[bold blue]Multi-file investigation:[/bold blue] {len(files_data)} files will be analyzed by the Chronicler"
            )
    try:
        if files_data:
            result = await _run_multifile_investigation(url, files_data, context_lines)
        else:
            result = await _run_single_investigation(
                url,
                log_content,
                error_line,
                context_lines,
                message,
                effective_verbose,
                effective_llm_log,
                effective_llm_all,
            )
    except Exception as e:
        console.print(f"[red]Investigation failed: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return
    if result is None:
        return
    display_result(console, result, effective_verbose)
    if result.investigation_id and sys.stdin.isatty():
        await _prompt_feedback(console, result, url)


async def _run_single_investigation(
    api_url: str,
    log_content: str,
    error_line: int | None,
    context_lines: int,
    message: str | None,
    verbose: bool,
    llm_log: bool,
    llm_all: bool,
) -> InvestigationResult | None:
    use_streaming = verbose or llm_log
    async with AgentClient(api_url) as client:
        session = await client.create_session()
        sid = session["session_id"]
        console.print(f"[dim]Session: {sid}[/dim]")
        try:
            if message is not None:
                pass
            else:
                with console.status("[bold blue]Uploading logs to API..."):
                    await client.parse_logs(sid, log_content, error_line=error_line, context_lines=context_lines)
            if use_streaming:
                return await _run_streaming_investigation(client, sid, message, verbose, llm_log, llm_all)
            else:
                return await _run_nonstreaming_investigation(client, sid, message)
        finally:
            try:
                await client.delete_session(sid)
            except Exception:
                pass


async def _run_streaming_investigation(
    client: AgentClient, session_id: str, message: str | None, verbose: bool, llm_log: bool, llm_all: bool
) -> InvestigationResult | None:
    verbose_display = VerboseDisplay(console) if verbose else None
    llm_display = LLMLoggingDisplay(console, show_all=llm_all) if llm_log else None
    md_formatter = MarkdownFormatter(full_output=llm_all) if llm_log else None
    md_renderer = ConsoleRenderer(console) if llm_log else None
    result_data = None
    async for event in client.investigate_stream(session_id, error_message=message, verbose=verbose or llm_log):
        if event.event.startswith("phase_"):
            phase_event = PhaseEvent(
                phase=event.data.get("phase", 0),
                phase_name=event.data.get("phase_name", ""),
                event_type=event.data.get("event_type", event.event.replace("phase_", "")),
                data=event.data.get("data", {}),
                message=event.data.get("message"),
            )
            if verbose_display:
                verbose_display.on_phase_event(phase_event)
        elif event.event == "llm_event" and llm_log:
            d = event.data
            llm_event = LLMEvent(
                phase=d.get("phase", 0),
                event_type=d.get("event_type", ""),
                system_prompt=d.get("system_prompt"),
                user_prompt=d.get("user_prompt"),
                response=d.get("response"),
                response_model=d.get("response_model"),
                model_name=d.get("model_name", ""),
                parse_failed=d.get("parse_failed", False),
                parse_error=d.get("parse_error"),
                expected_schema=d.get("expected_schema"),
            )
            if md_formatter and md_renderer:
                md = md_formatter.format_llm_event(llm_event)
                if md:
                    md_renderer.render(md)
            elif llm_display:
                llm_display.on_llm_event(llm_event)
        elif event.event == "data_retrieval_event" and llm_log:
            d = event.data
            data_event = DataRetrievalEvent(
                phase=d.get("phase", 0),
                event_type=d.get("event_type", ""),
                source=d.get("source", ""),
                operation=d.get("operation", ""),
                query_params=d.get("query_params", {}),
                result_summary=d.get("result_summary"),
                result_count=d.get("result_count"),
            )
            if md_formatter and md_renderer:
                md = md_formatter.format_data_event(data_event)
                if md:
                    md_renderer.render(md)
            elif llm_display:
                llm_display.on_data_event(data_event)
        elif event.event == "investigation_complete":
            result_data = event.data
        elif event.event == "error":
            console.print(f"[red]Error: {event.data.get('message')}[/red]")
            return None
    if result_data is None:
        console.print("[red]No investigation result received[/red]")
        return None
    return _build_investigation_result(result_data)


async def _run_nonstreaming_investigation(
    client: AgentClient, session_id: str, message: str | None
) -> InvestigationResult | None:
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Investigating...", total=None)
        try:
            result = await client.investigate(session_id, error_message=message)
        except Exception as e:
            progress.remove_task(task)
            console.print(f"[red]Investigation failed: {e}[/red]")
            return None
        progress.remove_task(task)
    result_data = result.get("result", result)
    return _build_investigation_result(result_data)


async def _run_multifile_investigation(
    api_url: str, files_data: list[dict], context_lines: int
) -> InvestigationResult | None:
    async with AgentClient(api_url) as client:
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Investigating (multi-file)...", total=None)
            try:
                result = await client.investigate_from_files(files_data, context_lines=context_lines)
            except Exception as e:
                progress.remove_task(task)
                console.print(f"[red]Investigation failed: {e}[/red]")
                return None
            progress.remove_task(task)
    result_data = result.get("result", result)
    return _build_investigation_result(result_data)


def _build_investigation_result(data: dict) -> InvestigationResult:
    try:
        return InvestigationResult.model_validate(data)
    except Exception:
        from srcs.models.investigation import InvestigationOutcome

        outcome_str = data.get("outcome", "INSUFFICIENT")
        try:
            outcome = InvestigationOutcome(outcome_str)
        except ValueError:
            outcome = InvestigationOutcome.INSUFFICIENT
        return InvestigationResult(
            investigation_id=data.get("investigation_id", ""),
            outcome=outcome,
            confidence=data.get("confidence", 0.0),
            root_cause=data.get("root_cause"),
            executive_summary=data.get("executive_summary", ""),
            explanation=data.get("explanation", ""),
            recommendations=data.get("recommendations", []),
        )


async def _prompt_feedback(con: Console, result: InvestigationResult, api_url: str) -> None:
    con.print()
    con.print(
        Panel("[bright_green]Your feedback helps improve future investigations.[/bright_green]", title="Reviewer")
    )
    response = Prompt.ask("Was this diagnosis correct?", choices=["y", "n", "skip"], default="skip")
    if response == "skip":
        con.print("[dim]Feedback skipped[/dim]")
        return
    was_correct = response == "y"
    actual_cause: str | None = None
    if not was_correct:
        actual_cause = Prompt.ask("Actual root cause", default="")
        if not actual_cause:
            actual_cause = None
    try:
        async with AgentClient(api_url) as client:
            await client.submit_feedback(
                result.investigation_id, was_correct, actual_cause=actual_cause, feedback_source="cli"
            )
        if was_correct:
            con.print("[green]Feedback recorded: Diagnosis was correct[/green]")
        else:
            con.print("[yellow]Feedback recorded: Diagnosis was incorrect[/yellow]")
            if actual_cause:
                con.print(f"[yellow]Actual cause: {actual_cause}[/yellow]")
    except Exception as e:
        con.print(f"[red]Failed to record feedback: {e}[/red]")
