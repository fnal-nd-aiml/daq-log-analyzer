"""
File: main.py
Purpose: CLI entry point.
Category: Utility
Author: artdaq team
Depends: srcs, mcp, slack, rich
Exports: load_logging_config, main_callback, investigate, feedback, list_investigations, ...
Complexity: Medium | Lines: 213
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
import typer
import yaml
from rich.console import Console

app = typer.Typer(
    name="artdaq-agent", help="LLM-powered root cause analysis for artdaq DAQ software", add_completion=False
)
console = Console()
DEFAULT_API_URL = "http://localhost:8000"


def _resolve_api_url(api_url: str | None) -> str:
    return api_url or os.environ.get("ARTDAQ_API_URL", DEFAULT_API_URL)


def load_logging_config() -> dict:
    try:
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
            return config.get("logging", {"level": "WARNING"})
    except FileNotFoundError:
        return {"level": "WARNING"}


@app.callback()
def main_callback(
    ctx: typer.Context,
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging"),
    api_url: str = typer.Option(
        None, "--api-url", help="REST API URL (default: $ARTDAQ_API_URL or http://localhost:8000)"
    ),
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = _resolve_api_url(api_url)
    logging_config = load_logging_config()
    if debug:
        level = logging.DEBUG
    else:
        level_str = logging_config.get("level", "WARNING").upper()
        level = getattr(logging, level_str, logging.WARNING)
    logging.basicConfig(level=level, format="%(levelname)s: %(name)s: %(message)s")


@app.command()
def investigate(
    ctx: typer.Context,
    log_file: Path = typer.Argument(None, help="Path to log file to investigate"),
    message: str = typer.Option(None, "--message", "-m", help="Error message to investigate directly"),
    content: str = typer.Option(None, "--content", "-t", help="Raw log content to investigate"),
    error_line: int = typer.Option(None, "--error", "-e", help="Line number of specific error to investigate"),
    context_lines: int = typer.Option(60, "--context", "-c", help="Number of context lines before error"),
    config_file: Path = typer.Option(None, "--config", help="Path to configuration file"),
    verbose: bool | None = typer.Option(None, "--verbose", "-v", help="Show verbose output (default from config.yaml)"),
    llm_log: bool | None = typer.Option(
        None, "--llm-log", "-l", help="Log LLM communications (default from config.yaml)"
    ),
    llm_all: bool | None = typer.Option(
        None, "--llm-all", "-a", help="Show full LLM output (default from config.yaml)"
    ),
    additional_files: list[Path] | None = typer.Option(
        None, "--files", "-f", help="Additional log files for multi-file investigation"
    ),
    api_url: str | None = typer.Option(None, "--api-url", help="Override REST API URL for this command"),
) -> None:
    if log_file is None and message is None and (content is None):
        if not sys.stdin.isatty():
            content = sys.stdin.read()
        else:
            console.print("[red]Error: Must provide a log file, --message, --content, or pipe via stdin[/red]")
            raise typer.Exit(1)
    sources = sum((x is not None for x in [log_file, message, content]))
    if sources > 1:
        console.print("[red]Error: Only one of log file, --message, or --content allowed[/red]")
        raise typer.Exit(1)
    if log_file is not None and (not log_file.exists()):
        console.print(f"[red]Log file not found: {log_file}[/red]")
        raise typer.Exit(1)
    effective_url = api_url or ctx.obj.get("api_url")
    from .investigate import run_investigation

    asyncio.run(
        run_investigation(
            log_file,
            error_line,
            context_lines,
            config_file,
            verbose,
            message,
            llm_log,
            llm_all,
            content,
            additional_files=additional_files,
            api_url=effective_url,
        )
    )


@app.command()
def feedback(
    ctx: typer.Context,
    investigation_id: str = typer.Argument(..., help="Investigation ID to provide feedback for"),
    correct: bool = typer.Option(None, "--correct/--incorrect", help="Was the diagnosis correct?"),
    actual_cause: str = typer.Option(None, "--actual", "-a", help="The actual root cause (if incorrect)"),
) -> None:
    from .feedback import submit_feedback

    asyncio.run(submit_feedback(investigation_id, correct, actual_cause, api_url=ctx.obj.get("api_url")))


@app.command(name="list")
def list_investigations(
    ctx: typer.Context, limit: int = typer.Option(10, "--limit", "-n", help="Number of investigations to show")
) -> None:
    from .feedback import list_recent_investigations

    asyncio.run(list_recent_investigations(limit, api_url=ctx.obj.get("api_url")))


@app.command()
def init(
    ctx: typer.Context,
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d", help="Data directory path"),
    skip_source: bool = typer.Option(False, "--skip-source", help="Skip syncing source repositories"),
    config_file: Path = typer.Option(None, "--config", help="Path to configuration file"),
) -> None:
    from .init import init_knowledge_base

    init_knowledge_base(data_dir, skip_source=skip_source, config_path=config_file, api_url=ctx.obj.get("api_url"))


@app.command(name="sync-source")
def sync_source(
    ctx: typer.Context,
    config_file: Path = typer.Option(None, "--config", help="Path to configuration file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose output"),
    status: bool = typer.Option(False, "--status", "-s", help="Show repository status only, don't sync"),
) -> None:
    from .source_cmd import run_sync_source

    run_sync_source(config_path=config_file, verbose=verbose, status_only=status, api_url=ctx.obj.get("api_url"))


@app.command()
def ask(
    ctx: typer.Context,
    question: str = typer.Argument(..., help="Question to ask the panel of experts"),
    log_file: Path = typer.Option(None, "--log", "-l", help="Path to log file for context"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose output with panel deliberation"),
    config_file: Path = typer.Option(None, "--config", help="Path to configuration file"),
) -> None:
    if log_file is not None and (not log_file.exists()):
        console.print(f"[red]Log file not found: {log_file}[/red]")
        raise typer.Exit(1)
    from .ask import run_ask

    asyncio.run(run_ask(question, log_file, verbose, config_file, api_url=ctx.obj.get("api_url")))


@app.command()
def mcp(
    sse: bool = typer.Option(False, "--sse", help="Use SSE transport instead of stdio"),
    streamable_http: bool = typer.Option(
        False, "--streamable-http", help="Use Streamable HTTP transport (for OpenWebUI)"
    ),
    port: int = typer.Option(8001, "--port", "-p", help="Port for SSE/Streamable HTTP transport"),
) -> None:
    from srcs.mcp import run_mcp_server

    if streamable_http:
        transport = "streamable-http"
        console.print(f"[dim]Starting MCP server (Streamable HTTP on port {port})...[/dim]")
    elif sse:
        transport = "sse"
        console.print(f"[dim]Starting MCP server (SSE transport on port {port})...[/dim]")
    else:
        transport = "stdio"
        console.print("[dim]Starting MCP server (stdio transport)...[/dim]")
    run_mcp_server(transport=transport, port=port)


@app.command()
def slack(
    socket_mode: bool = typer.Option(True, "--socket/--http", help="Use Socket Mode (default) or HTTP mode"),
    port: int = typer.Option(3000, "--port", "-p", help="Port for HTTP mode"),
) -> None:
    from srcs.slack import run_slack_bot

    mode_name = "Socket Mode" if socket_mode else f"HTTP mode on port {port}"
    console.print(f"[dim]Starting Slack bot ({mode_name})...[/dim]")
    try:
        asyncio.run(run_slack_bot(socket_mode=socket_mode, port=port))
    except KeyboardInterrupt:
        console.print("\n[dim]Slack bot stopped by user[/dim]")


@app.command()
def version() -> None:
    from srcs import __version__

    console.print(f"artdaq-agent version {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
