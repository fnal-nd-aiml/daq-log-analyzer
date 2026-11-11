"""
File: admin.py
Purpose: Log parsing, source repositories and initialization.
Category: Utility
Author: artdaq team
Depends: config, sqlite_store, log_parser, source
Exports: register
Complexity: Medium | Lines: 158
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from mcp.server.fastmcp import FastMCP
from ..context import _json_default
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def parse_logs(content: str, error_line: int | None=None, context_lines: int=60) -> str:
        from srcs.models.log_parser import extract_error_and_context, parse_log_content
        try:
            logs = parse_log_content(content)
            if not logs:
                return json.dumps({'error': 'No parseable log entries found in content'})
            error, context = extract_error_and_context(logs, error_line, context_lines)

            def _log_to_dict(log: Any) -> dict:
                return {'timestamp': log.timestamp, 'level': log.level, 'component': log.component, 'function': log.function, 'message': log.message, 'raw_line': log.raw_line, 'line': log.line}
            return json.dumps({'trigger_error': _log_to_dict(error), 'context_logs': [_log_to_dict(lg) for lg in context], 'total_logs_parsed': len(logs)}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to parse logs')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def create_log_from_message(message: str) -> str:
        from srcs.models.log_parser import create_log_from_message as _create_log
        try:
            log = _create_log(message)
            return json.dumps({'timestamp': log.timestamp, 'level': log.level, 'component': log.component, 'function': log.function, 'message': log.message, 'raw_line': log.raw_line, 'line': log.line}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to create log from message')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def get_source_status() -> str:
        import asyncio
        from srcs.config import load_source_config
        from srcs.source import RepositoryManager
        try:
            source_config = load_source_config()
            if source_config is None:
                return json.dumps({'error': 'No source configuration found in config.yaml'})
            manager = RepositoryManager(source_config)
            repositories = []
            for repo_config in source_config.repositories:
                repo_name = repo_config.get_repo_name()
                repo_path = manager.get_repo_path(repo_config)
                if repo_path.exists() and (repo_path / '.git').exists():
                    status = await asyncio.to_thread(manager.get_repo_status, repo_path)
                    if status:
                        repositories.append({'name': repo_name, 'status': 'cloned', 'path': str(status.path), 'branch': status.branch, 'commit': status.commit, 'commit_date': status.commit_date, 'is_dirty': status.is_dirty})
                    else:
                        repositories.append({'name': repo_name, 'status': 'unknown'})
                else:
                    repositories.append({'name': repo_name, 'status': 'not_cloned', 'branch': repo_config.branch})
            return json.dumps({'repos_path': str(source_config.get_repos_path()), 'repositories': repositories}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to get source status')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def sync_sources() -> str:
        import asyncio
        from srcs.config import load_source_config
        from srcs.source import RepositoryManager
        try:
            source_config = load_source_config()
            if source_config is None:
                return json.dumps({'error': 'No source configuration found in config.yaml'})
            if not source_config.has_repositories():
                return json.dumps({'results': [], 'success_count': 0, 'failure_count': 0}, indent=2)
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
            return json.dumps({'results': results, 'success_count': success_count, 'failure_count': failure_count}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to sync sources')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def init_knowledge_base(skip_source: bool=False, skip_ollama_check: bool=False) -> str:
        import asyncio
        import yaml
        try:
            config_path = Path('config.yaml')
            if not config_path.exists():
                return json.dumps({'error': 'config.yaml not found'})
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}
            storage_cfg = config_data.get('storage', {})
            data_dir = Path(storage_cfg.get('sqlite_path', './data/knowledge.db')).parent
            steps = []
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
                steps.append({'step': 'init_database', 'success': True, 'message': f'SQLite schema initialized at {db_path}'})
            except Exception as e:
                steps.append({'step': 'init_database', 'success': False, 'message': str(e)})
                all_success = False
            if not skip_ollama_check:
                llm_config = config_data.get('llm', {})
                provider = llm_config.get('provider', 'ollama')
                if provider == 'ollama':
                    steps.append({'step': 'check_ollama', 'success': True, 'message': 'Ollama check: use admin API for details'})
                else:
                    steps.append({'step': 'check_ollama', 'success': True, 'message': f"Provider is '{provider}', Ollama check not needed"})
            else:
                steps.append({'step': 'check_ollama', 'success': True, 'message': 'Skipped (skip_ollama_check=true)'})
            if not skip_source:
                from srcs.config import load_source_config
                from srcs.source import RepositoryManager
                source_config = load_source_config()
                if source_config and source_config.has_repositories():
                    try:
                        manager = RepositoryManager(source_config)
                        sync_results = await asyncio.to_thread(manager.sync_all)
                        synced = sum((1 for r in sync_results if r.success))
                        failed = sum((1 for r in sync_results if not r.success))
                        msg = f'{synced} repos synced'
                        if failed:
                            msg += f', {failed} failed'
                            all_success = False
                        steps.append({'step': 'sync_source', 'success': failed == 0, 'message': msg})
                    except Exception as e:
                        steps.append({'step': 'sync_source', 'success': False, 'message': str(e)})
                        all_success = False
                else:
                    steps.append({'step': 'sync_source', 'success': True, 'message': 'No source repositories configured'})
            else:
                steps.append({'step': 'sync_source', 'success': True, 'message': 'Skipped (skip_source=true)'})
            return json.dumps({'success': all_success, 'steps': steps}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to initialize knowledge base')
            return json.dumps({'error': str(e)}, indent=2)