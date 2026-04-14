"""
File: admin.py
Purpose: Admin endpoints for log parsing, source management, and initializat...
Category: Utility
Author: artdaq team
Depends: config, extraction, sqlite_store, log_parser, source, ...
Exports: ParsedLogEntry, ParseLogsRequest, ParseLogsResponse, MessageRequest, RepoStatusResponse, ...
Complexity: High | Lines: 343
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from srcs.config import load_source_config
from srcs.models.log_parser import create_log_from_message, extract_error_and_context, parse_log_content
from srcs.source import RepositoryManager, SourceConfig

logger = logging.getLogger(__name__)
router = APIRouter()


class ParsedLogEntry(BaseModel):
    timestamp: datetime
    level: str
    component: str
    function: str | None = None
    message: str
    raw_line: str | None = None
    line: int | None = None


class ParseLogsRequest(BaseModel):
    content: str = Field(..., description="Raw log text content")
    error_line: int | None = Field(default=None, description="Specific error line number")
    context_lines: int = Field(default=60, description="Number of context lines around the error")


class ParseLogsResponse(BaseModel):
    trigger_error: ParsedLogEntry
    context_logs: list[ParsedLogEntry]
    total_logs_parsed: int


class MessageRequest(BaseModel):
    message: str = Field(..., description="Error message text")


class RepoStatusResponse(BaseModel):
    name: str
    status: str
    path: str | None = None
    branch: str | None = None
    commit: str | None = None
    commit_date: str | None = None
    is_dirty: bool | None = None


class SourceStatusResponse(BaseModel):
    repos_path: str
    repositories: list[RepoStatusResponse]


class SyncResultResponse(BaseModel):
    repo_name: str
    success: bool
    action: str
    message: str
    path: str | None = None


class SyncResponse(BaseModel):
    results: list[SyncResultResponse]
    success_count: int
    failure_count: int


class InitRequest(BaseModel):
    skip_source: bool = Field(default=False, description="Skip syncing source repositories")
    skip_ollama_check: bool = Field(default=False, description="Skip checking Ollama model availability")


class InitStepResult(BaseModel):
    step: str
    success: bool
    message: str


class InitResponse(BaseModel):
    success: bool
    steps: list[InitStepResult]


@router.post("/logs/parse", response_model=ParseLogsResponse)
async def parse_logs(request: ParseLogsRequest) -> ParseLogsResponse:
    logs = parse_log_content(request.content)
    if not logs:
        raise HTTPException(status_code=422, detail="No parseable log entries found in content")
    error, context = extract_error_and_context(logs, request.error_line, request.context_lines)
    return ParseLogsResponse(
        trigger_error=ParsedLogEntry(
            timestamp=error.timestamp,
            level=error.level,
            component=error.component,
            function=error.function,
            message=error.message,
            raw_line=error.raw_line,
            line=error.line,
        ),
        context_logs=[
            ParsedLogEntry(
                timestamp=log.timestamp,
                level=log.level,
                component=log.component,
                function=log.function,
                message=log.message,
                raw_line=log.raw_line,
                line=log.line,
            )
            for log in context
        ],
        total_logs_parsed=len(logs),
    )


@router.post("/logs/from-message", response_model=ParsedLogEntry)
async def log_from_message(request: MessageRequest) -> ParsedLogEntry:
    log = create_log_from_message(request.message)
    return ParsedLogEntry(
        timestamp=log.timestamp,
        level=log.level,
        component=log.component,
        function=log.function,
        message=log.message,
        raw_line=log.raw_line,
        line=log.line,
    )


def _load_source_config_or_404() -> SourceConfig:
    source_config = load_source_config()
    if source_config is None:
        raise HTTPException(
            status_code=404, detail="No source configuration found. Add a 'source' section to config.yaml."
        )
    return source_config


@router.get("/source/status", response_model=SourceStatusResponse)
async def source_status() -> SourceStatusResponse:
    source_config = _load_source_config_or_404()
    manager = RepositoryManager(source_config)
    repositories: list[RepoStatusResponse] = []
    for repo_config in source_config.repositories:
        repo_name = repo_config.get_repo_name()
        repo_path = manager.get_repo_path(repo_config)
        if repo_path.exists() and (repo_path / ".git").exists():
            status = await asyncio.to_thread(manager.get_repo_status, repo_path)
            if status:
                repositories.append(
                    RepoStatusResponse(
                        name=repo_name,
                        status="cloned",
                        path=str(status.path),
                        branch=status.branch,
                        commit=status.commit,
                        commit_date=status.commit_date,
                        is_dirty=status.is_dirty,
                    )
                )
            else:
                repositories.append(RepoStatusResponse(name=repo_name, status="unknown"))
        else:
            repositories.append(RepoStatusResponse(name=repo_name, status="not_cloned", branch=repo_config.branch))
    return SourceStatusResponse(repos_path=str(source_config.get_repos_path()), repositories=repositories)


@router.post("/source/sync", response_model=SyncResponse)
async def source_sync() -> SyncResponse:
    source_config = _load_source_config_or_404()
    if not source_config.has_repositories():
        return SyncResponse(results=[], success_count=0, failure_count=0)
    manager = RepositoryManager(source_config)
    sync_results = await asyncio.to_thread(manager.sync_all)
    results: list[SyncResultResponse] = []
    success_count = 0
    failure_count = 0
    for r in sync_results:
        results.append(
            SyncResultResponse(
                repo_name=r.repo_name,
                success=r.success,
                action=r.action,
                message=r.message,
                path=str(r.path) if r.path else None,
            )
        )
        if r.success:
            success_count += 1
        else:
            failure_count += 1
    return SyncResponse(results=results, success_count=success_count, failure_count=failure_count)


@router.post("/init", response_model=InitResponse)
async def init_knowledge_base(request: InitRequest) -> InitResponse:
    steps: list[InitStepResult] = []
    all_success = True
    config_path = Path("config.yaml")
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="config.yaml not found. API requires it to already exist.")
    import yaml

    try:
        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}
    except (IOError, OSError) as e:
        logger.error("Failed to read config.yaml: %s", e)
        raise HTTPException(status_code=500, detail="Configuration error")
    except yaml.YAMLError as e:
        logger.error("Failed to parse config.yaml: %s", e)
        raise HTTPException(status_code=500, detail="Configuration error")
    storage_cfg = config_data.get("storage", {})
    data_dir = Path(storage_cfg.get("sqlite_path", "./data/knowledge.db")).parent
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "chroma").mkdir(exist_ok=True)
        steps.append(InitStepResult(step="create_directories", success=True, message=f"Created {data_dir}"))
    except OSError as e:
        logger.error("Failed to create directories: %s", e)
        steps.append(InitStepResult(step="create_directories", success=False, message="Failed to create directories"))
        all_success = False
    try:
        from srcs.knowledge.sqlite_store import SQLiteStore

        db_path = data_dir / "knowledge.db"
        store = SQLiteStore(db_path)
        await store._ensure_initialized()
        steps.append(
            InitStepResult(step="init_database", success=True, message=f"SQLite schema initialized at {db_path}")
        )
    except (OSError, ImportError) as e:
        logger.error("Failed to initialize database: %s", e)
        steps.append(InitStepResult(step="init_database", success=False, message="Failed to initialize database"))
        all_success = False
    if not request.skip_ollama_check:
        try:
            ollama_result = await asyncio.to_thread(_check_ollama_models_no_pull, config_data)
            steps.append(ollama_result)
            if not ollama_result.success:
                all_success = False
        except (ConnectionError, OSError) as e:
            logger.error("Failed to check Ollama models: %s", e)
            steps.append(InitStepResult(step="check_ollama", success=False, message="Failed to check Ollama models"))
            all_success = False
    else:
        steps.append(InitStepResult(step="check_ollama", success=True, message="Skipped (skip_ollama_check=true)"))
    if not request.skip_source:
        source_config = load_source_config()
        if source_config and source_config.has_repositories():
            try:
                manager = RepositoryManager(source_config)
                sync_results = await asyncio.to_thread(manager.sync_all)
                synced = sum((1 for r in sync_results if r.success))
                failed = sum((1 for r in sync_results if not r.success))
                msg = f"{synced} repos synced"
                if failed:
                    msg += f", {failed} failed"
                    all_success = False
                steps.append(InitStepResult(step="sync_source", success=failed == 0, message=msg))
            except (OSError, RuntimeError) as e:
                logger.error("Failed to sync source repositories: %s", e)
                steps.append(
                    InitStepResult(step="sync_source", success=False, message="Failed to sync source repositories")
                )
                all_success = False
            if source_config.auto_index:
                try:
                    index_result = await asyncio.to_thread(_build_code_index, source_config, data_dir)
                    steps.append(index_result)
                    if not index_result.success:
                        all_success = False
                except (OSError, RuntimeError) as e:
                    logger.error("Failed to build code index: %s", e)
                    steps.append(
                        InitStepResult(step="build_index", success=False, message="Failed to build code index")
                    )
                    all_success = False
        else:
            steps.append(InitStepResult(step="sync_source", success=True, message="No source repositories configured"))
    else:
        steps.append(InitStepResult(step="sync_source", success=True, message="Skipped (skip_source=true)"))
    return InitResponse(success=all_success, steps=steps)


def _check_ollama_models_no_pull(config_data: dict) -> InitStepResult:
    import httpx

    llm_config = config_data.get("llm", {})
    provider = llm_config.get("provider", "ollama")
    if provider != "ollama":
        return InitStepResult(
            step="check_ollama", success=True, message=f"Provider is '{provider}', Ollama check not needed"
        )
    providers = llm_config.get("providers", {})
    ollama_cfg = providers.get("ollama", {})
    embedding_cfg = llm_config.get("embedding", {})
    host = (
        ollama_cfg.get("host") or embedding_cfg.get("host") or llm_config.get("ollama_host", "http://localhost:11434")
    )
    model = ollama_cfg.get("model") or llm_config.get("model", "gpt-oss:120b")
    embedding_model = embedding_cfg.get("model") or llm_config.get("embedding_model", "nomic-embed-text")
    try:
        response = httpx.get(f"{host}/api/tags", timeout=10)
        response.raise_for_status()
        available = response.json().get("models", [])
        available_names = {m["name"] for m in available}
        available_base = {m["name"].split(":")[0] for m in available}
    except httpx.ConnectError:
        return InitStepResult(step="check_ollama", success=False, message=f"Cannot connect to Ollama at {host}")
    except (httpx.HTTPError, ConnectionError, OSError) as e:
        logger.error("Error checking Ollama: %s", e)
        return InitStepResult(step="check_ollama", success=False, message="Error checking Ollama")
    missing: list[str] = []
    found: list[str] = []
    for name in [model, embedding_model]:
        base = name.split(":")[0]
        if name in available_names or base in available_base:
            found.append(name)
        else:
            missing.append(name)
    if missing:
        return InitStepResult(step="check_ollama", success=False, message=f"Available: {found}. Missing: {missing}")
    return InitStepResult(step="check_ollama", success=True, message=f"Models available: {found}")


def _build_code_index(source_config: SourceConfig, data_dir: Path) -> InitStepResult:
    from srcs.extraction import CodeIndex, CodeIndexConfig

    manager = RepositoryManager(source_config)
    repo_paths = manager.get_existing_repo_paths()
    if not repo_paths:
        return InitStepResult(step="build_index", success=True, message="No repositories to index")
    config = CodeIndexConfig(source_roots=repo_paths, index_path=data_dir / "code_index.db")
    index = CodeIndex(config)
    stats = index.build_index()
    return InitStepResult(
        step="build_index",
        success=True,
        message=f"Indexed {stats['files_indexed']} files, {stats['functions_found']} functions, {stats['classes_found']} classes",
    )
