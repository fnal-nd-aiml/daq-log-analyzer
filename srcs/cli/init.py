"""
File: init.py
Purpose: Initialize command implementation.
Category: Utility
Author: artdaq team
Depends: client, rich
Exports: load_llm_config, check_ollama_models, pull_ollama_model, init_knowledge_base, DEFAULT_API_URL
Complexity: Medium | Lines: 174
"""

import asyncio
import os
from pathlib import Path
import httpx
import yaml
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from srcs.api.client import AgentClient

console = Console()
DEFAULT_API_URL = "http://localhost:8000"


def _get_api_url(api_url: str | None = None) -> str:
    return api_url or os.environ.get("ARTDAQ_API_URL", DEFAULT_API_URL)


def load_llm_config(config_path: Path | None = None) -> dict:
    defaults = {
        "provider": "ollama",
        "model": "gpt-oss:120b",
        "embedding_model": "nomic-embed-text",
        "ollama_host": "http://localhost:11434",
    }
    if config_path and config_path.exists():
        cfg_path = config_path
    elif Path("config.yaml").exists():
        cfg_path = Path("config.yaml")
    else:
        return defaults
    try:
        with open(cfg_path) as f:
            config = yaml.safe_load(f) or {}
        llm_config = config.get("llm", {})
        result = {**defaults}
        result["provider"] = llm_config.get("provider", defaults["provider"])
        providers = llm_config.get("providers", {})
        ollama_cfg = providers.get("ollama", {})
        embedding_cfg = llm_config.get("embedding", {})
        if ollama_cfg.get("model"):
            result["model"] = ollama_cfg["model"]
        elif llm_config.get("model"):
            result["model"] = llm_config["model"]
        if embedding_cfg.get("model"):
            result["embedding_model"] = embedding_cfg["model"]
        elif llm_config.get("embedding_model"):
            result["embedding_model"] = llm_config["embedding_model"]
        if ollama_cfg.get("host"):
            result["ollama_host"] = ollama_cfg["host"]
        elif embedding_cfg.get("host"):
            result["ollama_host"] = embedding_cfg["host"]
        elif llm_config.get("ollama_host"):
            result["ollama_host"] = llm_config["ollama_host"]
        return result
    except Exception:
        return defaults


def check_ollama_models(config_path: Path | None = None) -> bool:
    llm_config = load_llm_config(config_path)
    provider = llm_config.get("provider", "ollama")
    if provider != "ollama":
        return True
    ollama_host = llm_config.get("ollama_host", "http://localhost:11434")
    model = llm_config.get("model", "gpt-oss:120b")
    embedding_model = llm_config.get("embedding_model", "nomic-embed-text")
    console.print()
    console.print("[bold]Checking Ollama models...[/bold]")
    try:
        response = httpx.get(f"{ollama_host}/api/tags", timeout=10)
        response.raise_for_status()
        available_models = response.json().get("models", [])
        available_names = {m["name"] for m in available_models}
        available_base_names = {m["name"].split(":")[0] for m in available_models}
    except httpx.ConnectError:
        console.print(f"  [red]✗[/red] Cannot connect to Ollama at {ollama_host}")
        console.print("    Run: [cyan]ollama serve[/cyan]")
        return False
    except Exception as e:
        console.print(f"  [red]✗[/red] Error checking Ollama: {e}")
        return False
    all_available = True
    required_models = [("Main model", model), ("Embedding model", embedding_model)]
    for label, model_name in required_models:
        base_name = model_name.split(":")[0]
        if model_name in available_names or base_name in available_base_names:
            console.print(f"  [green]✓[/green] {label}: {model_name}")
        else:
            console.print(f"  [yellow]○[/yellow] {label}: {model_name} (not found, pulling...)")
            if not pull_ollama_model(ollama_host, model_name):
                all_available = False
    return all_available


def pull_ollama_model(ollama_host: str, model_name: str) -> bool:
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.fields[status]}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Pulling {model_name}...", status="starting")
            with httpx.stream("POST", f"{ollama_host}/api/pull", json={"name": model_name}, timeout=None) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        data = yaml.safe_load(line)
                        status = data.get("status", "")
                        if "completed" in data and "total" in data:
                            completed = data["completed"]
                            total = data["total"]
                            pct = int(100 * completed / total) if total > 0 else 0
                            progress.update(task, status=f"{status} ({pct}%)")
                        else:
                            progress.update(task, status=status)
        console.print(f"    [green]✓[/green] Successfully pulled {model_name}")
        return True
    except Exception as e:
        console.print(f"    [red]✗[/red] Failed to pull {model_name}: {e}")
        console.print(f"      Run manually: [cyan]ollama pull {model_name}[/cyan]")
        return False


def init_knowledge_base(
    data_dir: Path, skip_source: bool = False, config_path: Path | None = None, api_url: str | None = None
) -> None:
    models_ok = check_ollama_models(config_path)
    if not models_ok:
        console.print()
        console.print("[yellow]Warning: Some models are not available[/yellow]")
    config_file = Path("config.yaml")
    if not config_file.exists():
        try:
            default_config = f'# artdaq Deep Investigation Agent Configuration\n\nllm:\n  provider: "ollama"\n  model: "gpt-oss:120b"\n  embedding_model: "nomic-embed-text"\n  temperature: 0.1\n  max_tokens: 4096\n  ollama_host: "http://localhost:11434"\n\nstorage:\n  sqlite_path: "{data_dir}/knowledge.db"\n  chroma_path: "{data_dir}/chroma"\n\ninvestigation:\n  max_hypotheses: 10\n  max_evidence_iterations: 10\n  max_chain_depth: 8\n  confidence_floor: 0.1\n  confidence_ceiling: 0.95\n\n'
            config_file.write_text(default_config)
            console.print(f"[green]Created default config: {config_file}[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not create config: {e}[/yellow]")
    url = _get_api_url(api_url)
    console.print()
    console.print("[bold]Initializing via API...[/bold]")
    try:
        asyncio.run(_init_via_api(url, skip_source))
    except Exception as e:
        console.print(f"[red]Initialization failed: {e}[/red]")
        console.print("[dim]Make sure the API server is running: ./run.sh api[/dim]")
        return
    console.print()
    console.print("[bold]Knowledge base initialized![/bold]")
    console.print()
    console.print("Next steps:")
    console.print("  1. Run investigation: ./run.sh investigate <logfile>")


async def _init_via_api(api_url: str, skip_source: bool) -> None:
    async with AgentClient(api_url) as client:
        result = await client.init_system(skip_source=skip_source)
    status = result.get("status", "unknown")
    if status == "success":
        for step in result.get("steps", []):
            step_name = step.get("name", "")
            step_status = step.get("status", "")
            if step_status == "success":
                console.print(f"  [green]✓[/green] {step_name}")
            elif step_status == "skipped":
                console.print(f"  [dim]○[/dim] {step_name} (skipped)")
            else:
                message = step.get("message", "")
                console.print(f"  [yellow]⚠[/yellow] {step_name}: {message}")
    else:
        message = result.get("message", "Unknown error")
        console.print(f"  [red]✗[/red] {message}")
