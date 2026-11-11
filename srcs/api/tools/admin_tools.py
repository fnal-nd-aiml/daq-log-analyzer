"""
File: admin_tools.py
Purpose: Admin tools for knowledge base and source management (session-less).
Category: Utility
Author: artdaq team
Depends: config, sqlite_store, source
Exports: init_knowledge_base, sync_sources
Complexity: Medium | Lines: 85
"""

from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Any
from ..errors import validation_error
from .router import ToolContext, register_tool
logger = logging.getLogger(__name__)

@register_tool('init_knowledge_base', session_less=True)
async def init_knowledge_base(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get('params', {})
    skip_source = params.get('skip_source', False)
    _ = params.get('skip_ollama_check', False)
    config_path = Path('config.yaml')
    if not config_path.exists():
        raise validation_error('config.yaml not found.')
    import yaml
    with open(config_path) as f:
        config_data = yaml.safe_load(f) or {}
    storage_cfg = config_data.get('storage', {})
    data_dir = Path(storage_cfg.get('sqlite_path', './data/knowledge.db')).parent
    steps: list[dict[str, Any]] = []
    all_success = True
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / 'chroma').mkdir(exist_ok=True)
        steps.append({'step': 'create_directories', 'success': True, 'message': f'Created {data_dir}'})
    except Exception as e:
        steps.append({'step': 'create_directories', 'success': False, 'message': str(e)})
        all_success = False
    try:
        from srcs.knowledge.sqlite_store import SQLiteStore
        db_path = data_dir / 'knowledge.db'
        store = SQLiteStore(db_path)
        await store._ensure_initialized()
        steps.append({'step': 'init_database', 'success': True, 'message': f'SQLite initialized at {db_path}'})
    except Exception as e:
        steps.append({'step': 'init_database', 'success': False, 'message': str(e)})
        all_success = False
    if not skip_source:
        try:
            from srcs.config import load_source_config
            from srcs.source import RepositoryManager
            source_config = load_source_config()
            if source_config and source_config.has_repositories():
                manager = RepositoryManager(source_config)
                sync_results = await asyncio.to_thread(manager.sync_all)
                synced = sum((1 for r in sync_results if r.success))
                failed = sum((1 for r in sync_results if not r.success))
                msg = f'{synced} repos synced'
                if failed:
                    msg += f', {failed} failed'
                    all_success = False
                steps.append({'step': 'sync_source', 'success': failed == 0, 'message': msg})
            else:
                steps.append({'step': 'sync_source', 'success': True, 'message': 'No source repos configured'})
        except Exception as e:
            steps.append({'step': 'sync_source', 'success': False, 'message': str(e)})
            all_success = False
    else:
        steps.append({'step': 'sync_source', 'success': True, 'message': 'Skipped'})
    return {'success': all_success, 'steps': steps}

@register_tool('sync_sources', session_less=True)
async def sync_sources(ctx: ToolContext) -> dict[str, Any]:
    from srcs.config import load_source_config
    from srcs.source import RepositoryManager
    source_config = load_source_config()
    if source_config is None:
        raise validation_error('No source configuration found in config.yaml.')
    if not source_config.has_repositories():
        return {'results': [], 'success_count': 0, 'failure_count': 0}
    manager = RepositoryManager(source_config)
    sync_results = await asyncio.to_thread(manager.sync_all)
    results = []
    success_count = 0
    failure_count = 0
    for r in sync_results:
        results.append({'repo_name': r.repo_name, 'success': r.success, 'action': r.action, 'message': r.message, 'path': str(r.path) if r.path else None})
        if r.success:
            success_count += 1
        else:
            failure_count += 1
    return {'results': results, 'success_count': success_count, 'failure_count': failure_count}